import pytest
from app.explainer.quote_checker import verify_quote
from app.explainer.models import SchemeNoticeIn
from app.explainer.engine import explain_scheme_document, list_available_schemes

def test_quote_verification():
    doc = "Under the scheme, an amount of Rs. 6,000/- per year is transferred directly into the bank accounts."
    assert verify_quote("Rs. 6,000/- per year is transferred directly", doc) is True
    # Invented quote must fail
    assert verify_quote("Farmers will receive a free tractor worth 5 lakh", doc) is False

def test_explain_pm_kisan():
    schemes = list_available_schemes()
    assert any(s["id"] == "pm_kisan" for s in schemes)
    
    inp = SchemeNoticeIn(document_id="pm_kisan", language="hi", farmer_profile={"land_acres": 2.5, "crop": "Onion"})
    res = explain_scheme_document(inp)
    
    assert res.scheme_name == "Pradhan Mantri Kisan Samman Nidhi (PM-KISAN)"
    assert res.quotes_verified_count > 0
    assert res.unverified_quotes_dropped == 0
    assert res.integrity_digest.startswith("KM-SCHEME-")
    assert len(res.rights) > 0
    assert any("6,000" in r.text or "6,000" in r.quote for r in res.rights)
