"""Live weather + soil moisture for the farm location (Open-Meteo, free, no key)."""
from __future__ import annotations

from app.decision.weather_rules import analyze, days_from_daily
from app.tools import ToolResult, guarded
from app.tools.http import get_json
from app.tools.location import resolve_location

FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
DAILY = "temperature_2m_max,temperature_2m_min,precipitation_sum,precipitation_probability_max,wind_speed_10m_max,et0_fao_evapotranspiration"


def _soil_moisture(hourly: dict) -> float | None:
    vals = [v for v in (hourly.get("soil_moisture_3_to_9cm") or [])[:24] if v is not None]
    return round(sum(vals) / len(vals), 3) if vals else None


def get_weather(profile: dict) -> ToolResult:
    loc = resolve_location(profile)
    f = get_json(
        FORECAST_URL,
        {
            "latitude": loc["lat"],
            "longitude": loc["lon"],
            "daily": DAILY,
            "hourly": "soil_moisture_3_to_9cm",
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
    src = {"name": "Open-Meteo forecast", "url": f.url, "fetched_at": f.fetched_at, "stale": f.stale}
    sources = [src] + ([loc["source"]] if loc.get("source") else [])

    where = f"{loc['name']}, {loc['state']}".strip(", ")
    lines = [f"WEATHER for {where} ({loc['lat']}, {loc['lon']}) - Open-Meteo, fetched {f.fetched_at}" + (f" [STALE: {f.age_s}s old]" if f.stale else "")]
    if cur:
        lines.append(f"Now: {cur.get('temperature_2m')} C, humidity {cur.get('relative_humidity_2m')} %, wind {cur.get('wind_speed_10m')} km/h")
    for d in days:
        lines.append(f"{d['date']}: max {d['tmax']} C, min {d['tmin']} C, rain {d['rain_mm']} mm (chance {d['rain_prob']} %), wind up to {d['wind_kmh']} km/h")
    if soil is not None:
        lines.append(f"SOIL MOISTURE 3-9 cm (model estimate, next-24h average): {soil} m3/m3")
    if a["flags"]:
        for fl in a["flags"]:
            lines.append(f"RISK FLAG {fl['flag']} on {fl['day']}: {fl['value']} {fl['unit']} ({fl['rule']})")
    else:
        lines.append("RISK FLAGS: none in the next 7 days")
    lines.append("SPRAY-SAFE DAYS (wind <= 15 km/h, rain chance <= 40 %, rain < 2.5 mm): " + (", ".join(a["spray_ok_days"]) or "none"))
    lines.append(f"IRRIGATION: rain expected in next 48 h = {a['rain_next_48h_mm']} mm -> {a['irrigation']}")
    if a["dry_spell"]:
        lines.append("DRY SPELL: no rainy day (>= 2.5 mm) in the next 7 days")

    card = {
        "type": "forecast",
        "title": f"7-day forecast - {where}",
        "days": [{"date": d["date"], "tmax": d["tmax"], "tmin": d["tmin"], "rain_mm": d["rain_mm"], "rain_prob": d["rain_prob"]} for d in days],
        "flags": [{"flag": x["flag"], "day": x["day"]} for x in a["flags"]],
        "soil_moisture": soil,
    }
    return ToolResult("\n".join(lines), True, sources, [card], {"location": {k: loc[k] for k in ("name", "state", "district", "lat", "lon")}, "analysis": a, "soil_moisture": soil, "days": days})


weather = guarded("weather")(lambda text, profile: get_weather(profile))
