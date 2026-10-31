"""Tests for agri_inputs tool and investment_rules decision module."""
from __future__ import annotations

import app.tools.agri_inputs as ai_mod
from app.core.config import Settings
from app.tools import NeedsInput, ToolResult
from app.tools.http import Fetched


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def fake_get_json(url, params=None, ttl=None, timeout=None):
    """Never called in most tests — agri_inputs doesn't need network if fertilizer_resource_id is empty."""
    return Fetched({}, url, "2026-11-01T10:00:00Z", False, 0)


def install_settings(**kw):
    base = dict(data_gov_api_key="k", fertilizer_resource_id="")
    base.update(kw)
    ai_mod.get_settings = lambda: Settings(**base)


# ---------------------------------------------------------------------------
# agri_inputs tool
# ---------------------------------------------------------------------------

def test_agri_inputs_onion_returns_ok():
    install_settings()
    result = ai_mod.agri_inputs("", {"place": "Nashik, Maharashtra", "crop": "Onion"})
    assert result.ok
    assert "AGRI INPUTS for Onion" in result.text
    assert "FERTILIZER MRP" in result.text
    assert "ICAR RECOMMENDED INPUTS" in result.text
    assert "ICAR EXPECTED YIELD" in result.text
    assert result.cards[0]["type"] == "investment_inputs"


def test_agri_inputs_wheat_cost_estimate():
    install_settings()
    result = ai_mod.agri_inputs("", {"place": "Pune", "crop": "Wheat"})
    assert result.ok
    assert "Wheat" in result.text
    # Fertilizer cost per acre should be present and positive
    fert_cost = result.facts.get("total_fert_cost_per_acre_rs")
    assert fert_cost is not None and fert_cost > 0


def test_agri_inputs_raises_needs_input_without_crop():
    install_settings()
    import pytest
    with pytest.raises(NeedsInput) as exc:
        ai_mod.agri_inputs("", {"place": "Nashik"})
    assert exc.value.field == "crop"


def test_agri_inputs_card_has_required_fields():
    install_settings()
    result = ai_mod.agri_inputs("", {"place": "Nashik", "crop": "Tomato"})
    card = result.cards[0]
    assert card["type"] == "investment_inputs"
    assert "crop" in card
    assert "fertilizer_mrp" in card
    assert "fetched_at" in card


def test_agri_inputs_sources_include_icar_and_mrp():
    install_settings()
    result = ai_mod.agri_inputs("", {"place": "Nashik", "crop": "Soybean"})
    source_names = [s["name"] for s in result.sources]
    assert any("PIB" in n or "MoAFW" in n for n in source_names)
    assert any("ICAR" in n for n in source_names)


def test_agri_inputs_facts_structure():
    install_settings()
    result = ai_mod.agri_inputs("", {"place": "Nashik", "crop": "Potato"})
    f = result.facts
    assert f["crop"] == "Potato"
    assert f["npk_kg_per_acre"] is not None
    assert f["yield_range_qtl_per_acre"] is not None
    assert f["yield_range_qtl_per_acre"]["low"] > 0
    assert f["yield_range_qtl_per_acre"]["high"] > f["yield_range_qtl_per_acre"]["low"]


def test_agri_inputs_uses_configurable_mrp():
    """If env overrides MRP, the tool uses the overridden value."""
    install_settings(fertilizer_mrp_urea=300.0)
    result = ai_mod.agri_inputs("", {"place": "Nashik", "crop": "Wheat"})
    # The text should mention Rs 300 (not default Rs 242)
    assert "300" in result.text


def test_agri_inputs_crop_from_text():
    install_settings()
    # No crop in profile but 'onion' in text
    result = ai_mod.agri_inputs("How much to grow onion?", {"place": "Nashik"})
    assert result.ok
    assert "Onion" in result.text


# ---------------------------------------------------------------------------
# investment_rules module
# ---------------------------------------------------------------------------

from app.decision.investment_rules import estimate_input_cost, estimate_revenue, investment_signal


def test_estimate_input_cost_onion():
    fert_mrp = {"Urea (45 kg bag)": 242.0, "DAP (50 kg bag)": 1350.0, "MOP (50 kg bag)": 1700.0}
    npk = {"N": 50.0, "P": 50.0, "K": 50.0}
    result = estimate_input_cost("onion", 1.0, npk, fert_mrp, seed_kg_per_acre=4.0)
    assert result["area_acres"] == 1.0
    assert result["fertilizer_cost_rs"] is not None
    assert result["fertilizer_cost_rs"] > 0
    assert result["total_input_cost_rs"] is not None


