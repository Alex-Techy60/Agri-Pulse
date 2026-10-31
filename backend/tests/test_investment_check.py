"""Tests for investment_check post-tool (synthesis of mandi + agri_inputs → ROI signal)."""
from __future__ import annotations

import datetime as dt

import app.tools.agri_inputs as ai_mod
import app.tools.investment_check as ic_mod
import app.tools.location as location
import app.tools.mandi as mandi_mod
from app.core.config import Settings
from app.tools.http import Fetched

GEO = {"results": [{"name": "Nashik", "latitude": 19.99, "longitude": 73.78, "admin1": "Maharashtra", "admin2": "Nashik", "country_code": "IN"}]}


def mandi_records(day_price):
    out = []
    for date, prices in day_price.items():
        for i, p in enumerate(prices):
            out.append({"State": "Maharashtra", "District": "Nashik" if i == 0 else "Pune", "Market": f"M{i}", "Commodity": "Onion", "Arrival_Date": date, "Min_Price": p - 100, "Max_Price": p + 100, "Modal_Price": p})
    return out


def routes_ok(url, params):
    if "geocoding" in url:
        return GEO
    if "open-meteo" in url:
        return {}
    if "data.gov.in" in url:
        if "filters[state]" not in params and "filters[State]" not in params:
            return {"records": []}
        today = dt.date.today()
        recs = []
        for off, prices in {0: [2500] * 6, 7: [2000] * 6}.items():
            recs += mandi_records({(today - dt.timedelta(days=off)).strftime("%d/%m/%Y"): prices})
        return {"records": recs, "total": len(recs)}
    raise AssertionError(url)


def install(key="k"):
    def fake(url, params=None, ttl=None, timeout=None):
        return Fetched(routes_ok(url, params or {}), url, "2026-11-01T10:00:00Z", False, 0)
    for m in (location, mandi_mod):
        m.get_json = fake
    mandi_mod.get_settings = lambda: Settings(data_gov_api_key=key)
    ai_mod.get_settings = lambda: Settings(data_gov_api_key=key, fertilizer_resource_id="")
    # investment_check calls get_mandi and get_agri_inputs directly, so patch their get_json too
    import app.tools.investment_check as ic
    ic.get_mandi.__module__  # just ensure import is ok


def test_investment_check_returns_signal():
    install()
    result = ic_mod.investment_check("", {"place": "Nashik, Maharashtra", "crop": "Onion"})
    assert result.ok
    assert "INVESTMENT SIGNAL" in result.text
    assert result.facts.get("investment") is not None
    sig = result.facts["investment"]["signal"]
    assert sig in ("FAVOURABLE", "MARGINAL", "UNFAVOURABLE")


def test_investment_check_card_type():
    install()
    result = ic_mod.investment_check("", {"place": "Nashik, Maharashtra", "crop": "Onion"})
    assert result.ok
    assert result.cards[0]["type"] == "investment_inputs"
    assert "signal" in result.cards[0]


def test_investment_check_mandi_price_used():
    install()
    result = ic_mod.investment_check("", {"place": "Nashik, Maharashtra", "crop": "Onion"})
    assert result.facts.get("mandi_price_used") is not None
    assert result.facts["mandi_price_used"] > 0


def test_investment_check_has_cost_and_revenue():
    install()
    result = ic_mod.investment_check("", {"place": "Nashik, Maharashtra", "crop": "Onion"})
    inv = result.facts["investment"]
    assert inv["total_input_cost_rs"] is not None
    assert inv["revenue_low_rs"] is not None
    assert inv["revenue_high_rs"] is not None
    assert "Rs" in result.text and "quintal" in result.text

