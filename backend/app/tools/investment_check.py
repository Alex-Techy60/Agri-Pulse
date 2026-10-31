"""Post-tool: investment signal — runs AFTER mandi + agri_inputs for the investment_advice intent.

Reads facts from those two tools (already in the orchestrator's results cache via get_cached_result),
runs the deterministic investment_rules, and returns a ToolResult whose text the LLM uses to
state the INVESTMENT SIGNAL clearly.

Contract: same as every other tool — (text: str, profile: dict) -> ToolResult, wrapped in guarded().
The get_mandi / get_agri_inputs results are cached by http.py so this tool never double-bills quota.
"""
from __future__ import annotations

import logging

from app.decision.investment_rules import estimate_input_cost, estimate_revenue, investment_signal
from app.tools import SourceUnavailable, ToolResult, guarded
from app.tools.agri_inputs import get_agri_inputs
from app.tools.mandi import get_mandi

log = logging.getLogger("tool.investment_check")


def get_investment_check(profile: dict, text: str = "") -> ToolResult:
    """Synthesise mandi price + agri input costs → ROI signal."""
    # Re-call both tools (results are cached in http.py's LRU so these are fast re-uses)
    mandi_result = get_mandi(profile, text)
    agri_result = get_agri_inputs(profile, text)

    mandi_facts = mandi_result.facts
    agri_facts = agri_result.facts

    mandi_price = None
    price_info = mandi_facts.get("price", {})
    position = mandi_facts.get("position", {})
    # Use the latest state median or best price as the reference mandi price
    if position and position.get("state_median"):
        mandi_price = float(position["state_median"])
    elif price_info and price_info.get("compared_with"):
        # No direct price in signal facts — use the state median from position
        pass

    # Try to get a price from the own_market or best_market
    own_market = mandi_facts.get("own_market", [])
    if own_market and own_market[0].get("modal"):
        mandi_price = float(own_market[0]["modal"])
    elif position and position.get("best_price"):
        mandi_price = float(position["best_price"])
    elif position and position.get("state_median"):
        mandi_price = float(position["state_median"])

    crop = agri_facts.get("crop", profile.get("crop", ""))
    crop_key = agri_facts.get("crop_key", "")
    npk = agri_facts.get("npk_kg_per_acre")
    fert_mrp = agri_facts.get("fertilizer_mrp", {})
    seed_kg = agri_facts.get("seed_kg_per_acre")
    yield_range = agri_facts.get("yield_range_qtl_per_acre")

    # Default to 1 acre if no profile area given
    area_acres = float(profile.get("area_acres") or 1.0)

    if mandi_price is None:
        return ToolResult(
            "INVESTMENT SIGNAL: INSUFFICIENT_DATA — mandi price not available. "
            "Cannot compute return on investment without a live mandi price. "
            "The fertilizer cost estimate is in AGRI INPUTS above; return estimate requires a live mandi price.",
            ok=False,
            sources=[],
        )

    input_cost = estimate_input_cost(crop_key, area_acres, npk, fert_mrp, seed_kg)
    revenue = estimate_revenue(crop, area_acres, mandi_price, yield_range or {})
    sig = investment_signal(input_cost, revenue)

    lines = [
        f"INVESTMENT SIGNAL (computed in code, {area_acres:.1f} acre): {sig['signal']}",
        f"Reason: {sig['reason']}",
        f"Mandi price used: Rs {mandi_price:.0f}/quintal (data.gov.in Agmarknet, live)",
        f"ICAR yield range: {yield_range['low']}–{yield_range['high']} qtl/acre (ICAR Package of Practices guidance)" if yield_range else "Yield range: not available",
        f"Total estimated input cost ({area_acres:.1f} acre): Rs {sig.get('total_input_cost_rs', 'N/A')} (Govt MRP + ICAR quantities)",
        f"Estimated revenue range: Rs {sig.get('revenue_low_rs', 'N/A'):,} (low yield) – Rs {sig.get('revenue_high_rs', 'N/A'):,} (high yield)",
        f"Estimated net profit range: Rs {sig.get('net_profit_low_rs', 'N/A'):,} – Rs {sig.get('net_profit_high_rs', 'N/A'):,}",
        f"ROI range: {sig.get('roi_low_pct', 'N/A')}% – {sig.get('roi_high_pct', 'N/A')}%",
        "NOTE: This is an estimate. Actual yield, market price and input cost vary. "
        "Confirm fertilizer, seed costs and soil requirements with your local KVK or agriculture officer before investing.",
        "Say the INVESTMENT SIGNAL clearly (Favourable / Marginal / Unfavourable), give the cost and profit range, "
        "and remind the farmer this is an estimate, not a guarantee.",
    ]

    return ToolResult(
        "\n".join(lines),
        ok=True,
        sources=mandi_result.sources + agri_result.sources,
        cards=[{
            "type": "investment_inputs",
            "title": f"Investment estimate — {crop} ({area_acres:.1f} acre)",
            "crop": crop,
            "fertilizer_mrp": fert_mrp,
            "npk": npk,
            "seed_kg_per_acre": seed_kg,
            "total_fert_cost_per_acre_rs": agri_facts.get("total_fert_cost_per_acre_rs"),
            "yield_range_qtl": yield_range,
            "signal": sig,
            "sources": list({s["name"] for s in mandi_result.sources + agri_result.sources}),
            "fetched_at": agri_facts.get("fetched_at", ""),
        }],
        facts={"investment": sig, "input_cost": input_cost, "revenue": revenue, "mandi_price_used": mandi_price},
    )


investment_check = guarded("investment_check")(lambda text, profile: get_investment_check(profile, text))

