"""Crop suitability for the farm's place: which crops fit now, when to sow the farmer's crop, whether it is ready.

Live part: five complete years of daily weather at the farm from the Open-Meteo historical archive (ERA5 reanalysis), averaged
by day of year. Reference part: the FAO EcoCrop limits in data/ecocrop_subset.csv. The scoring is in app/decision/crop_fit.py.
A climate guide only: never presented as a forecast, a profit ranking or a replacement for the local agriculture officer.
"""
from __future__ import annotations

import datetime as dt
import logging

from app.decision import crop_fit as cf
from app.tools import SourceUnavailable, ToolResult, guarded
from app.tools.http import get_json
from app.tools.location import resolve_location
from app.tools.mandi import crop_key

log = logging.getLogger("tool.crop_fit")
ARCHIVE_URL = "https://archive-api.open-meteo.com/v1/archive"
CLIMATE_TTL_S = 30 * 86400  # a five-year average does not move within a month
CLIMATE_TIMEOUT_S = 15.0
YEARS = 5
MAX_SUITABLE_LISTED = 6
ECOCROP_NOTE = "FAO EcoCrop limits (gaez.fao.org/pages/ecocrop; table rebuilt from the UKCEH copy by scripts/build_ecocrop_subset.py)"

# Names the farmer or the mandi tool use -> the key in the EcoCrop table.
CROP_ALIASES = {"soyabean": "soybean", "paddy": "rice", "paddy(common)": "rice", "chana": "gram", "arhar": "tur", "bhindi": "okra", "lady finger": "okra", "ladyfinger": "okra",
                "green gram": "moong", "black gram": "urad", "green chilli": "chilli", "bengal gram": "gram", "pearl millet": "bajra", "sorghum": "jowar", "peas": "pea", "lentils": "lentil"}


def table_key(crop: str) -> str:
    k = crop_key(crop or "")
    return CROP_ALIASES.get(k, k)


def parse_sowing_date(raw: str, today: dt.date) -> dt.date | None:
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%d.%m.%Y"):
        try:
            d = dt.datetime.strptime((raw or "").strip(), fmt).date()
        except ValueError:
            continue
        return d if dt.timedelta(days=-366) <= d - today <= dt.timedelta(days=366) else None
    return None


def fetch_climate(loc: dict, today: dt.date):
    """-> (365-day climatology, Fetched, first year, last year). Raises SourceUnavailable; never fills a gap with a guess."""
    y1, y0 = today.year - 1, today.year - YEARS
    f = get_json(ARCHIVE_URL, {"latitude": loc["lat"], "longitude": loc["lon"], "start_date": f"{y0}-01-01", "end_date": f"{y1}-12-31",
                                "daily": "temperature_2m_mean,temperature_2m_max,temperature_2m_min,precipitation_sum", "timezone": "auto"},
                 ttl=CLIMATE_TTL_S, timeout=CLIMATE_TIMEOUT_S)
    d = (f.data or {}).get("daily") if isinstance(f.data, dict) else None
    if not d or not d.get("time"):
        raise SourceUnavailable("the historical weather response had no daily data")
    days = [{"date": t, "tmean": a, "tmax": b, "tmin": c, "rain": r} for t, a, b, c, r in zip(d["time"], d["temperature_2m_mean"], d["temperature_2m_max"], d["temperature_2m_min"], d["precipitation_sum"])]
    clim = cf.climatology(days)
    if clim is None:
        raise SourceUnavailable("the historical weather response had gaps")
    return clim, f, y0, y1


def _detail(c: cf.Crop, s: dict) -> str:
    heat = f"; {s['hot_days']} days of the cycle have a typical daytime maximum above the crop's limit of {c.tmax:g} C" if s["hot_days"] else ""
    return (f"temperature fit {s['temp']} ({s['label']}), sow about {s['sow_on']}, usual cycle {c.gmin}-{c.gmax} days, harvest roughly {s['harvest_from']} to {s['harvest_to']}; "
            f"rain over the cycle {s['rain_mm']} mm vs the crop's optimum {c.ropmn:g}-{c.ropmx:g} mm -> {s['rain_label']}{heat}")


def _line(c: cf.Crop, s: dict) -> str:
    return f"- {c.common}: {_detail(c, s)}"


