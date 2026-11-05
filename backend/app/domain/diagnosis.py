"""Crop photo -> structured, safe assessment. The vision model describes; this code decides what is shown.

Only symptoms / severity / possible causes come from the model, and each is sanitised: no brands, no application
rates, bounded length. Recommendations and disclaimer are fixed safe text, never model output.
"""
from __future__ import annotations

import re

from app.llm.client import parse_json

VISION_PROMPT = (
    "You are an expert plant pathologist analyzing a crop leaf or plant photograph. "
    "Identify the crop, observe all visible symptoms (lesions, chlorosis, discoloration, wilting, pest damage), "
    "and determine the most probable cause.\n"
    "OUTPUT FORMAT: Strict JSON matching this schema:\n"
    '{"crop": "<crop_name>", "symptoms": ["<symptom_1>", "<symptom_2>"], '
    '"severity": "mild | moderate | severe", "possible_causes": ["<fungal/bacterial/pest_name>"], '
    '"recommendations": ["<cultural_or_organic_step_1>", "<step_2>"], '
    '"disclaimer": "Field diagnosis requires physical inspection. Consult your Taluka Krishi Adhikari or KVK."}\n'
    "Rules: describe only what is visible. At most 5 items per list. "
    "Use words, not numbers or percentages. Do NOT recommend proprietary brand chemical formulations or off-label doses. "
    "If the photo is not a plant or crop, set crop to unknown and symptoms to []."
)

BRAND_PATTERN = (
    r"\b(?:Roundup|Bayer|Syngenta|BASF|Corteva|Tata\s+Rallis|UPL|Dhanuka|FMC|Confidor|Antracol|Ridomil|Coragen|Amistar|Nativo|Tafgor|Lancer|Actara|Regent)\b"
    r"|\u0930\u093e\u0909\u0902\u0921\u0905\u092a|\u0930\u093e\u0909\u0902\u0921-?\u0905\u092a|\u0930\u093f\u0921\u094b\u092e\u093f\u0932|\u0915\u0949\u0928\u094d\u092b\u093f\u0921\u0949\u0930|\u0915\u0949\u0928\u094d\u092b\u093f\u0921\u094b\u0930|\u092c\u093e\u092f\u0930|\u0938\u093f\u0902\u091c\u0947\u0902\u091f\u093e|\u0938\u093f\u0902\u0917\u0947\u0902\u091f\u093e|\u092f\u0942\u092a\u0940\u090f\u0932|\u0927\u093e\u0928\u0941\u0915\u093e|\u0915\u094b\u0930\u094d\u091f\u0947\u0935\u093e|\u0915\u094b\u0930\u093e\u091c\u0947\u0928"
)
RATE_PATTERN = (
    r"[\d.]+\s*(?:ml|g|gm|kg|l|litre|liter)s?\s*(?:per|/)\s*(?:acre|hectare|ha|bigha|litre|liter|l)\b"
    # Hindi/Marathi: "20 \u092e\u093f\u0932\u0940 \u092a\u094d\u0930\u0924\u093f \u0932\u0940\u091f\u0930", "\u090f\u0915\u0930\u0940 500 \u0917\u094d\u0930\u0945\u092e", "\u092a\u094d\u0930\u0924\u093f \u090f\u0915\u0921\u093c 2 \u0915\u093f\u0932\u094b"
    r"|[\d.]+\s*(?:\u092e\u093f\u0932\u0940|\u092e\u093f\.\u0932\u0940\.?|\u0917\u094d\u0930\u093e\u092e|\u0917\u094d\u0930\u0945\u092e|\u0915\u093f\u0932\u094b|\u0932\u0940\u091f\u0930|\u0932\u093f\u091f\u0930)\s*(?:\u092a\u094d\u0930\u0924\u093f|/)\s*(?:\u090f\u0915\u0921\u093c|\u090f\u0915\u0930|\u0939\u0947\u0915\u094d\u091f\u0930|\u0939\u0947\u0915\u094d\u091f\u0947\u092f\u0930|\u0932\u0940\u091f\u0930|\u0932\u093f\u091f\u0930|\u092c\u0940\u0918\u093e)"
    r"|(?:\u090f\u0915\u0930\u0940|\u092a\u094d\u0930\u0924\u093f \u090f\u0915\u0921\u093c|\u092a\u094d\u0930\u0924\u093f \u090f\u0915\u0930)\s*[\d.]+\s*(?:\u092e\u093f\u0932\u0940|\u0917\u094d\u0930\u093e\u092e|\u0917\u094d\u0930\u0945\u092e|\u0915\u093f\u0932\u094b|\u0932\u0940\u091f\u0930|\u0932\u093f\u091f\u0930)"
)
_UNSAFE = re.compile(f"{BRAND_PATTERN}|{RATE_PATTERN}", re.I)
SEVERITIES = {"none", "mild", "moderate", "severe"}
RECOMMENDATIONS = [
    "Show the affected plants to your local Krishi Vigyan Kendra (KVK) or agriculture officer.",
    "If any treatment is advised, follow the product label.",
]
DISCLAIMER = "This is a visual assessment from a photo only. Confirm with your agriculture officer before acting."


def _clean(items, limit: int = 5) -> list[str]:
    if not isinstance(items, list):
        return []
    out = []
    for x in items:
        if isinstance(x, str) and x.strip() and not _UNSAFE.search(x):
            out.append(x.strip()[:120])
    return out[:limit]


def parse_diagnosis(text: str) -> dict | None:
    """Returns {summary, card} or None when the model output is not usable (caller then says the photo could not be assessed)."""
    d = parse_json(text)
    if not d:
        return None
    crop = d.get("crop") if isinstance(d.get("crop"), str) and not _UNSAFE.search(d["crop"]) else "unknown"
    sev = str(d.get("severity", "")).strip().lower()
    sev = sev if sev in SEVERITIES else "unknown"
    symptoms, causes = _clean(d.get("symptoms")), _clean(d.get("possible_causes"))
    summary = (
        f"IMAGE ASSESSMENT (visual only, from the farmer's photo): crop {crop.strip()[:60]}; severity {sev}; "
        f"symptoms: {'; '.join(symptoms) or 'none visible'}; possible causes: {'; '.join(causes) or 'cannot tell from the photo'}. "
        "The photo has ALREADY been received and analysed: never ask the farmer to send or describe a photo. If the crop seen differs from the farmer's crop, say that plainly and still report what is visible. "
        "Say 'from your photo' and never repeat the label IMAGE ASSESSMENT. Advise the farmer to confirm with the local KVK / agriculture officer. Do not recommend pesticides, brands or doses."
    )
    card = {
        "type": "diagnosis",
        "title": "Crop health assessment",
        "symptoms": symptoms,
        "severity": sev,
        "possible_causes": causes,
        "recommendations": RECOMMENDATIONS,
        "disclaimer": DISCLAIMER,
    }
    return {"summary": summary, "card": card}