def test_estimate_input_cost_no_npk():
    result = estimate_input_cost("unknowncrop", 1.0, None, {}, None)
    assert result["fertilizer_cost_rs"] is None
    assert result["total_input_cost_rs"] is None
    assert any("not available" in n for n in result["notes"])


def test_estimate_revenue():
    result = estimate_revenue("Onion", 1.0, 2500.0, {"low": 80.0, "high": 120.0})
    assert result["revenue_low_rs"] == 80.0 * 1.0 * 2500.0
    assert result["revenue_high_rs"] == 120.0 * 1.0 * 2500.0
    assert result["yield_low_qtl"] == 80.0
    assert result["yield_high_qtl"] == 120.0


def test_investment_signal_favourable():
    # Low cost, high revenue → FAVOURABLE
    input_cost = {"total_input_cost_rs": 5000.0}
    revenue = {"revenue_low_rs": 10000.0, "revenue_high_rs": 15000.0, "mandi_price_rs_per_qtl": 2500.0}
    sig = investment_signal(input_cost, revenue)
    assert sig["signal"] == "FAVOURABLE"
    assert sig["net_profit_low_rs"] > 0
    assert sig["roi_low_pct"] >= 20.0


def test_investment_signal_unfavourable():
    # High cost, low revenue → UNFAVOURABLE
    input_cost = {"total_input_cost_rs": 50000.0}
    revenue = {"revenue_low_rs": 5000.0, "revenue_high_rs": 8000.0, "mandi_price_rs_per_qtl": 500.0}
    sig = investment_signal(input_cost, revenue)
    assert sig["signal"] == "UNFAVOURABLE"
    assert sig["net_profit_low_rs"] < 0


def test_investment_signal_marginal():
    # Slightly above break-even but below 20 %
    input_cost = {"total_input_cost_rs": 10000.0}
    revenue = {"revenue_low_rs": 10500.0, "revenue_high_rs": 12000.0, "mandi_price_rs_per_qtl": 1500.0}
    sig = investment_signal(input_cost, revenue)
    assert sig["signal"] == "MARGINAL"


def test_investment_signal_insufficient_data():
    input_cost = {"total_input_cost_rs": None}
    revenue = {"revenue_low_rs": 10000.0, "revenue_high_rs": 15000.0, "mandi_price_rs_per_qtl": 2500.0}
    sig = investment_signal(input_cost, revenue)
    assert sig["signal"] == "INSUFFICIENT_DATA"


def test_estimate_input_cost_with_seed_price():
    fert_mrp = {"Urea (45 kg bag)": 242.0, "DAP (50 kg bag)": 1350.0, "MOP (50 kg bag)": 1700.0}
    npk = {"N": 60.0, "P": 30.0, "K": 20.0}
    result = estimate_input_cost("wheat", 2.0, npk, fert_mrp, seed_kg_per_acre=40.0, seed_price_rs_per_kg=50.0)
    assert result["seed_cost_rs"] == 40.0 * 2.0 * 50.0
    assert result["total_input_cost_rs"] == result["fertilizer_cost_rs"] + result["seed_cost_rs"]


def test_investment_full_chain_onion():
    """Integration: full chain from agri_inputs facts → investment_rules."""
    install_settings()
    result = ai_mod.agri_inputs("", {"place": "Nashik", "crop": "Onion"})
    assert result.ok
    f = result.facts
    fert_mrp = f["fertilizer_mrp"]
    # Use lowercase keys as returned by tool
    # fert_mrp keys are like "Urea (45 kg bag)" etc
    input_cost = estimate_input_cost(
        f["crop_key"], 1.0,
        f["npk_kg_per_acre"],
        fert_mrp,
        f["seed_kg_per_acre"],
    )
    revenue = estimate_revenue(
        f["crop"], 1.0,
        mandi_price_rs_per_qtl=2500.0,
        yield_range_qtl_per_acre=f["yield_range_qtl_per_acre"],
    )
    sig = investment_signal(input_cost, revenue)
    assert sig["signal"] in ("FAVOURABLE", "MARGINAL", "UNFAVOURABLE")
    assert sig["net_profit_low_rs"] is not None

