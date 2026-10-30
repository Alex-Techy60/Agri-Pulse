"""Deterministic sell/hold signal from REAL mandi price history, plus weather cross-checks.

The LLM explains these results; it does not compute or override them.
HEURISTIC thresholds (+/-5 % vs recent average) are tunable; cite or justify them in the pitch.
"""
from __future__ import annotations

import datetime as dt
import re
import unicodedata

SELL_ABOVE_PCT = 5.0
HOLD_BELOW_PCT = -5.0
MIN_POINTS = 3
OUTLIER_FACTOR = 10.0
POSITION_BAND_PCT = 5.0  # local median within +/-5 % of the state median counts as NEAR


def norm_name(s: str) -> str:
    """Compare place names across sources: 'Srīnagar District' / 'Raipur district' / 'Raipur' must all match."""
    t = unicodedata.normalize("NFKD", str(s or "")).encode("ascii", "ignore").decode().lower()
    return re.sub(r"\s+", " ", re.sub(r"\bdistrict\b", "", t)).strip()


def parse_date(s: str) -> dt.date | None:
    for fmt in ("%d/%m/%Y", "%Y-%m-%d", "%d-%m-%Y"):
        try:
            return dt.datetime.strptime(str(s).strip(), fmt).date()
        except ValueError:
            continue
    return None


def to_float(v) -> float | None:
    try:
        return float(str(v).replace(",", "").strip())
    except (TypeError, ValueError):
        return None


def build_series(records: list[dict]) -> list[dict]:
    """records: normalised dicts with arrival_date + modal_price. -> [{date, modal, n}] ascending."""
    by: dict[dt.date, list[float]] = {}
    for r in records:
        d, m = parse_date(r.get("arrival_date", "")), to_float(r.get("modal_price"))
        if d and m and m > 0:
            by.setdefault(d, []).append(m)
    by = {d: _drop_outliers(v) for d, v in by.items()}
    return [{"date": d.isoformat(), "modal": round(sum(v) / len(v), 0), "n": len(v)} for d, v in sorted(by.items())]


def _drop_outliers(vals: list[float]) -> list[float]:
    """Agmarknet has data-entry slips (an extra zero, a Rs/kg row). Drop prices >10x or <1/10 of the day's median."""
    if len(vals) < 3:
        return vals
    s = sorted(vals)
    med = s[len(s) // 2] if len(s) % 2 else (s[len(s) // 2 - 1] + s[len(s) // 2]) / 2
    return [v for v in vals if med / OUTLIER_FACTOR < v < med * OUTLIER_FACTOR]


def clean_rows(rows: list[dict]) -> list[dict]:
    """Same outlier rule as build_series, for per-market rows (all one commodity): drops entries 10x away from the median
    (typos or unit slips). NOTE: the fetch layer already removes other commodities that the API's loose filter returns."""
    vals = [r["modal"] for r in rows if r.get("modal")]
    keep = set(map(id, [r for r in rows if r.get("modal") and r["modal"] in _drop_outliers_keep(vals)]))
    return [r for r in rows if id(r) in keep]


def _drop_outliers_keep(vals: list[float]) -> set:
    return set(_drop_outliers(vals))


def signal(series: list[dict]) -> dict:
    n = len(series)
    if n < MIN_POINTS:
        return {"signal": "INSUFFICIENT_DATA", "points": n, "latest": series[-1]["modal"] if n else None, "latest_date": series[-1]["date"] if n else None}
    latest = series[-1]["modal"]
    prev = [s["modal"] for s in series[:-1]]
    base = sum(prev) / len(prev)
    pct = (latest - base) / base * 100 if base else 0.0
    xs = list(range(n))
    xm, ym = sum(xs) / n, sum(s["modal"] for s in series) / n
    den = sum((x - xm) ** 2 for x in xs) or 1.0
    slope = sum((x - xm) * (s["modal"] - ym) for x, s in zip(xs, series)) / den
    sig = "SELL_NOW" if pct >= SELL_ABOVE_PCT else "HOLD" if pct <= HOLD_BELOW_PCT else "NEUTRAL"
    return {
        "signal": sig,
        "points": n,
        "latest": latest,
        "latest_date": series[-1]["date"],
        "baseline_mean": round(base, 0),
        "pct_vs_baseline": round(pct, 1),
        "trend_per_day": round(slope, 1),
    }


def cross_check(price: dict, weather: dict, position: dict | None = None) -> list[str]:
    """Combine price signal with weather risk. Pure function; returns plain-English notes.
    With a price TREND (>= 3 days of history) the trend decides. This source publishes only today's prices, so without a
    trend the farmer's market position today (vs the state median) is used instead, and the note says so."""
    notes: list[str] = []
    heavy_soon = [f for f in weather.get("flags", []) if f["flag"] == "HEAVY_RAIN" and f["day_index"] <= 3]
    sig = price.get("signal")
    label = (position or {}).get("label")
    if heavy_soon:
        f = heavy_soon[0]
        rain = f"heavy rain ({f['value']} mm) forecast on {f['day']}"
        if sig == "SELL_NOW":
            notes.append(f"SELL_BEFORE_RAIN: {rain}; prices are above the recent average, so selling before the rain is favourable.")
        elif sig in (None, "INSUFFICIENT_DATA") and label == "ABOVE_STATE_MEDIAN":
            notes.append(f"SELL_BEFORE_RAIN: {rain}; no price trend is available, but your district's price today is {position['pct_vs_state_median']} % above the state median, so selling before the rain is favourable.")
        elif sig in (None, "INSUFFICIENT_DATA") and label == "BELOW_STATE_MEDIAN":
            notes.append(f"STORAGE_RISK: {rain}; your district's price today is {abs(position['pct_vs_state_median'])} % below the state median. The best price today is Rs {position['best_price']} at {position['best_market']} ({position['best_district']}); protect stored produce or consider selling early.")
        else:
            notes.append(f"STORAGE_RISK: {rain}; protect stored produce or consider selling early.")
    if sig == "INSUFFICIENT_DATA":
        notes.append("Price history is too short for a trend; report only the latest published prices and say a trend is not available.")
    return notes


def market_position(rows: list[dict], district: str) -> dict | None:
    """Where the farmer's district sits among the state's markets on the latest day. Descriptive, not a forecast: the
    source publishes only the current day, so this works without any price history. rows = [{market, district, modal}]."""
    ok = [r for r in rows if r.get("modal")]
    if len(ok) < 3:
        return None
    med = lambda xs: sorted(xs)[len(xs) // 2] if len(xs) % 2 else (sorted(xs)[len(xs) // 2 - 1] + sorted(xs)[len(xs) // 2]) / 2
    state_median = med([r["modal"] for r in ok])
    best = max(ok, key=lambda r: r["modal"])
    out = {"state_median": round(state_median), "markets": len(ok), "best_market": best.get("market"), "best_district": best.get("district"), "best_price": round(best["modal"])}
    local = [r["modal"] for r in ok if district and norm_name(r.get("district")) == norm_name(district)]
    if local and state_median:
        pct = (med(local) - state_median) / state_median * 100
        out.update({"local_median": round(med(local)), "local_markets": len(local), "pct_vs_state_median": round(pct, 1),
                    "label": "ABOVE_STATE_MEDIAN" if pct >= POSITION_BAND_PCT else "BELOW_STATE_MEDIAN" if pct <= -POSITION_BAND_PCT else "NEAR_STATE_MEDIAN"})
    return out