def get_crop_fit(profile: dict, text: str = "") -> ToolResult:
    loc = resolve_location(profile)
    today = dt.date.today()
    clim, f, y0, y1 = fetch_climate(loc, today)
    crops = cf.load_crops()
    where = f"{loc['name']}, {loc['state']}".strip(", ")
    ranked = cf.rank_for_sowing(clim, today, crops)
    suitable = [(c, s) for c, s in ranked if s["temp"] >= cf.GOOD]
    rain_fed = cf.rain_fed_only(ranked)
    unsuitable = [c.common for c, s in ranked if s["temp"] == 0]

    lines = [
        f"CROP FIT for {where} ({loc['lat']}, {loc['lon']}). A CLIMATE-ONLY guide: {ECOCROP_NOTE} applied to the average weather of {y0}-{y1} at this place "
        f"(Open-Meteo historical weather, ERA5 reanalysis, fetched {f.fetched_at}). It is not a forecast and not a profit ranking; soil, variety, water supply, pests and prices are NOT included. "
        f"Fit scores run 0-100 (GOOD is {cf.GOOD} or more; the cut-off is a heuristic). Always tell the farmer to confirm with the local agriculture officer or KVK. When citing, say \"FAO EcoCrop limits and Open-Meteo historical weather\"; the date in a citation is never a sowing or harvest date."
    ]
    lines.append(f"SUITABLE CROPS to sow between {today.isoformat()} and {(today + dt.timedelta(days=cf.SOW_LOOKAHEAD_DAYS)).isoformat()}: " + (f"{len(suitable)} crops have a GOOD temperature fit; {min(len(suitable), MAX_SUITABLE_LISTED)} are listed, not ranked by profit. Name at most 5 of them in the answer, one short line each." if suitable else "none has a GOOD temperature fit in this period."))
    lines += [_line(c, s) for c, s in suitable[:MAX_SUITABLE_LISTED]]
    lines.append("RAIN-FED (no irrigation assumed): " + (", ".join(c.common for c, s in rain_fed[:6]) if rain_fed else "none: the rain over a crop cycle starting now is below what these crops need, so they would need irrigation."))
    if unsuitable:
        lines.append("NOT SUITABLE to sow in this period (temperature fit 0): " + ", ".join(unsuitable[:8]))

    cards = [{"type": "crop_fit", "title": f"Crops that fit the climate - {where}", "note": "Climate only. Confirm with your agriculture officer.",
              "crops": [{"crop": c.common, "fit": s["temp"], "label": s["label"], "sow_on": s["sow_on"], "harvest_from": s["harvest_from"], "harvest_to": s["harvest_to"],
                         "rain_mm": s["rain_mm"], "rain_label": s["rain_label"]} for c, s in suitable[:MAX_SUITABLE_LISTED]]}]
    facts: dict = {"location": {k: loc[k] for k in ("name", "state", "district", "lat", "lon")}, "suitable": [c.key for c, _ in suitable]}

    key = table_key(profile.get("crop", ""))
    if profile.get("crop"):
        c = crops.get(key)
        if c is None:
            lines.append(f"YOUR CROP {profile['crop']}: no EcoCrop limits are loaded for it (the table covers annual field crops; perennials such as banana, mango or sugarcane are not scored). Say so; give no fit, sowing or harvest dates for it.")
        else:
            now = cf.best_sowing_now(clim, c, today)
            lines.append(f"YOUR CROP {c.common}: {_detail(c, now)}")
            win = cf.sowing_windows(clim, c, today)
            if win:
                lines.append(f"BEST SOWING WINDOWS for {c.common} over the next 12 months: " + "; ".join(f"about {w['sow_on']} (temperature fit {w['temp']}, {w['rain_mm']} mm rain over the cycle, {w['rain_label']})" for w in win))
            else:
                lines.append(f"BEST SOWING WINDOWS for {c.common}: no sowing date in the next 12 months reaches a POSSIBLE temperature fit at this place.")
            facts.update({"crop": c.key, "fit_now": now, "windows": win})
            cards[0]["your_crop"] = {"crop": c.common, "fit": now["temp"], "label": now["label"], "sow_on": now["sow_on"], "windows": [w["sow_on"] for w in win]}
            raw = (profile.get("sowing_date") or "").strip()
            if raw:
                d = parse_sowing_date(raw, today)
                if d is None:
                    lines.append(f"SOWING DATE '{raw}' could not be read as a date within a year of today; ask the farmer for it as day/month/year.")
                else:
                    h = cf.harvest_status(c, d, today)
                    lines.append(f"SOWN {d.isoformat()}: {h['days_since_sowing']} days ago. The usual cycle of {c.common} is {c.gmin}-{c.gmax} days (varieties differ), so harvest is expected from {h['earliest']} to {h['latest']}. STAGE: {h['status']}"
                                 + (f" ({h['days_to_earliest']} days to the earliest harvest)." if h["status"] == "BEFORE_EARLIEST_HARVEST" else "."))
                    facts["harvest"] = h
    sources = [{"name": "Open-Meteo historical weather (5-year average)", "url": f.url, "fetched_at": f.fetched_at, "stale": f.stale}] + ([loc["source"]] if loc.get("source") else [])
    return ToolResult("\n".join(lines), True, sources, cards, facts)


crop_fit = guarded("crop_fit")(lambda text, profile: get_crop_fit(profile, text))
