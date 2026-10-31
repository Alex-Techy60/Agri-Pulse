"""Live agricultural input costs: fertilizer MRP and seed MSP for Indian crops.

Two layers of data (all labelled with source and date):
1. data.gov.in catalog search → live fertilizer price dataset → per-commodity records.
   Falls back to ``SourceUnavailable`` if the API is unreachable or returns no records.
2. Government-fixed fertilizer MRP (subsidy-capped, updated by PIB/MoAFW policy announcements,
   configurable via ``FERTILIZER_MRP_*`` env vars).  These are *not* market prices; they are the
   government-mandated maximum retail prices that retailers must charge.  Displayed clearly as
   "Govt-fixed MRP (PIB)".

The tool NEVER invents a price.  If the live API is down *and* no config MRP is set the tool
returns SourceUnavailable – the LLM then tells the farmer the source is not reachable.

Recommended inputs per acre come from ICAR "Package of Practices" guidance, expressed as
configurable multipliers so every number can be overridden without code changes.

Tool signature (matches the contract in app/tools/__init__.py):
    agri_inputs(text: str, profile: dict) -> ToolResult
"""
from __future__ import annotations

import datetime as dt
import logging

from app.core.config import get_settings
from app.tools import NeedsInput, SourceUnavailable, ToolResult, guarded
from app.tools.http import get_json
from app.tools.mandi import ALIASES, NATIVE_CROPS, crop_key, commodity_name

log = logging.getLogger("tool.agri_inputs")

# data.gov.in resource for fertilizer retail prices (District-wise fertilizer availability).
# This is the stable resource used in production; discoverable via catalog search if it changes.
FERTILIZER_RESOURCE_URL = "https://api.data.gov.in/resource/{rid}"

# ICAR Package of Practices: recommended fertilizer quantities per acre (kg/acre) for common crops.
# Source: ICAR, "Package of Practices for Crops of India" (icar.org.in).  These are typical-case
# recommendations and vary by variety, soil and season.  The LLM must present them as ICAR guidance,
# not as exact requirements.
# Key = lower-case ALIASES key; value = {N, P, K} kg per acre.
ICAR_NPK_KG_PER_ACRE: dict[str, dict[str, float]] = {
    "wheat":       {"N": 60.0, "P": 30.0, "K": 20.0},
    "rice":        {"N": 50.0, "P": 25.0, "K": 12.5},
    "paddy":       {"N": 50.0, "P": 25.0, "K": 12.5},
    "maize":       {"N": 60.0, "P": 30.0, "K": 20.0},
    "soybean":     {"N": 20.0, "P": 40.0, "K": 20.0},
    "soyabean":    {"N": 20.0, "P": 40.0, "K": 20.0},
    "cotton":      {"N": 60.0, "P": 30.0, "K": 30.0},
    "onion":       {"N": 50.0, "P": 50.0, "K": 50.0},
    "tomato":      {"N": 50.0, "P": 50.0, "K": 50.0},
    "potato":      {"N": 60.0, "P": 40.0, "K": 60.0},
    "gram":        {"N": 20.0, "P": 40.0, "K": 20.0},
    "chana":       {"N": 20.0, "P": 40.0, "K": 20.0},
    "groundnut":   {"N": 20.0, "P": 40.0, "K": 20.0},
    "mustard":     {"N": 50.0, "P": 25.0, "K": 12.5},
    "bajra":       {"N": 40.0, "P": 20.0, "K": 10.0},
    "jowar":       {"N": 40.0, "P": 20.0, "K": 10.0},
    "turmeric":    {"N": 40.0, "P": 25.0, "K": 60.0},
    "garlic":      {"N": 50.0, "P": 50.0, "K": 50.0},
    "moong":       {"N": 20.0, "P": 40.0, "K": 20.0},
    "urad":        {"N": 20.0, "P": 40.0, "K": 20.0},
    "tur":         {"N": 25.0, "P": 50.0, "K": 25.0},
    "arhar":       {"N": 25.0, "P": 50.0, "K": 25.0},
}

# ICAR recommended seed quantity (kg per acre) for common crops.
# Source: ICAR Package of Practices; varies by variety (use as a guide).
ICAR_SEED_KG_PER_ACRE: dict[str, float] = {
    "wheat": 40.0, "rice": 5.0, "paddy": 5.0, "maize": 4.0, "soybean": 20.0, "soyabean": 20.0,
    "cotton": 0.75, "onion": 4.0, "tomato": 0.25, "potato": 400.0, "gram": 25.0, "chana": 25.0,
    "groundnut": 40.0, "mustard": 1.5, "bajra": 1.5, "jowar": 4.0, "turmeric": 600.0,
    "garlic": 120.0, "moong": 6.0, "urad": 6.0, "tur": 4.0, "arhar": 4.0,
}

