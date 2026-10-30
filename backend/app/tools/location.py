"""Place name -> lat/lon/state/district via Open-Meteo's free geocoding API (live, no key)."""
from __future__ import annotations

from app.tools import NeedsInput, PlaceNotFound
from app.tools.http import get_json

GEO_URL = "https://geocoding-api.open-meteo.com/v1/search"


def _score(r: dict, rest: list[str]) -> int:
    hay = f"{r.get('admin1', '')} {r.get('admin2', '')}".lower()
    return sum(1 for t in rest if t and t in hay)


def resolve_location(profile: dict) -> dict:
    """Returns {name,state,district,lat,lon,source}. Raises NeedsInput / PlaceNotFound / SourceUnavailable."""
    if profile.get("lat") is not None and profile.get("lon") is not None and profile.get("state"):
        return {
            "name": profile.get("place") or "your location",
            "state": profile["state"],
            "district": profile.get("district", ""),
            "lat": float(profile["lat"]),
            "lon": float(profile["lon"]),
            "source": None,
        }
    place = (profile.get("place") or "").strip()
    if not place:
        raise NeedsInput("place", "the nearest town, village or district of the farm")
    parts = [p.strip() for p in place.split(",") if p.strip()]
    f = get_json(GEO_URL, {"name": parts[0], "count": 10, "language": "en", "format": "json", "countryCode": "IN"}, ttl=86400)
    results = (f.data or {}).get("results") or [] if isinstance(f.data, dict) else []
    if not results:
        raise PlaceNotFound(place)
    rest = [p.lower() for p in parts[1:]]
    best = max(results, key=lambda r: _score(r, rest)) if rest else results[0]
    return {
        "name": best.get("name", parts[0]),
        "state": best.get("admin1", ""),
        "district": best.get("admin2", ""),
        "lat": best["latitude"],
        "lon": best["longitude"],
        "source": {"name": "Open-Meteo geocoding", "url": f.url, "fetched_at": f.fetched_at, "stale": f.stale},
    }
