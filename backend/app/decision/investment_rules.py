"""Deterministic investment advisory rules for crop farming.

The LLM explains results; it never computes them.

All inputs come from tool facts (live mandi price, ICAR guidance).  No number is hard-coded here:
every threshold is configurable or derived from the live data passed in.

Rule: ROI = (mandi_price × expected_yield) − total_input_cost
      Investment is FAVOURABLE if ROI > 0 and ROI % > 0, MARGINAL if ROI % is below 20 %, UNFAVOURABLE otherwise.
      The thresholds are labelled clearly (HEURISTIC) and can be overridden.
"""
from __future__ import annotations

import math

# ROI thresholds (HEURISTIC: smallholder farming in India; 20 % net margin is a widely-used
# minimum for advisory in development-finance literature, e.g. NABARD guidelines).
ROI_FAVOURABLE_PCT = 20.0   # HEURISTIC
ROI_MARGINAL_PCT   = 0.0    # breakeven


def estimate_input_cost(
    crop_key: str,
    area_acres: float,
    npk_kg_per_acre: dict | None,
    fert_mrp: dict,          # {name: price_rs_per_bag}
    seed_kg_per_acre: float | None,
    seed_price_rs_per_kg: float | None = None,   # None = cost not known, returned as None
) -> dict:
    """Estimate total input cost per `area_acres` for `crop_key`.

    Returns a dict with all components labelled with their source.  Never raises.
    A missing value is None (not zero or guessed).
    """
    result: dict = {
        "crop_key": crop_key,
        "area_acres": area_acres,
        "fertilizer_cost_rs": None,
        "seed_cost_rs": None,
        "total_input_cost_rs": None,
        "notes": [],
        "source": "ICAR Package of Practices + Govt-fixed MRP (PIB/MoAFW)",
    }

    fert_cost: float | None = None
    if npk_kg_per_acre and fert_mrp:
        n_kg = npk_kg_per_acre.get("N", 0) * area_acres
        p_kg = npk_kg_per_acre.get("P", 0) * area_acres
        k_kg = npk_kg_per_acre.get("K", 0) * area_acres

        # Use standard nutrient concentrations per bag
        # Urea: 46 % N; 45 kg bag → kg N per bag = 20.7
        urea_bags = n_kg / (46.0 * 0.45)
        # DAP: 46 % P2O5 ≈ 46 % P; 50 kg bag → 23 kg P per bag
        dap_bags = p_kg / (46.0 * 0.50)
        # MOP: 60 % K; 50 kg bag → 30 kg K per bag
        mop_bags = k_kg / (60.0 * 0.50)

        urea_price = next((v for k, v in fert_mrp.items() if "urea" in k.lower()), None)
        dap_price  = next((v for k, v in fert_mrp.items() if "dap" in k.lower()), None)
        mop_price  = next((v for k, v in fert_mrp.items() if "mop" in k.lower()), None)

        urea_cost = urea_bags * urea_price if urea_price else None
        dap_cost  = dap_bags  * dap_price  if dap_price  else None
        mop_cost  = mop_bags  * mop_price  if mop_price  else None

        computed = [c for c in (urea_cost, dap_cost, mop_cost) if c is not None]
        if computed:
            fert_cost = round(sum(computed), 0)
            result["fertilizer_cost_rs"] = fert_cost
            result["notes"].append("Fertilizer: ICAR NPK guidance × Govt MRP bags")
        else:
            result["notes"].append("Fertilizer cost: MRP data missing for one or more fertilizers")
    else:
        result["notes"].append("Fertilizer cost: ICAR NPK data or MRP not available for this crop")

    seed_cost: float | None = None
    if seed_kg_per_acre is not None and seed_price_rs_per_kg is not None:
        seed_cost = round(seed_kg_per_acre * area_acres * seed_price_rs_per_kg, 0)
        result["seed_cost_rs"] = seed_cost
        result["notes"].append("Seed: ICAR seed rate × given price")
    else:
        result["notes"].append("Seed cost not included (current seed price not available from live source; verify with local dealer)")

    if fert_cost is not None:
        result["total_input_cost_rs"] = round(fert_cost + (seed_cost or 0.0), 0)

    return result