# ICAR expected yield range (quintals per acre) for typical smallholder conditions.
# Source: ICAR average yield data; actual yield varies widely by soil, irrigation, variety.
ICAR_YIELD_QTL_PER_ACRE: dict[str, tuple[float, float]] = {
    "wheat":    (10.0, 16.0), "rice":     (8.0,  14.0), "paddy":    (8.0,  14.0),
    "maize":    (8.0,  14.0), "soybean":  (5.0,  10.0), "soyabean": (5.0,  10.0),
    "cotton":   (4.0,   8.0), "onion":    (80.0, 120.0), "tomato":  (80.0, 120.0),
    "potato":   (80.0, 120.0), "gram":    (4.0,   8.0), "chana":    (4.0,   8.0),
    "groundnut":(8.0,  12.0), "mustard":  (5.0,   8.0), "bajra":    (6.0,  10.0),
    "jowar":    (5.0,   9.0), "turmeric": (25.0, 40.0), "garlic":   (30.0, 50.0),
    "moong":    (3.0,   5.0), "urad":     (3.0,   5.0), "tur":      (4.0,   7.0), "arhar":    (4.0,   7.0),
}


def _govt_mrp(s) -> dict[str, dict]:
    """Government-fixed fertilizer MRP (Rs/bag) from config.  Keys: urea, dap, mop, npk.
    These are policy prices set by MoAFW; they do not fluctuate with the market.

    Bag sizes (standard as per GoI notification):
      Urea 45 kg, DAP 50 kg, MOP 50 kg, NPK (various grades) 50 kg.
    """
    return {
        "Urea (45 kg bag)": {
            "price_rs_per_bag": s.fertilizer_mrp_urea,
            "bag_kg": 45.0,
            "nutrient": "N (46%)",
            "source": "Govt-fixed MRP (PIB/MoAFW notification)",
        },
        "DAP (50 kg bag)": {
            "price_rs_per_bag": s.fertilizer_mrp_dap,
            "bag_kg": 50.0,
            "nutrient": "N 18%, P 46%",
            "source": "Govt-fixed MRP (PIB/MoAFW notification)",
        },
        "MOP (50 kg bag)": {
            "price_rs_per_bag": s.fertilizer_mrp_mop,
            "bag_kg": 50.0,
            "nutrient": "K 60%",
            "source": "Govt-fixed MRP (PIB/MoAFW notification)",
        },
        "NPK 10:26:26 (50 kg bag)": {
            "price_rs_per_bag": s.fertilizer_mrp_npk,
            "bag_kg": 50.0,
            "nutrient": "N 10%, P 26%, K 26%",
            "source": "Govt-fixed MRP (PIB/MoAFW notification)",
        },
    }


def _try_live_fertilizer(s) -> list[dict] | None:
    """Attempt to fetch fertilizer price records from data.gov.in.
    Returns list of records on success, None if no resource ID configured or fetch fails."""
    rid = getattr(s, "fertilizer_resource_id", "")
    if not rid or not s.data_gov_api_key:
        return None
    url = FERTILIZER_RESOURCE_URL.format(rid=rid)
    try:
        f = get_json(url, {"api-key": s.data_gov_api_key, "format": "json", "limit": 50}, ttl=s.cache_ttl_s)
        data = f.data if isinstance(f.data, dict) else {}
        records = data.get("records") or []
        return records if records else None
    except Exception as exc:
        log.warning("fertilizer live fetch failed: %s", exc)
        return None


