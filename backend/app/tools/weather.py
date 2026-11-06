"""Live weather + soil moisture for the farm location (Open-Meteo, free, no key)."""
from __future__ import annotations

from app.decision.weather_rules import analyze, days_from_daily
from app.tools import ToolResult, guarded
from app.tools.http import get_json
from app.tools.location import resolve_location

FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
DAILY = "temperature_2m_max,temperature_2m_min,precipitation_sum,precipitation_probability_max,wind_speed_10m_max,et0_fao_evapotranspiration"


SOIL_HOURLY = ("soil_moisture_3_to_9cm", "soil_moisture_9_to_27cm", "soil_moisture_27_to_81cm", "soil_temperature_6cm", "soil_temperature_18cm")


def _day_mean(hourly: dict, key: str, digits: int = 3) -> float | None:
    vals = [v for v in (hourly.get(key) or [])[:24] if v is not None]
    return round(sum(vals) / len(vals), digits) if vals else None


def _soil_moisture(hourly: dict) -> float | None:
    return _day_mean(hourly, "soil_moisture_3_to_9cm")


def soil_profile(hourly: dict) -> dict:
    """Next-24h means per depth. The surface dries first while the deeper layers hold the water roots use, so the surface figure
    alone can mislead (3-9 cm 0.17 but 9-27 cm 0.30 on 31 Oct 2026, Nashik). Only layers the model returned are included."""
    out = {"moisture_3_9cm": _day_mean(hourly, "soil_moisture_3_to_9cm"), "moisture_9_27cm": _day_mean(hourly, "soil_moisture_9_to_27cm"),
           "moisture_27_81cm": _day_mean(hourly, "soil_moisture_27_to_81cm"), "temp_6cm_c": _day_mean(hourly, "soil_temperature_6cm", 1),
           "temp_18cm_c": _day_mean(hourly, "soil_temperature_18cm", 1)}
    return {k: v for k, v in out.items() if v is not None}


def get_weather(profile: dict) -> ToolResult:
    loc = resolve_location(profile)
    f = get_json(
        FORECAST_URL,
        {
            "latitude": loc["lat"],
            "longitude": loc["lon"],
            "daily": DAILY,
            "hourly": ",".join(SOIL_HOURLY),
            "current": "temperature_2m,relative_humidity_2m,wind_speed_10m",
            "forecast_days": 7,
            "timezone": "auto",
            "wind_speed_unit": "kmh",
        },
    )
    data = f.data if isinstance(f.data, dict) else {}
    days = days_from_daily(data.get("daily") or {})
    if not days:
        from app.tools import SourceUnavailable

        raise SourceUnavailable("forecast response had no daily data")
    a = analyze(days)
    cur = data.get("current") or {}
    soil = _soil_moisture(data.get("hourly") or {})
    profile = soil_profile(data.get("hourly") or {})
    src = {"name": "Open-Meteo forecast", "url": f.url, "fetched_at": f.fetched_at, "stale": f.stale}
    sources = [src] + ([loc["source"]] if loc.get("source") else [])

    where = f"{loc['name']}, {loc['state']}".strip(", ")
    lines = [f"WEATHER for {where} ({loc['lat']}, {loc['lon']}) - Open-Meteo, fetched {f.fetched_at}" + (f" [STALE: {f.age_s}s old]" if f.stale else "")]
    if cur:
        lines.append(f"Now: {cur.get('temperature_2m')} C, humidity {cur.get('relative_humidity_2m')} %, wind {cur.get('wind_speed_10m')} km/h")
    for d in days:
        lines.append(f"{d['date']}: max {d['tmax']} C, min {d['tmin']} C, rain {d['rain_mm']} mm (chance {d['rain_prob']} %), wind up to {d['wind_kmh']} km/h")
    if soil is not None:
        lines.append(f"SOIL MOISTURE 3-9 cm (model estimate, next-24h average): {soil} m3/m3 (no verified dry/wet threshold exists for it: state the number only, do not call it low, high, dry or wet)")
    deeper = [f"{lab} {profile[k]}" for k, lab in (("moisture_9_27cm", "9-27 cm"), ("moisture_27_81cm", "27-81 cm")) if k in profile]
    if deeper:
        lines.append("SOIL MOISTURE DEEPER (root zone, model estimate, next-24h average): " + ", ".join(deeper) + " m3/m3. The surface layer dries first and the deeper layers hold the water roots use, so report all layers, never only the surface one, and do not call the soil dry or wet.")
    temps = [f"{lab} {profile[k]} C" for k, lab in (("temp_6cm_c", "6 cm"), ("temp_18cm_c", "18 cm")) if k in profile]
    if temps:
        lines.append("SOIL TEMPERATURE (model estimate, next-24h average): " + ", ".join(temps))
    if a["flags"]:
        for fl in a["flags"]:
            lines.append(f"RISK FLAG {fl['flag']} on {fl['day']}: {fl['value']} {fl['unit']} ({fl['rule']})")
    else:
        lines.append("RISK FLAGS: none in the next 7 days")
    lines.append("SPRAY-SAFE DAYS (wind <= 15 km/h, rain chance <= 40 %, rain < 2.5 mm): " + (", ".join(a["spray_ok_days"]) or "none"))
    lines.append(f"IRRIGATION: rain expected in next 48 h = {a['rain_next_48h_mm']} mm -> {a['irrigation']} (applies to a growing crop; it does not apply to a crop that is mature or being harvested, and the crop stage is not known here)")
    wb = a["water_balance"]
    if wb:
        lines.append(
            f"WATER BALANCE next {wb['days']} days: forecast rain {wb['rain_mm']} mm vs reference crop water demand (ET0, grass reference, not your crop's exact need) {wb['et0_mm']} mm "
            f"-> {wb['label']} (rain minus demand = {wb['balance_mm']} mm)"
        )
    if a["dry_spell"]:
        lines.append("DRY SPELL: no rainy day (>= 2.5 mm) in the next 7 days")

    card = {
        "type": "forecast",
        "title": f"7-day forecast - {where}",
        "days": [{"date": d["date"], "tmax": d["tmax"], "tmin": d["tmin"], "rain_mm": d["rain_mm"], "rain_prob": d["rain_prob"]} for d in days],
        "flags": [{"flag": x["flag"], "day": x["day"]} for x in a["flags"]],
        "spray_ok_days": a["spray_ok_days"],  # deterministic rule from weather_rules: the UI shows it, never recomputes it
        "rain_next_48h_mm": a["rain_next_48h_mm"],
        "irrigation": a["irrigation"],
        "soil_moisture": soil,
        "soil_profile": profile,
    }
    return ToolResult("\n".join(lines), True, sources, [card], {"location": {k: loc[k] for k in ("name", "state", "district", "lat", "lon")}, "analysis": a, "soil_moisture": soil, "soil_profile": profile, "days": days})


weather = guarded("weather")(lambda text, profile: get_weather(profile))
