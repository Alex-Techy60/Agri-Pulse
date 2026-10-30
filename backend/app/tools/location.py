"""Place name -> lat/lon/state/district via Open-Meteo's free geocoding API (live, no key)."""
from __future__ import annotations

from app.tools import NeedsInput, PlaceNotFound
from app.tools.http import get_json

GEO_URL = "https://geocoding-api.open-meteo.com/v1/search"


# Indian states / UTs, lower-case, including common alternative spellings. If the farmer TYPES one of these, results from
# other states must never be used silently (e.g. "Ahmednagar, Maharashtra" must not become Himatnagar, Gujarat).
INDIA_STATES = {
    "andhra pradesh", "arunachal pradesh", "assam", "bihar", "chhattisgarh", "chattisgarh", "goa", "gujarat", "haryana",
    "himachal pradesh", "jharkhand", "karnataka", "kerala", "keralam", "madhya pradesh", "maharashtra", "manipur",
    "meghalaya", "mizoram", "nagaland", "odisha", "orissa", "punjab", "rajasthan", "sikkim", "tamil nadu", "telangana",
    "tripura", "uttar pradesh", "uttarakhand", "uttaranchal", "west bengal", "delhi", "new delhi", "puducherry",
    "pondicherry", "chandigarh", "ladakh", "jammu and kashmir", "andaman and nicobar islands", "lakshadweep",
}


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
    # The geocoder orders by name match, not importance: "Panaji" returns a Gujarat village before Goa's capital and
    # "Ahmednagar" a Gujarat town before the Maharashtra city. Rank by state/district hint first, then by population.
    best = max(results, key=lambda r: (_score(r, rest), r.get("population") or 0))
    wanted = [t for t in rest if t in INDIA_STATES]
    if wanted and not any(w in (best.get("admin1") or "").lower() for w in wanted):
        raise PlaceNotFound(f"{parts[0]} in {', '.join(wanted)}: the place finder has no match there; ask for the nearest bigger town or the district name")
    return {
        "name": best.get("name", parts[0]),
        "state": best.get("admin1", ""),
        "district": best.get("admin2", ""),
        "lat": best["latitude"],
        "lon": best["longitude"],
        "source": {"name": "Open-Meteo geocoding", "url": f.url, "fetched_at": f.fetched_at, "stale": f.stale},
    }
