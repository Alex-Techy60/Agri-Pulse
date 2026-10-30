"""Live mandi (wholesale market) prices from data.gov.in / Agmarknet, plus a sell/hold signal.

Needs a free key: DATA_GOV_API_KEY (https://data.gov.in -> register -> My Account -> API key).
Without it the tool returns an explicit "source unavailable" result; it NEVER fills in prices.

Schema note: the exact field/filter spelling of the data.gov.in resource could not be confirmed when this
was written, so records are key-normalised (lower-case) and filters are tried as `state`/`commodity`/`arrival_date`
and then `State`/`Commodity`/`Arrival_Date`. Run `make check-live` once with your key to confirm.
"""
from __future__ import annotations

import datetime as dt
from concurrent.futures import ThreadPoolExecutor

from app.core.config import get_settings
from app.decision.price_rules import build_series, cross_check, signal
from app.tools import NeedsInput, SourceUnavailable, ToolResult, guarded
from app.tools.http import get_json
from app.tools.location import resolve_location
from app.tools.weather import get_weather

API = "https://api.data.gov.in/resource/{rid}"

# UI/common crop name -> Agmarknet commodity name. VERIFY with `make check-live`; unknown crops are passed through Title-Cased.
ALIASES = {
    "tomato": "Tomato", "onion": "Onion", "potato": "Potato", "wheat": "Wheat", "maize": "Maize", "rice": "Rice",
    "paddy": "Paddy(Dhan)(Common)", "soybean": "Soyabean", "soyabean": "Soyabean", "cotton": "Cotton",
    "groundnut": "Groundnut", "gram": "Bengal Gram(Gram)(Whole)", "chana": "Bengal Gram(Gram)(Whole)",
    "banana": "Banana", "mustard": "Mustard", "bajra": "Bajra(Pearl Millet/Cumbu)", "jowar": "Jowar(Sorghum)",
    "cabbage": "Cabbage", "cauliflower": "Cauliflower", "brinjal": "Brinjal", "garlic": "Garlic", "turmeric": "Turmeric",
}


def commodity_name(profile: dict, text: str) -> str:
    crop = (profile.get("crop") or "").strip()
    if not crop:
        low = (text or "").lower()
        crop = next((k for k in ALIASES if k in low), "")
    if not crop:
        raise NeedsInput("crop", "which crop the farmer grows or wants to sell")
    return ALIASES.get(crop.lower(), crop.title())


def _norm(rec: dict) -> dict:
    return {str(k).lower(): v for k, v in rec.items()}


def _fetch_day(state: str, commodity: str, day: dt.date, key: str, rid: str, style: str):
    """Returns (records, Fetched|None). Tries lower-case then Title-case filter names unless style is forced."""
    date_s = day.strftime("%d/%m/%Y")
    styles = ["lower", "title"] if style == "auto" else [style]
    last = None
    for st in styles:
        names = ("state", "commodity", "arrival_date") if st == "lower" else ("State", "Commodity", "Arrival_Date")
        params = {
            "api-key": key, "format": "json", "limit": 300,
            f"filters[{names[0]}]": state, f"filters[{names[1]}]": commodity, f"filters[{names[2]}]": date_s,
        }
        f = get_json(API.format(rid=rid), params, ttl=get_settings().cache_ttl_s * 2)
        last = f
        recs = [_norm(r) for r in ((f.data or {}).get("records") or [])] if isinstance(f.data, dict) else []
        if recs:
            return recs, f
    return [], last


