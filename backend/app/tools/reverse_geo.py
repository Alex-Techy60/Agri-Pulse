"""Coordinates -> a place name the other tools understand, from OpenStreetMap Nominatim (live, no key).

Lets a farmer who cannot type a village name tap "use my location". Nominatim gives the district and state reliably, and the
village or town when OpenStreetMap has one. Each candidate name is checked against the forward geocoder the weather and mandi
tools use, so the place handed back is one they can resolve; when the village is unknown the taluka, then the district, is used.
Coordinates are used for this one lookup only: they are not stored and not logged."""
from __future__ import annotations

from app.tools import PlaceNotFound
from app.tools.http import get_json
from app.tools.location import clean_admin_name, resolve_location

NOMINATIM_URL = "https://nominatim.openstreetmap.org/reverse"
INDIA = (6.0, 38.0, 68.0, 98.5)  # lat_min, lat_max, lon_min, lon_max: a rough box, so a stray coordinate is not looked up
_clean = clean_admin_name


def locate(lat: float, lon: float) -> dict:
    """-> {place, name, state, district, source}. Raises PlaceNotFound (outside India / no usable name) or SourceUnavailable."""
    if not (INDIA[0] <= lat <= INDIA[1] and INDIA[2] <= lon <= INDIA[3]):
        raise PlaceNotFound("these coordinates are outside India")
    f = get_json(NOMINATIM_URL, {"format": "jsonv2", "lat": round(lat, 3), "lon": round(lon, 3), "zoom": 12, "addressdetails": 1, "accept-language": "en"}, ttl=86400)
    addr = (f.data.get("address") if isinstance(f.data, dict) else None) or {}
    if addr.get("country_code") != "in":
        raise PlaceNotFound("these coordinates are not in India")
    state, district = addr.get("state", ""), _clean(addr.get("state_district") or addr.get("county"))
    names, seen = [], set()
    for key in ("village", "town", "city", "suburb", "municipality", "county"):  # most local first
        n = _clean(addr.get(key))
        if n and n.lower() not in seen and n.lower() != district.lower():
            seen.add(n.lower())
            names.append(n)
    candidates = [f"{n}, {district}, {state}" if district else f"{n}, {state}" for n in names] + ([f"{district}, {state}"] if district else [])
    for cand in candidates:
        try:
            loc = resolve_location({"place": cand})
        except PlaceNotFound:
            continue
        return {"place": cand, "name": loc["name"], "state": loc["state"], "district": loc["district"],
                "source": {"name": "OpenStreetMap Nominatim", "url": NOMINATIM_URL, "fetched_at": f.fetched_at, "stale": f.stale}}
    raise PlaceNotFound("no place name for these coordinates could be matched")
