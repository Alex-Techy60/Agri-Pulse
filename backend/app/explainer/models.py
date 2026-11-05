from __future__ import annotations
from pydantic import BaseModel, Field
from typing import Literal

class ExplainerItem(BaseModel):
    id: str
    text: str
    quote: str
    verified: bool = True

class EligibilityCondition(BaseModel):
    condition: str
    met: Literal["yes", "no", "unknown"] = "unknown"
    reason: str
    quote: str
    verified: bool = True

class SchemeNoticeIn(BaseModel):
    document_id: str | None = None
    text: str | None = Field(None, max_length=50000)
    url: str | None = None
    language: str = "hi"
    farmer_profile: dict = Field(default_factory=dict) # {place, crop, land_acres, category}

class SchemeExplainerResult(BaseModel):
    title: str
    scheme_name: str
    issuing_authority: str
    summary: str
    rights: list[ExplainerItem]
    eligibility: list[EligibilityCondition]
    benefits: list[ExplainerItem]
    deadlines: list[ExplainerItem]
    documents_required: list[str]
    quotes_verified_count: int
    unverified_quotes_dropped: int
    voice_script: str
    integrity_digest: str
