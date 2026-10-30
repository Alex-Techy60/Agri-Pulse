"""Deterministic sell/hold signal from REAL mandi price history, plus weather cross-checks.

The LLM explains these results; it does not compute or override them.
HEURISTIC thresholds (+/-5 % vs recent average) are tunable; cite or justify them in the pitch.
"""
from __future__ import annotations

import datetime as dt

SELL_ABOVE_PCT = 5.0
HOLD_BELOW_PCT = -5.0
MIN_POINTS = 3
OUTLIER_FACTOR = 10.0


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


def cross_check(price: dict, weather: dict) -> list[str]:
    """Combine price signal with weather risk. Pure function; returns plain-English notes."""
    notes: list[str] = []
    heavy_soon = [f for f in weather.get("flags", []) if f["flag"] == "HEAVY_RAIN" and f["day_index"] <= 3]
    sig = price.get("signal")
    if heavy_soon:
        f = heavy_soon[0]
        if sig == "SELL_NOW":
            notes.append(f"SELL_BEFORE_RAIN: heavy rain ({f['value']} mm) forecast on {f['day']}; prices are above the recent average, so selling before the rain is favourable.")
        else:
            notes.append(f"STORAGE_RISK: heavy rain ({f['value']} mm) forecast on {f['day']}; protect stored produce or consider selling early.")
    if sig == "INSUFFICIENT_DATA":
        notes.append("Price history is too short for a trend; report only the latest published prices and say a trend is not available.")
    return notes
