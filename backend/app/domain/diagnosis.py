"""Crop photo -> structured, safe assessment. The vision model describes; this code decides what is shown.

Only symptoms / severity / possible causes come from the model, and each is sanitised: no brands, no application
rates, bounded length. Recommendations and disclaimer are fixed safe text, never model output.
"""
from __future__ import annotations

import re

from app.llm.client import parse_json

VISION_PROMPT = (
    "You are looking at a farm / crop photo. Reply with JSON only, no other text:\n"
    '{"crop": "<crop or plant visible, or unknown>", "symptoms": ["<specific visible symptom>", ...], '
    '"severity": "mild | moderate | severe | none", "possible_causes": ["<factual possible cause>", ...]}\n'
    "Rules: describe only what is visible (colour changes, spots, wilting, holes, pests). At most 5 items per list. "
    "Use words, not numbers or percentages. Do NOT recommend pesticides, brands, doses or treatments. "
    "If the photo is not a plant or crop, set crop to unknown and symptoms to []."
)

BRAND_PATTERN = r"\b(Roundup|Bayer|Syngenta|BASF|Corteva|Tata\s+Rallis|UPL|Dhanuka|FMC)\b"
RATE_PATTERN = r"[\d.]+\s*(?:ml|g|gm|kg|l|litre|liter)s?\s*(?:per|/)\s*(?:acre|hectare|ha|bigha|litre|liter|l)\b"
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