def get_mandi(profile: dict, text: str = "") -> ToolResult:
    s = get_settings()
    if not s.data_gov_api_key:
        raise SourceUnavailable("DATA_GOV_API_KEY is not set (free key from data.gov.in)")
    loc = resolve_location(profile)
    if not loc["state"]:
        raise NeedsInput("state", "the state of the farm (the place could not be matched to a state)")
    commodity = commodity_name(profile, text)

    today = dt.date.today()
    days = [today - dt.timedelta(days=i) for i in range(s.mandi_days)]
    with ThreadPoolExecutor(max_workers=min(7, len(days))) as ex:
        outs = list(ex.map(lambda d: _fetch_day(loc["state"], commodity, d, s.data_gov_api_key, s.mandi_resource_id, s.mandi_filter_style), days))

    records, fetched = [], [f for _, f in outs if f is not None]
    for recs, _ in outs:
        records.extend(recs)
    if not fetched:
        raise SourceUnavailable("no response from data.gov.in")
    series = build_series(records)
    src = {"name": "data.gov.in Agmarknet", "url": fetched[0].url, "fetched_at": max(f.fetched_at for f in fetched), "stale": any(f.stale for f in fetched)}
    sources = [src] + ([loc["source"]] if loc.get("source") else [])
    where = f"{loc['state']}"

    if not series:
        return ToolResult(
            f"MANDI PRICES: no published records for {commodity} in {where} for the last {s.mandi_days} days "
            f"(source: data.gov.in Agmarknet). Say honestly that no price data is available; do not estimate prices.",
            True, sources, [], {"location": {k: loc[k] for k in ("name", "state", "district", "lat", "lon")}, "price": {"signal": "INSUFFICIENT_DATA", "points": 0}},
        )

    sig = signal(series)
    latest_date = series[-1]["date"]
    latest_recs = [r for r in records if _same_day(r.get("arrival_date"), latest_date)]
    dist = (loc.get("district") or loc.get("name") or "").lower()

    def row(r):
        return {"market": r.get("market"), "district": r.get("district"), "modal": _num(r.get("modal_price")), "min": _num(r.get("min_price")), "max": _num(r.get("max_price"))}

    rows = [row(r) for r in latest_recs if _num(r.get("modal_price"))]
    near = [r for r in rows if dist and (r["district"] or "").lower() == dist][:3]
    top = sorted(rows, key=lambda r: r["modal"], reverse=True)[:3]

    lines = [f"MANDI PRICES for {commodity} in {where} - data.gov.in Agmarknet, fetched {src['fetched_at']}" + (" [STALE]" if src["stale"] else ""), "Unit: Rs per quintal. Daily average of modal prices across reporting markets:"]
    lines += [f"{p['date']}: Rs {p['modal']:.0f} ({p['n']} markets)" for p in series]
    if sig["signal"] != "INSUFFICIENT_DATA":
        lines.append(
            f"SIGNAL (computed in code): {sig['signal']} - latest Rs {sig['latest']:.0f} on {sig['latest_date']} vs average of earlier days Rs {sig['baseline_mean']:.0f} "
            f"({sig['pct_vs_baseline']} %), trend {sig['trend_per_day']} Rs/quintal per day over {sig['points']} days"
        )
    else:
        lines.append(f"SIGNAL: INSUFFICIENT_DATA ({sig['points']} days of prices; need 3). Report the latest prices only.")
    if near:
        lines.append(f"MARKETS in {loc.get('district') or loc['name']} on {latest_date}: " + "; ".join(f"{m['market']} Rs {m['modal']:.0f}" for m in near))
    if top:
        lines.append(f"HIGHEST MARKETS in {where} on {latest_date}: " + "; ".join(f"{m['market']} ({m['district']}) Rs {m['modal']:.0f}" for m in top))

    card = {"type": "prices", "title": f"{commodity} - mandi prices, {where}", "unit": "Rs/quintal", "series": series, "markets": (near + [m for m in top if m not in near])[:5], "signal": sig}
    return ToolResult("\n".join(lines), True, sources, [card], {"location": {k: loc[k] for k in ("name", "state", "district", "lat", "lon")}, "price": sig, "commodity": commodity})


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
    notes = cross_check(price, wx)
    decision = price.get("signal", "INSUFFICIENT_DATA")
    lines = [f"DECISION (computed in code): {decision}"] + [f"NOTE: {n}" for n in notes]
    if not notes:
        lines.append("NOTE: no weather risk that changes the price signal in the next 3 days.")
    return ToolResult("\n".join(lines), True, [], [], {"decision": decision, "notes": notes})


mandi = guarded("mandi")(lambda text, profile: get_mandi(profile, text))
cross = guarded("cross_check")(lambda text, profile: get_cross_check(profile, text))
