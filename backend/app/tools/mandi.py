"""Live mandi (wholesale market) prices from data.gov.in / Agmarknet, plus a sell/hold signal.

Needs a free key: DATA_GOV_API_KEY (https://data.gov.in -> register -> My Account -> API key).
Without it the tool returns an explicit "source unavailable" result; it NEVER fills in prices.

Schema note: the exact field/filter spelling of the data.gov.in resource could not be confirmed when this
was written, so records are key-normalised (lower-case) and filters are tried as `state`/`commodity`/`arrival_date`
and then `State`/`Commodity`/`Arrival_Date`. Run `make check-live` once with your key to confirm.
"""
from __future__ import annotations

import re

from app.core.config import get_settings
from app.decision.price_rules import build_series, clean_rows, cross_check, market_position, norm_name, signal
from app.tools import NeedsInput, SourceUnavailable, ToolResult, guarded
from app.tools.http import get_json
from app.tools.location import resolve_location
from app.tools.weather import get_weather

API = "https://api.data.gov.in/resource/{rid}"
PAGE, MAX_PAGES = 500, 4  # per-call limit and a cap on pages: a state-level query is far below 2000 rows

# UI/common crop name -> Agmarknet commodity name. EVERY name below was checked against the real data.gov.in file of
# 30 Oct 2026 (all exist; 'Paddy(Dhan)(Common)' did not and is now 'Paddy(Common)'). Unknown crops pass through Title-Cased.
# Sugarcane is absent on purpose: the dataset has no sugarcane commodity.
ALIASES = {
    "tomato": "Tomato", "onion": "Onion", "potato": "Potato", "wheat": "Wheat", "maize": "Maize", "rice": "Rice",
    "paddy": "Paddy(Common)", "soybean": "Soyabean", "soyabean": "Soyabean", "cotton": "Cotton",
    "groundnut": "Groundnut", "gram": "Bengal Gram(Gram)(Whole)", "chana": "Bengal Gram(Gram)(Whole)",
    "banana": "Banana", "mustard": "Mustard", "bajra": "Bajra(Pearl Millet/Cumbu)", "jowar": "Jowar(Sorghum)",
    "cabbage": "Cabbage", "cauliflower": "Cauliflower", "brinjal": "Brinjal", "garlic": "Garlic", "turmeric": "Turmeric",
    "chilli": "Green Chilli", "coriander": "Coriander(Leaves)", "moong": "Green Gram(Moong)(Whole)",
    "urad": "Black Gram(Urd Beans)(Whole)", "tur": "Red gram/Arhar/Tur(whole)", "arhar": "Red gram/Arhar/Tur(whole)",
    "apple": "Apple", "mango": "Mango(Raw-Ripe)", "lemon": "Lemon", "ginger": "Ginger(Green)",
    "pomegranate": "Pomegranate", "grapes": "Grapes",
}


# Geocoder state name (lower-case) -> the spelling used in the data.gov.in dataset. Checked against the real file of
# 30 Oct 2026 and live geocoder output. Names the dataset does not contain today (Jharkhand, Sikkim, Mizoram, Arunachal,
# Ladakh) are left alone and honestly return "no records".
STATE_ALIASES = {
    "kerala": "Keralam", "chhattisgarh": "Chattisgarh", "national capital territory of delhi": "NCT of Delhi",
    "delhi": "NCT of Delhi", "puducherry": "Pondicherry", "andaman and nicobar islands": "Andaman and Nicobar",
    "orissa": "Odisha", "uttaranchal": "Uttarakhand",
}


def agmarknet_state(name: str) -> str:
    return STATE_ALIASES.get((name or "").strip().lower(), (name or "").strip())


def commodity_name(profile: dict, text: str) -> str:
    crop = (profile.get("crop") or "").strip()
    if not crop:
        low = (text or "").lower()
        crop = next((k for k in ALIASES if re.search(rf"(?<![a-z]){re.escape(k)}(?![a-z])", low)), "")  # whole words only
    if not crop:
        raise NeedsInput("crop", "which crop the farmer grows or wants to sell")
    return ALIASES.get(crop.lower(), crop.title())


