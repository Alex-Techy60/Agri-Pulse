"""Deterministic weather risk rules. LLM never decides these; code does.

Every threshold below is tagged with its basis (full table + URLs: docs/SOURCES.md):
  IMD        = India Meteorological Department glossary definition (verified against the glossary text).
  HEURISTIC  = practical guidance WITHOUT a verified Indian primary source; justification given inline.
"""
from __future__ import annotations

IMD_HEAVY_RAIN_MM = 64.5  # IMD glossary: "Heavy rain" = 64.5 to 124.4 mm in a day (lower bound used)
IMD_RAINY_DAY_MM = 2.5  # IMD glossary: "Rainy Day" = 2.5 mm or more in a day
IMD_HEAT_C = 40.0  # IMD: a heat wave is declared only when Tmax reaches >= 40 C in plains (it ALSO needs a +4..+6 C departure from normal, which we do not check), so this is a heat-STRESS flag, not a heat-wave declaration
IMD_COLD_C = 4.0  # HEURISTIC low-temperature stress flag. NOT an IMD cold-wave criterion (IMD uses wind-chill minimum temperature and departure from normal); crop-specific limits come from crop_rules
SPRAY_MAX_WIND_KMH = 15.0  # HEURISTIC: no Indian limit found; sits just under the ~16 km/h upper end of the 3-16 km/h window in Canadian guidance (Saskatchewan/OMAFRA). Product label always governs
SPRAY_MAX_RAIN_PROB = 40  # HEURISTIC: practical wash-off risk cut-off on the daily max rain probability; conservative on purpose (a skipped spray day costs less than a washed-off one)
IRRIGATION_SKIP_RAIN_MM = 10.0  # HEURISTIC: FAO gives effective-rainfall formulas but no fixed skip limit; 10 mm in 48 h is roughly 2 days of typical crop water use (ET0 about 4-5 mm/day)


def _val(lst, i):
    try:
        v = lst[i]
        return None if v is None else float(v)
    except (IndexError, TypeError, ValueError):
        return None


def days_from_daily(daily: dict) -> list[dict]:
    dates = daily.get("time") or []
    out = []
    for i, d in enumerate(dates):
        out.append(
            {
                "i": i,
                "date": d,
                "tmax": _val(daily.get("temperature_2m_max", []), i),
                "tmin": _val(daily.get("temperature_2m_min", []), i),
                "rain_mm": _val(daily.get("precipitation_sum", []), i),
                "rain_prob": _val(daily.get("precipitation_probability_max", []), i),
                "wind_kmh": _val(daily.get("wind_speed_10m_max", []), i),
                "et0_mm": _val(daily.get("et0_fao_evapotranspiration", []), i),
            }
        )
    return out


def analyze(days: list[dict]) -> dict:
    flags = []
    for d in days:
        if d["rain_mm"] is not None and d["rain_mm"] >= IMD_HEAVY_RAIN_MM:
            flags.append({"flag": "HEAVY_RAIN", "day": d["date"], "day_index": d["i"], "value": d["rain_mm"], "unit": "mm", "rule": f">= {IMD_HEAVY_RAIN_MM} mm/24h (IMD heavy rain)"})
        if d["tmax"] is not None and d["tmax"] >= IMD_HEAT_C:
            flags.append({"flag": "HEAT_STRESS", "day": d["date"], "day_index": d["i"], "value": d["tmax"], "unit": "C", "rule": f"Tmax >= {IMD_HEAT_C} C (IMD minimum temperature for a plains heat wave; departure from normal not checked)"})
        if d["tmin"] is not None and d["tmin"] <= IMD_COLD_C:
            flags.append({"flag": "COLD_STRESS", "day": d["date"], "day_index": d["i"], "value": d["tmin"], "unit": "C", "rule": f"Tmin <= {IMD_COLD_C} C (heuristic low-temperature stress threshold)"})

    spray_ok = [
        d["date"]
        for d in days
        if d["wind_kmh"] is not None
        and d["rain_prob"] is not None
        and d["wind_kmh"] <= SPRAY_MAX_WIND_KMH
        and d["rain_prob"] <= SPRAY_MAX_RAIN_PROB
        and (d["rain_mm"] or 0) < IMD_RAINY_DAY_MM
    ]

    next48 = sum((d["rain_mm"] or 0) for d in days[:2])
    irrigation = "SKIP_IRRIGATION" if next48 >= IRRIGATION_SKIP_RAIN_MM else "IRRIGATE_IF_SOIL_DRY"

    rainy = [d["date"] for d in days if (d["rain_mm"] or 0) >= IMD_RAINY_DAY_MM]
    dry_spell = len(days) >= 5 and not rainy

    return {
        "flags": flags,
        "spray_ok_days": spray_ok,
        "rain_next_48h_mm": round(next48, 1),
        "irrigation": irrigation,
        "rainy_days": rainy,
        "dry_spell": dry_spell,
    }


# Rain-history rules (HEURISTIC; justification in docs/SOURCES.md). 'Dry' = under one IMD rainy day's worth (2.5 mm) in 7 days.
DRY_PAST7_MM = 2.5
DRY_NEXT7_MM = 5.0
IRRIGATION_URGENT_PAST14_MM = 5.0
WATERLOG_PAST7_MM = 100.0
WATERLOG_NEXT3_MM = 30.0


def analyze_rain_history(past_mm: list[float | None], forecast_mm: list[float | None]) -> dict:
    """past_mm: oldest -> yesterday (>= 14 days to judge dryness). forecast_mm: today -> +6 days.
    Missing days count as 0 mm only for totals; alerts need enough real days, never guessed."""
    tot = lambda xs: round(sum(x for x in xs if x is not None), 1)
    p7, p14, p30, f7, f3 = tot(past_mm[-7:]), tot(past_mm[-14:]), tot(past_mm), tot(forecast_mm[:7]), tot(forecast_mm[:3])
    real = lambda xs: sum(1 for x in xs if x is not None)
    alerts = []
    if real(past_mm[-7:]) >= 5 and real(forecast_mm[:7]) >= 5 and p7 < DRY_PAST7_MM and f7 < DRY_NEXT7_MM:
        alerts.append("DRY_SPELL_ALERT")
    if real(past_mm[-14:]) >= 10 and p14 < IRRIGATION_URGENT_PAST14_MM:
        alerts.append("IRRIGATION_URGENT")
    if p7 > WATERLOG_PAST7_MM and f3 > WATERLOG_NEXT3_MM:
        alerts.append("WATERLOGGING_RISK")
    return {"past_7d_mm": p7, "past_14d_mm": p14, "past_30d_mm": p30, "forecast_7d_mm": f7, "forecast_3d_mm": f3, "alerts": alerts}
