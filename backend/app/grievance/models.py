from __future__ import annotations
from pydantic import BaseModel, Field, model_validator
from typing import Literal

CrisisCategory = Literal[
    "CROP_LOSS_HAIL",
    "PEST_OUTBREAK",
    "CANAL_WATER_DISPUTE",
    "TRANSFORMER_PUMP_FAILURE",
    "SPURIOUS_FERTILIZER_SEED",
    "SPURIOUS_SEEDS_PESTICIDE",
    "ANIMAL_CROP_RAID",
    "MANDI_PAYMENT_ISSUE",
    "OTHER"
]

UrgencyLevel = Literal["P1", "P2", "P3"]
ReportStatus = Literal["OPEN", "INSPECTING", "RESOLVED", "DISPUTED"]

class FarmCrisisIn(BaseModel):
    farmer_name: str = Field(..., max_length=100)
    farmer_phone: str = Field(..., max_length=20)
    place: str = Field(..., max_length=100)
    district: str = Field("Nashik", max_length=60)
    state: str = Field("Maharashtra", max_length=60)
    category: CrisisCategory
    description: str = Field(..., max_length=4000)
    language: str = "mr"
    photo_b64: str | None = None
    lat: float | None = 20.0059
    lon: float | None = 73.7997

    @model_validator(mode="before")
    @classmethod
    def _coerce_fields(cls, data: dict):
        if not isinstance(data, dict):
            return data
        d = dict(data)
        if "farmer_phone" not in d and "mobile" in d:
            d["farmer_phone"] = str(d["mobile"]).strip()
        if "place" not in d or not str(d.get("place", "")).strip():
            parts = [d.get("village"), d.get("taluka"), d.get("district")]
            non_empty = [str(p).strip() for p in parts if p and str(p).strip()]
            d["place"] = ", ".join(non_empty) if non_empty else "Nashik"
        if "photo_b64" not in d and "damage_photo_b64" in d:
            d["photo_b64"] = d["damage_photo_b64"]
        return d

class ResolutionIn(BaseModel):
    officer_name: str = Field(..., max_length=100)
    resolution_notes: str = Field(..., max_length=2000)
    proof_photo_b64: str | None = None

class FeedbackIn(BaseModel):
    confirmed: bool # True = confirmed fix, False = dispute

class FarmCrisisReport(BaseModel):
    id: str
    farmer_name: str
    farmer_phone_masked: str
    place: str
    district: str
    state: str
    category: CrisisCategory
    urgency: UrgencyLevel
    description: str
    english_translation: str
    language: str
    assigned_department: str
    sla_deadline_hours: int
    sla_deadline: str | None = None
    sla_breached: bool = False
    status: ReportStatus = "OPEN"
    created_at: str
    resolution_proof_url: str | None = None
    resolution_notes: str | None = None
    citizen_confirmed: bool | None = None
    lat: float
    lon: float

    @model_validator(mode="before")
    @classmethod
    def _compute_deadline(cls, data: dict):
        if not isinstance(data, dict):
            return data
        d = dict(data)
        if "sla_deadline" not in d or not d["sla_deadline"]:
            import datetime
            try:
                created = datetime.datetime.fromisoformat(str(d.get("created_at", "")).replace("Z", "+00:00"))
                hours = int(d.get("sla_deadline_hours", 48))
                d["sla_deadline"] = (created + datetime.timedelta(hours=hours)).isoformat()
            except Exception:
                pass
        return d