def _norm(rec: dict) -> dict:
    """Lower-case keys and undo the XML-style space escape: the data.gov.in preview shows 'Modal X0020 Price', i.e. the
    field may be named `Modal_x0020_Price` instead of `modal_price`. Accept both so prices are never silently dropped."""
    return {str(k).lower().replace("_x0020_", "_"): v for k, v in rec.items()}


def _same(a, b) -> bool:
    return " ".join(str(a).lower().split()) == " ".join(str(b).lower().split())


def _fetch_records(state: str, commodity: str, key: str, rid: str, style: str):
    """Returns (records, Fetched|None). Verified against the live API (30 Oct 2026):
    * lower-case filter names work (`filters[state]`); Title-case ones match nothing;
    * the date filter is ignored (yesterday returns the same total as today): this resource publishes only the current day;
    * the commodity filter is a LOOSE text match: 'Onion' also returns 'Onion Green', 'Potato' returns 'Sweet Potato',
      'Green Chilli' returns ginger and moong gram. So records are kept only if the commodity matches EXACTLY.
    Pages through results (the API reports `total`) so an exact match is never cut off by the page size."""
    styles = ["lower", "title"] if style == "auto" else [style]
    last = None
    for st in styles:
        names = ("state", "commodity") if st == "lower" else ("State", "Commodity")
        got: list[dict] = []
        for page in range(MAX_PAGES):
            params = {"api-key": key, "format": "json", "limit": PAGE, "offset": page * PAGE, f"filters[{names[0]}]": state, f"filters[{names[1]}]": commodity}
            f = get_json(API.format(rid=rid), params, ttl=get_settings().cache_ttl_s * 2)
            last = f
            data = f.data if isinstance(f.data, dict) else {}
            batch = [_norm(r) for r in (data.get("records") or [])]
            got += batch
            try:
                total = int(data.get("total") or 0)
            except (TypeError, ValueError):
                total = 0
            if not batch or len(got) >= total:
                break
        exact = [r for r in got if _same(r.get("commodity", ""), commodity)]
        if exact:
            return exact, last
    return [], last


