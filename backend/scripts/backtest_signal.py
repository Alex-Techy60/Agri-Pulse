"""Backtest the sell/hold band on real dated Agmarknet prices. Usage: python -m scripts.backtest_signal [state] [commodity] [days]

For each past day it runs the production build_series + signal over the preceding 7 days, then compares with the state
average price about 7 days later. SELL_NOW is 'right' if the price then fell, HOLD is 'right' if it then rose.
"""
from __future__ import annotations

import datetime as dt
import sys
import time

from app.core.config import get_settings
from app.decision import price_rules
from app.decision.price_rules import build_series, parse_date, signal
from app.tools.http import get_json

API = "https://api.data.gov.in/resource/35985678-0d79-46b4-9ed6-6f13308a1d24"
PAGE, MAX_PAGES, PAUSE_S = 500, 40, 3.0
BANDS = (3.0, 5.0, 7.0, 10.0)
WINDOW_DAYS = 7
HORIZON_DAYS = 7


def fetch_rows(state: str, commodity: str, days: int) -> list[dict]:
    """Newest rows first, paged slowly: this API rate limits bursts and the key is shared with the running app."""
    oldest, out = dt.date.today() - dt.timedelta(days=days), []
    for page in range(MAX_PAGES):
        params = {"api-key": get_settings().data_gov_api_key, "format": "json", "limit": PAGE, "offset": page * PAGE, "filters[State]": state,
                  "filters[Commodity]": commodity, "sort[Arrival_Date]": "desc"}
        recs = (get_json(API, params, ttl=3600, timeout=25).data or {}).get("records") or []
        rows = [{str(k).lower(): v for k, v in r.items()} for r in recs]
        out += [r for r in rows if str(r.get("commodity", "")).strip().lower() == commodity.lower()]
        dates = [parse_date(r.get("arrival_date", "")) for r in rows]
        if len(recs) < PAGE or min(d for d in dates if d) < oldest:
            break
        time.sleep(PAUSE_S)
    return [r for r in out if (d := parse_date(r.get("arrival_date", ""))) and d >= oldest]


def evaluate(series: list[dict], band: float) -> dict:
    price_rules.SELL_ABOVE_PCT, price_rules.HOLD_BELOW_PCT = band, -band
    dates = [dt.date.fromisoformat(s["date"]) for s in series]
    calls: dict[str, list[float]] = {"SELL_NOW": [], "HOLD": [], "NEUTRAL": []}
    for i, d in enumerate(dates):
        window = [s for s, x in zip(series[: i + 1], dates) if (d - x).days < WINDOW_DAYS]
        later = next((series[j]["modal"] for j in range(i + 1, len(series)) if (dates[j] - d).days >= HORIZON_DAYS), None)
        sig = signal(window)
        if later is not None and sig["signal"] in calls:
            calls[sig["signal"]].append((later - series[i]["modal"]) / series[i]["modal"] * 100)
    return calls


def main() -> None:
    state, commodity = (sys.argv[1:3] + ["Maharashtra", "Onion"][len(sys.argv[1:3]):])
    days = int(sys.argv[3]) if len(sys.argv) > 3 else 180
    records = fetch_rows(state, commodity, days)
    series = build_series(records)
    if not series:
        print("no data returned")
        return
    print(f"{commodity}, {state}: {len(records)} real records, {len(series)} market days, {series[0]['date']} to {series[-1]['date']}")
    print("band    SELL_NOW n / right / avg 7d move    HOLD n / right / avg 7d move    NEUTRAL n")
    for band in BANDS:
        c = evaluate(series, band)
        sell, hold = c["SELL_NOW"], c["HOLD"]
        avg = lambda xs: f"{sum(xs) / len(xs):+.1f}%" if xs else "n/a"
        rate = lambda xs, ok: f"{sum(map(ok, xs)) * 100 // len(xs)}%" if xs else "n/a"
        print(f"+/-{band:<4} {len(sell):>4} / {rate(sell, lambda x: x < 0):>4} / {avg(sell):>6}             {len(hold):>4} / {rate(hold, lambda x: x > 0):>4} / {avg(hold):>6}             {len(c['NEUTRAL'])}")


if __name__ == "__main__":
    main()