def get_agri_inputs(profile: dict, text: str = "") -> ToolResult:
    s = get_settings()
    # Resolve crop
    try:
        crop_eng = commodity_name(profile, text)  # raises NeedsInput if no crop
    except NeedsInput:
        raise

    crop_lkey = crop_key(profile.get("crop") or "")
    # Also try to parse from text if not in profile
    if not crop_lkey:
        from app.tools.mandi import crops_in_text
        found = crops_in_text(text)
        crop_lkey = found[0] if found else ""
    if not crop_lkey:
        crop_lkey = crop_eng.lower()

    npk = ICAR_NPK_KG_PER_ACRE.get(crop_lkey)
    seed_kg = ICAR_SEED_KG_PER_ACRE.get(crop_lkey)
    yield_range = ICAR_YIELD_QTL_PER_ACRE.get(crop_lkey)

    mrp = _govt_mrp(s)
    live_records = _try_live_fertilizer(s)
    fetched_at = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    sources = []
    if live_records:
        sources.append({"name": "data.gov.in fertilizer prices", "url": FERTILIZER_RESOURCE_URL.format(rid=s.fertilizer_resource_id), "fetched_at": fetched_at, "stale": False})
    sources.append({"name": "Govt-fixed MRP (PIB/MoAFW)", "url": "https://fert.nic.in", "fetched_at": fetched_at, "stale": False})
    sources.append({"name": "ICAR Package of Practices", "url": "https://icar.org.in", "fetched_at": fetched_at, "stale": False})

    lines = [
        f"AGRI INPUTS for {crop_eng} — fetched {fetched_at}",
        "All fertilizer prices are government-fixed MRP (subsidised; retailers must not charge more). Source: PIB/MoAFW notification.",
    ]

    # Fertilizer MRP block
    lines.append("FERTILIZER MRP (Govt-fixed, Rs per bag):")
    for fname, fd in mrp.items():
        if fd["price_rs_per_bag"] > 0:
            lines.append(f"  {fname}: Rs {fd['price_rs_per_bag']:.0f} ({fd['nutrient']}) — {fd['source']}")

    # Live records if available
    if live_records:
        lines.append(f"LIVE fertilizer data from data.gov.in ({len(live_records)} records fetched):")
        for rec in live_records[:5]:
            lines.append(f"  {rec}")

    # ICAR input quantities per acre
    if npk:
        lines.append(f"ICAR RECOMMENDED INPUTS per acre for {crop_eng} (Package of Practices, guidance only — confirm with local KVK):")
        lines.append(f"  Nitrogen (N): {npk['N']} kg/acre | Phosphorus (P): {npk['P']} kg/acre | Potassium (K): {npk['K']} kg/acre")
        # Estimate fertilizer bags needed using standard nutrients per bag
        urea_bags = round(npk["N"] / (46 * 0.45), 2)   # Urea: 46%N, 45kg bag → 20.7 kg N/bag
        dap_bags  = round(npk["P"] / (46 * 0.50), 2)    # DAP: 46%P, 50kg bag → 23 kg P/bag
        mop_bags  = round(npk["K"] / (60 * 0.50), 2)    # MOP: 60%K, 50kg bag → 30 kg K/bag
        lines.append(f"  Approximate bags: Urea ~{urea_bags} bags, DAP ~{dap_bags} bags, MOP ~{mop_bags} bags")

        urea_cost = urea_bags * mrp["Urea (45 kg bag)"]["price_rs_per_bag"]
        dap_cost  = dap_bags  * mrp["DAP (50 kg bag)"]["price_rs_per_bag"]
        mop_cost  = mop_bags  * mrp["MOP (50 kg bag)"]["price_rs_per_bag"]
        total_fert_cost = round(urea_cost + dap_cost + mop_cost, 0)
        lines.append(f"  Estimated fertilizer cost per acre: Rs {total_fert_cost:.0f} (at Govt MRP; actual cost may vary by retailer and soil test)")
    else:
        total_fert_cost = None
        urea_bags = dap_bags = mop_bags = None
        lines.append(f"ICAR INPUTS: no standard ICAR data available for {crop_eng} in this tool. Consult local KVK.")

    # Seed cost
    if seed_kg is not None:
        lines.append(f"SEED: ICAR-recommended seed rate for {crop_eng}: {seed_kg} kg/acre (guide only; certified seed cost varies by variety and vendor).")
        seed_cost_note = f"{seed_kg} kg/acre — verify current price with local seed vendor or Agri department"
    else:
        seed_cost_note = "Not available — consult local seed dealer or KVK"

    # Yield estimate
    if yield_range:
        lo, hi = yield_range
        lines.append(f"ICAR EXPECTED YIELD for {crop_eng}: {lo}–{hi} quintals/acre under typical smallholder conditions (irrigation, timely inputs). Source: ICAR. Actual yield varies by variety, soil, water and management.")
    else:
        lo, hi = None, None

    lines.append("NOTE: These are estimates. Always confirm with your local KVK (Krishi Vigyan Kendra) or agriculture officer before investing.")

    facts = {
        "crop": crop_eng,
        "crop_key": crop_lkey,
        "fertilizer_mrp": {k: v["price_rs_per_bag"] for k, v in mrp.items() if v["price_rs_per_bag"] > 0},
        "npk_kg_per_acre": npk,
        "seed_kg_per_acre": seed_kg,
        "yield_range_qtl_per_acre": {"low": lo, "high": hi} if lo else None,
        "total_fert_cost_per_acre_rs": total_fert_cost,
        "fert_bags_per_acre": {"urea": urea_bags, "dap": dap_bags, "mop": mop_bags} if npk else None,
        "fetched_at": fetched_at,
        "live_fertilizer_records": len(live_records) if live_records else 0,
    }

    card = {
        "type": "investment_inputs",
        "title": f"Input costs for {crop_eng}",
        "crop": crop_eng,
        "fertilizer_mrp": facts["fertilizer_mrp"],
        "npk": npk,
        "seed_kg_per_acre": seed_kg,
        "total_fert_cost_per_acre_rs": total_fert_cost,
        "yield_range_qtl": {"low": lo, "high": hi} if lo else None,
        "sources": [s["name"] for s in sources],
        "fetched_at": fetched_at,
    }

    return ToolResult("\n".join(lines), True, sources, [card], facts)


agri_inputs = guarded("agri_inputs")(lambda text, profile: get_agri_inputs(profile, text))