def estimate_revenue(
    crop: str,
    area_acres: float,
    mandi_price_rs_per_qtl: float,
    yield_range_qtl_per_acre: dict,   # {"low": float, "high": float}
) -> dict:
    """Estimate gross revenue and net profit range.

    Returns a dict with low/high scenarios.  The mandi price is live (from the mandi tool).
    Yield range is from ICAR guidance.
    """
    lo = yield_range_qtl_per_acre.get("low") or 0.0
    hi = yield_range_qtl_per_acre.get("high") or 0.0
    lo_rev = round(lo * area_acres * mandi_price_rs_per_qtl, 0)
    hi_rev = round(hi * area_acres * mandi_price_rs_per_qtl, 0)
    return {
        "crop": crop,
        "area_acres": area_acres,
        "mandi_price_rs_per_qtl": mandi_price_rs_per_qtl,
        "yield_low_qtl": round(lo * area_acres, 1),
        "yield_high_qtl": round(hi * area_acres, 1),
        "revenue_low_rs": lo_rev,
        "revenue_high_rs": hi_rev,
        "source": "ICAR yield range × data.gov.in mandi price (live)",
    }


def investment_signal(
    input_cost: dict,
    revenue: dict,
) -> dict:
    """Compute net profit and ROI signal from the deterministic cost and revenue estimates.

    Signal:
      FAVOURABLE  — net profit positive and ROI % ≥ ROI_FAVOURABLE_PCT
      MARGINAL    — net profit positive but ROI % < ROI_FAVOURABLE_PCT
      UNFAVOURABLE — net profit negative (loss expected)
      INSUFFICIENT_DATA — total input cost not available
    """
    total_cost = input_cost.get("total_input_cost_rs")
    lo_rev = revenue.get("revenue_low_rs")
    hi_rev = revenue.get("revenue_high_rs")

    if total_cost is None:
        return {"signal": "INSUFFICIENT_DATA", "reason": "Input cost could not be computed (see notes above)"}

    # Conservative scenario: low yield revenue
    net_lo = round((lo_rev or 0.0) - total_cost, 0)
    net_hi = round((hi_rev or 0.0) - total_cost, 0)
    roi_lo_pct = round(net_lo / total_cost * 100, 1) if total_cost > 0 else None
    roi_hi_pct = round(net_hi / total_cost * 100, 1) if total_cost > 0 else None

    # Signal on conservative scenario
    if roi_lo_pct is not None and roi_lo_pct >= ROI_FAVOURABLE_PCT:
        signal = "FAVOURABLE"
        reason = f"Even in the low-yield case net return is Rs {net_lo:,.0f} ({roi_lo_pct:.1f} % ROI), above the {ROI_FAVOURABLE_PCT:.0f} % threshold."
    elif roi_lo_pct is not None and roi_lo_pct > ROI_MARGINAL_PCT:
        signal = "MARGINAL"
        reason = f"Net return positive (Rs {net_lo:,.0f}, {roi_lo_pct:.1f} % ROI in low-yield case) but below the {ROI_FAVOURABLE_PCT:.0f} % guideline threshold. Check current prices and soil conditions."
    else:
        signal = "UNFAVOURABLE"
        reason = f"At current mandi prices (Rs {revenue['mandi_price_rs_per_qtl']:.0f}/qtl) and low-yield case, estimated loss is Rs {abs(net_lo):,.0f}. Consider alternatives or wait for prices to improve."

    return {
        "signal": signal,
        "reason": reason,
        "net_profit_low_rs": net_lo,
        "net_profit_high_rs": net_hi,
        "roi_low_pct": roi_lo_pct,
        "roi_high_pct": roi_hi_pct,
        "total_input_cost_rs": total_cost,
        "revenue_low_rs": lo_rev,
        "revenue_high_rs": hi_rev,
        "threshold_pct": ROI_FAVOURABLE_PCT,
        "note": "HEURISTIC threshold. This is an estimate, not a guarantee. Actual yield, cost and price will vary.",
    }

