"""Crop water need from FAO-56: crop coefficient (Kc) x reference evapotranspiration (ET0), by growth stage.

Every number in CROPS is copied from FAO Irrigation and Drainage Paper 56 (Allen et al., 1998), chapter 6:
  Table 11 - lengths of the initial / development / mid-season / late stages (days), per planting row
  Table 12 - single crop coefficients Kc (initial, mid-season, end-season)
https://www.fao.org/4/x0490E/x0490e0b.htm

Where Table 12 prints a range, the midpoint is used and the note says so. The Kc initial value is an image in the
FAO web page; the value used is the one printed in the group heading for that crop family, and the note says so.
FAO calls its stage lengths "indicative" and says they vary with region and variety. The planting row chosen for each
crop is named in its `row` field, and the result tells the farmer that the timing is not tuned to Nashik.

Pure functions only: no network, no I/O. The caller passes the forecast; nothing here is invented.
"""
from __future__ import annotations

import datetime as dt

FAO56 = "FAO-56 (Allen et al., 1998), Table 11 stage lengths and Table 12 Kc, https://www.fao.org/4/x0490E/x0490e0b.htm"

CROPS: dict[str, dict] = {
    "onion": {
        "row": "dry onion, planted April, Mediterranean climate (Table 11)",
        "stages": {"ini": 15, "dev": 25, "mid": 70, "late": 40},
        "kc": {"ini": 0.7, "mid": 1.05, "end": 0.75},
        "note": "Kc ini from the Table 12 heading for small vegetables (0.7); Kc mid and end printed for dry onion.",
    },
    "tomato": {
        "row": "planted April/May, Mediterranean climate (Table 11)",
        "stages": {"ini": 30, "dev": 40, "mid": 45, "late": 30},
        "kc": {"ini": 0.6, "mid": 1.15, "end": 0.80},
        "note": "Kc ini and mid from the Table 12 heading for the Solanum family (0.6, 1.15); Kc end is the midpoint of the printed 0.70-0.90.",
    },
    "soybean": {
        "row": "planted June, Japan (Table 11)",
        "stages": {"ini": 20, "dev": 25, "mid": 75, "late": 30},
        "kc": {"ini": 0.4, "mid": 1.15, "end": 0.50},
        "note": "Kc ini from the Table 12 heading for legumes (0.4); Kc mid and end printed for soybeans.",
    },
    "cotton": {
        "row": "planted March-May, Egypt / Pakistan / California (Table 11)",
        "stages": {"ini": 30, "dev": 50, "mid": 60, "late": 55},
        "kc": {"ini": 0.35, "mid": 1.18, "end": 0.60},
        "note": "Kc ini from the Table 12 heading for fibre crops (0.35); Kc mid is the midpoint of the printed 1.15-1.20 and Kc end the midpoint of 0.50-0.70.",
    },
    "wheat": {
        "row": "planted November, Central India (Table 11, barley/oats/wheat)",
        "stages": {"ini": 15, "dev": 25, "mid": 50, "late": 30},
        "kc": {"ini": 0.7, "mid": 1.15, "end": 0.33},
        "note": "Winter wheat on non-frozen soils (Table 12): Kc ini 0.7, mid 1.15; Kc end is the midpoint of the printed 0.25-0.41.",
    },
}

LABEL_COVERS = "RAIN_COVERS_CROP_NEED"
LABEL_SHORT = "RAIN_SHORT_OF_CROP_NEED"
WINDOW_DAYS = 7


def crop_entry(crop: str) -> dict | None:
    return CROPS.get((crop or "").strip().lower())


def parse_sowing(text) -> dt.date | None:
    """A sowing date as the farmer typed it: ISO YYYY-MM-DD only. Anything else is treated as not given."""
    if not isinstance(text, str):
        return None
    try:
        return dt.date.fromisoformat(text.strip())
    except ValueError:
        return None


def stage_at(crop: str, sowing: dt.date, on: dt.date) -> dict | None:
    """Growth stage and Kc for `crop` on day `on`, sown on `sowing`. None if the crop is unknown.
    Kc rises linearly from ini to mid through the development stage, holds at mid, and falls linearly to end through the late stage."""
    entry = crop_entry(crop)
    if entry is None:
        return None
    day = (on - sowing).days  # 0 = sowing day
    st, kc = entry["stages"], entry["kc"]
    total = sum(st.values())
    if day < 0:
        return {"stage": "not_sown", "day": day, "kc": None, "total_days": total}
    if day >= total:
        return {"stage": "cycle_complete", "day": day, "kc": None, "total_days": total}
    ini_end = st["ini"]
    dev_end = ini_end + st["dev"]
    mid_end = dev_end + st["mid"]
    if day < ini_end:
        stage, value = "initial", kc["ini"]
    elif day < dev_end:
        frac = (day - ini_end + 1) / st["dev"]
        stage, value = "development", kc["ini"] + (kc["mid"] - kc["ini"]) * min(frac, 1.0)
    elif day < mid_end:
        stage, value = "mid_season", kc["mid"]
    else:
        frac = (day - mid_end + 1) / st["late"]
        stage, value = "late_season", kc["mid"] + (kc["end"] - kc["mid"]) * min(frac, 1.0)
    return {"stage": stage, "day": day, "kc": round(value, 2), "total_days": total}


def crop_water_need(crop: str, sowing: dt.date, today: dt.date, days: list[dict]) -> dict | None:
    """Crop water need for the next WINDOW_DAYS days of forecast, against the forecast rain.

    `days` are the forecast days from weather_rules.days_from_daily (keys date, rain_mm, et0_mm). Every day needs both
    rain and ET0 to count; a day with a missing value is left out and reported, so a gap never becomes a zero."""
    entry = crop_entry(crop)
    if entry is None:
        return None
    today_state = stage_at(crop, sowing, today)
    if today_state is None:
        return None
    window = [d for d in days if d.get("date") and dt.date.fromisoformat(d["date"]) >= today][:WINDOW_DAYS]
    used, need, rain, skipped = [], 0.0, 0.0, 0
    for d in window:
        state = stage_at(crop, sowing, dt.date.fromisoformat(d["date"]))
        if d.get("et0_mm") is None or d.get("rain_mm") is None or state is None or state["kc"] is None:
            skipped += 1
            continue
        need += state["kc"] * d["et0_mm"]
        rain += d["rain_mm"]
        used.append(d["date"])
    if not used:
        return {"today": today_state, "days": 0, "skipped": skipped, "need_mm": None, "rain_mm": None,
                "balance_mm": None, "label": None, "row": entry["row"], "note": entry["note"], "source": FAO56}
    need, rain = round(need, 1), round(rain, 1)
    gap = round(rain - need, 1)
    return {
        "today": today_state,
        "days": len(used),
        "skipped": skipped,
        "need_mm": need,
        "rain_mm": rain,
        "balance_mm": gap,
        "label": LABEL_COVERS if gap >= 0 else LABEL_SHORT,
        "row": entry["row"],
        "note": entry["note"],
        "source": FAO56,
    }