def get_mandi(profile: dict, text: str = "") -> ToolResult:
    s = get_settings()
    if not s.data_gov_api_key:
        raise SourceUnavailable("DATA_GOV_API_KEY is not set (free key from data.gov.in)")
    loc = resolve_location(profile)
    if not loc["state"]:
        raise NeedsInput("state", "the state of the farm (the place could not be matched to a state)")
    commodity = commodity_name(profile, text)

    records, f = _fetch_records(agmarknet_state(loc["state"]), commodity, s.data_gov_api_key, s.mandi_resource_id, s.mandi_filter_style)
    fetched = [f] if f is not None else []
    if not fetched:
        raise SourceUnavailable("no response from data.gov.in")
    series = build_series(records)
    src = {"name": "data.gov.in Agmarknet", "url": fetched[0].url, "fetched_at": max(f.fetched_at for f in fetched), "stale": any(f.stale for f in fetched)}
    sources = [src] + ([loc["source"]] if loc.get("source") else [])
    where = f"{loc['state']}"

    if not series:
        return ToolResult(
            f"MANDI PRICES: no published records for {commodity} in {where} today "
            f"(source: data.gov.in Agmarknet). Say honestly that no price data is available; do not estimate prices.",
            True, sources, [], {"location": {k: loc[k] for k in ("name", "state", "district", "lat", "lon")}, "price": {"signal": "INSUFFICIENT_DATA", "points": 0}},
        )

    sig = signal(series)
    latest_date = series[-1]["date"]
    latest_recs = [r for r in records if _same_day(r.get("arrival_date"), latest_date)]
    dist = norm_name(loc.get("district") or loc.get("name") or "")

    def row(r):
        return {"market": r.get("market"), "district": r.get("district"), "modal": _num(r.get("modal_price")), "min": _num(r.get("min_price")), "max": _num(r.get("max_price"))}

    rows = clean_rows([row(r) for r in latest_recs if _num(r.get("modal_price"))])
    near = [r for r in rows if dist and norm_name(r["district"]) == dist][:3]
    top = sorted(rows, key=lambda r: r["modal"], reverse=True)[:3]
    position = market_position(rows, loc.get("district") or loc.get("name") or "")

    lines = [f"MANDI PRICES for {commodity} in {where} - data.gov.in Agmarknet, fetched {src['fetched_at']}" + (" [STALE]" if src["stale"] else ""), "Unit: Rs per quintal. Daily average of modal prices across reporting markets:"]
    lines += [f"{p['date']}: Rs {p['modal']:.0f} ({p['n']} markets)" for p in series]
    if sig["signal"] != "INSUFFICIENT_DATA":
        lines.append(
            f"SIGNAL (computed in code): {sig['signal']} - latest Rs {sig['latest']:.0f} on {sig['latest_date']} vs average of earlier days Rs {sig['baseline_mean']:.0f} "
            f"({sig['pct_vs_baseline']} %), trend {sig['trend_per_day']} Rs/quintal per day over {sig['points']} days"
        )
    else:
        lines.append(f"SIGNAL: INSUFFICIENT_DATA ({sig['points']} day of prices; need 3). This source publishes only the current day, so say plainly that a price trend is not available and report today's prices and the market position only.")
    district_label = loc.get("district") or loc["name"]
    if near:
        lines.append(f"MARKETS in {district_label} on {latest_date}: " + "; ".join(f"{m['market']} Rs {m['modal']:.0f}" for m in near))
    elif top:  # small town / district with no reporting mandi: say so, then show the state's markets instead
        lines.append(f"NOTE: no markets reporting {commodity} in {district_label} on {latest_date}. Tell the farmer this, and that the prices below are from other markets in {where}.")
    if position:
        line = f"MARKET POSITION (computed in code, {latest_date}): {where} median Rs {position['state_median']} across {position['markets']} markets"
        if "label" in position:
            line += f"; {district_label} median Rs {position['local_median']} ({position['pct_vs_state_median']} % vs state median) -> {position['label']}"
        lines.append(line + f"; best price Rs {position['best_price']} at {position['best_market']} ({position['best_district']}). This is today's snapshot, not a forecast.")
    if top:
        lines.append(f"HIGHEST MARKETS in {where} on {latest_date}: " + "; ".join(f"{m['market']} ({m['district']}) Rs {m['modal']:.0f}" for m in top))

    card = {"type": "prices", "title": f"{commodity} - mandi prices, {where}", "unit": "Rs/quintal", "series": series, "markets": (near + [m for m in top if m not in near])[:5], "signal": sig, "position": position}
    return ToolResult("\n".join(lines), True, sources, [card], {"location": {k: loc[k] for k in ("name", "state", "district", "lat", "lon")}, "price": sig, "commodity": commodity, "position": position})


def _num(v):
    from app.decision.price_rules import to_float

    return to_float(v)


def _same_day(raw, iso: str) -> bool:
    from app.decision.price_rules import parse_date

    d = parse_date(raw or "")
    return bool(d) and d.isoformat() == iso


def get_cross_check(profile: dict, text: str = "") -> ToolResult:
    """Combines the (cached) price signal with the (cached) weather risk. Pure rules; no new data."""
    m, w = get_mandi(profile, text), get_weather(profile)
    price, wx = m.facts.get("price", {}), w.facts.get("analysis", {})
    notes = cross_check(price, wx, m.facts.get("position"))
    decision = price.get("signal", "INSUFFICIENT_DATA")
    pos = m.facts.get("position") or {}
    if decision == "INSUFFICIENT_DATA":  # this source publishes only today's prices: say what we CAN decide on
        where = f"MARKET POSITION {pos['label']} ({pos['pct_vs_state_median']} % vs state median)" if pos.get("label") else "no local market position either"
        lines = [f"DECISION (computed in code): NO PRICE TREND (the source publishes only today's prices); {where}. Lead with today's position and the best-paying market; do not call this a sell or hold signal."]
    else:
        lines = [f"DECISION (computed in code): {decision}"]
    lines += [f"NOTE: {n}" for n in notes]
    return ToolResult("\n".join(lines), True, [], [], {"decision": decision, "notes": notes})


mandi = guarded("mandi")(lambda text, profile: get_mandi(profile, text))
cross = guarded("cross_check")(lambda text, profile: get_cross_check(profile, text))
