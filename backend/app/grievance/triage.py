from __future__ import annotations
import re
from datetime import datetime, timezone
from app.grievance.models import FarmCrisisIn, FarmCrisisReport, CrisisCategory, UrgencyLevel
from app.llm.client import get_llm

CATEGORY_ROUTING: dict[CrisisCategory, dict] = {
    "TRANSFORMER_PUMP_FAILURE": {
        "urgency": "P1",
        "sla_hours": 24,
        "department": "State Electricity Distribution Co. (MSEDCL / DISCOM)"
    },
    "CROP_LOSS_HAIL": {
        "urgency": "P1",
        "sla_hours": 48,
        "department": "Krishi Vibhag (Agriculture Dept) & PMFBY Joint Survey Cell"
    },
    "PEST_OUTBREAK": {
        "urgency": "P2",
        "sla_hours": 48,
        "department": "Krishi Vigyan Kendra (KVK) Plant Protection Wing"
    },
    "CANAL_WATER_DISPUTE": {
        "urgency": "P2",
        "sla_hours": 72,
        "department": "Water Resources & Irrigation Sub-Division"
    },
    "SPURIOUS_FERTILIZER_SEED": {
        "urgency": "P2",
        "sla_hours": 72,
        "department": "District Quality Control Inspector (Agri Dept)"
    },
    "SPURIOUS_SEEDS_PESTICIDE": {
        "urgency": "P1",
        "sla_hours": 24,
        "department": "District Quality Control Inspector & Flying Squad (Agri Dept)"
    },
    "ANIMAL_CROP_RAID": {
        "urgency": "P2",
        "sla_hours": 36,
        "department": "Divisional Forest Officer & Wildlife Damage Assessment Wing"
    },
    "MANDI_PAYMENT_ISSUE": {
        "urgency": "P3",
        "sla_hours": 120,
        "department": "APMC Mandi Secretary & Market Vigilance Committee"
    },
    "OTHER": {
        "urgency": "P3",
        "sla_hours": 72,
        "department": "Taluka Krishi Adhikari Citizen Redressal Cell"
    }
}

TRIAGE_PROMPT = (
    "Classify incoming farmer crisis reports into priority tiers:\n"
    "- P1 (Emergency / 24-72h SLA): Hailstorm damage, flash flood crop loss, canal tail blockage, spurious fertilizer.\n"
    "- P2 (Urgent / 48h SLA): Distribution transformer burnout, agricultural pump grid failure, wild animal raids.\n"
    "- P3 (Standard / 72h SLA): General scheme delay, local advisory queries.\n\n"
    'Output JSON: {"urgency": "P1"|"P2"|"P3", "department": "<dept_name>", "sla_hours": <int>}'
)


def mask_phone(phone: str) -> str:
    digits = re.sub(r"\D", "", phone or "")
    if len(digits) >= 4:
        return f"••••{digits[-4:]}"
    return "••••"

def translate_to_english_for_officers(text: str, source_lang: str) -> str:
    """Translates the farmer's complaint from Hindi/Marathi into plain English for officers, keeping all names and dates exact."""
    if source_lang == "en" or not text.strip():
        return text
    try:
        llm = get_llm()
        system_prompt = (
            "You translate Indian farmers' civic and crisis grievances for state agricultural officers. "
            "Translate the text into plain English. "
            "Keep all village names, person names, crop names, numbers, and dates exact. "
            "Do not add, soften or summarize. Reply with the English translation only."
        )
        data, res = llm.chat([
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": text}
        ], fast=True, temperature=0, max_tokens=300)
        return (data or text).strip()
    except Exception:
        return f"[{source_lang.upper()} Report] {text}"

def triage_crisis(inp: FarmCrisisIn, report_id: str) -> FarmCrisisReport:
    routing = dict(CATEGORY_ROUTING.get(inp.category, {
        "urgency": "P2",
        "sla_hours": 72,
        "department": "District Agriculture Officer (Krishi Vibhag)"
    }))
    
    # Auto-escalate if description mentions critical emergency keywords
    urgency: UrgencyLevel = routing["urgency"]
    if re.search(r"\b(fire|burst|burnt|shock|urgent|starv|suicide|flood|drown)\b|आग|विज|जळाला|तातडी|बुडाले", inp.description, re.I):
        urgency = "P1"
        routing["sla_hours"] = min(routing["sla_hours"], 24)

    english = translate_to_english_for_officers(inp.description, inp.language)
    now_iso = datetime.now(timezone.utc).isoformat()

    return FarmCrisisReport(
        id=report_id,
        farmer_name=inp.farmer_name.strip(),
        farmer_phone_masked=mask_phone(inp.farmer_phone),
        place=inp.place.strip(),
        district=inp.district.strip(),
        state=inp.state.strip(),
        category=inp.category,
        urgency=urgency,
        description=inp.description.strip(),
        english_translation=english,
        language=inp.language,
        assigned_department=routing["department"],
        sla_deadline_hours=routing["sla_hours"],
        sla_breached=False,
        status="OPEN",
        created_at=now_iso,
        lat=inp.lat or 20.0059,
        lon=inp.lon or 73.7997
    )
