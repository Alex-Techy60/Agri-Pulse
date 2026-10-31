"""Place name -> lat/lon/state/district via Open-Meteo's free geocoding API (live, no key)."""
from __future__ import annotations

from app.tools import NeedsInput, PlaceNotFound
from app.tools.http import get_json

GEO_URL = "https://geocoding-api.open-meteo.com/v1/search"
GEO_GET_URL = "https://geocoding-api.open-meteo.com/v1/get"

# The geocoder only matches a native-script name when `language` is that script's language (verified live on 31 Oct 2026:
# "नाशिक" finds Nashik with language=mr and nothing with en/hi; "लुधियाना" works with hi). Devanagari is tried as
# Marathi, then Hindi. Results then carry native-script state/district names, so the chosen place is re-read in English
# by id: the mandi and weather tools are keyed on English names.
SCRIPT_LANGS = [
    ("\u0900", "\u097f", ["mr", "hi"]), ("\u0a80", "\u0aff", ["gu"]), ("\u0a00", "\u0a7f", ["pa"]), ("\u0b80", "\u0bff", ["ta"]),
    ("\u0c00", "\u0c7f", ["te"]), ("\u0c80", "\u0cff", ["kn"]), ("\u0980", "\u09ff", ["bn"]), ("\u0d00", "\u0d7f", ["ml"]),
]


def _search_langs(query: str) -> list[str]:
    for lo, hi, langs in SCRIPT_LANGS:
        if any(lo <= ch <= hi for ch in query):
            return langs
    return ["en"]


# Indian states / UTs, lower-case, including common alternative spellings. If the farmer TYPES one of these, results from
# other states must never be used silently (e.g. "Ahmednagar, Maharashtra" must not become Himatnagar, Gujarat).
INDIA_STATES = {
    "andhra pradesh", "arunachal pradesh", "assam", "bihar", "chhattisgarh", "chattisgarh", "goa", "gujarat", "haryana",
    "himachal pradesh", "jharkhand", "karnataka", "kerala", "keralam", "madhya pradesh", "maharashtra", "manipur",
    "meghalaya", "mizoram", "nagaland", "odisha", "orissa", "punjab", "rajasthan", "sikkim", "tamil nadu", "telangana",
    "tripura", "uttar pradesh", "uttarakhand", "uttaranchal", "west bengal", "delhi", "new delhi", "puducherry",
    "pondicherry", "chandigarh", "ladakh", "jammu and kashmir", "andaman and nicobar islands", "lakshadweep",
}


# Words that say nothing about WHICH place: "Pune district", "Khed taluka", "Nashik, India".
FILLER = {"india", "district", "dist", "tehsil", "taluka", "taluk", "tal", "village", "city"}


# Names farmers still type -> the name the geocoder actually knows. Each target was checked live on 31 Oct 2026 and
# returns the right state ("Gurgaon" alone otherwise resolves to a village in Hingoli, Maharashtra; "Panaji" has no Goa entry).
GEO_NAMES = {
    "ahmednagar": "Ahilyanagar", "panaji": "Panjim", "bangalore": "Bengaluru", "allahabad": "Prayagraj", "gurgaon": "Gurugram",
    # District names the geocoder does not list (checked live 31 Oct 2026): the district's own town, or the old name.
    "buldhana": "Buldana", "raigad": "Alibag", "chhatrapati sambhajinagar": "Aurangabad", "sambhajinagar": "Aurangabad",
}


# Maharashtra districts and big cities as farmers write them in Marathi/Hindi -> the English name the geocoder knows.
# Needed because the geocoder lacks many native spellings (checked live 31 Oct 2026: Satara, Sangli, Indore returned nothing).
NATIVE_PLACES = {
    "अहिल्यानगर": "Ahilyanagar", "अहमदनगर": "Ahilyanagar", "अकोला": "Akola", "अमरावती": "Amravati", "छत्रपती संभाजीनगर": "Aurangabad", "बीड": "Beed",
    "भंडारा": "Bhandara", "बुलढाणा": "Buldana", "चंद्रपूर": "Chandrapur", "धुळे": "Dhule", "गडचिरोली": "Gadchiroli", "गोंदिया": "Gondia",
    "हिंगोली": "Hingoli", "जळगाव": "Jalgaon", "जालना": "Jalna", "मुंबई": "Mumbai", "नांदेड": "Nanded", "नंदुरबार": "Nandurbar",
    "धाराशिव": "Dharashiv", "उस्मानाबाद": "Dharashiv", "पालघर": "Palghar", "परभणी": "Parbhani", "रायगड": "Alibag", "रत्नागिरी": "Ratnagiri",
    "सांगली": "Sangli", "सातारा": "Satara", "सिंधुदुर्ग": "Sindhudurg", "ठाणे": "Thane", "वर्धा": "Wardha", "वाशीम": "Washim", "यवतमाळ": "Yavatmal",
    "लासलगाव": "Lasalgaon", "मालेगाव": "Malegaon", "बारामती": "Baramati", "पंढरपूर": "Pandharpur", "कराड": "Karad", "शिर्डी": "Shirdi", "सिन्नर": "Sinnar",
    "इंदौर": "Indore", "भोपाल": "Bhopal", "लखनऊ": "Lucknow", "पटना": "Patna", "अमृतसर": "Amritsar", "चंडीगढ़": "Chandigarh", "दिल्ली": "Delhi",
    "अहमदाबाद": "Ahmedabad", "हैदराबाद": "Hyderabad", "बेंगलुरु": "Bengaluru", "जयपुर": "Jaipur", "आगरा": "Agra", "लुधियाना": "Ludhiana",
}


def _district_hints(rest: list[str]) -> list[str]:
    """Typed parts that are neither a state nor filler: the district/town the farmer named."""
    hints = []
    for t in rest:
        if t in INDIA_STATES:
            continue
        words = [w for w in t.split() if w not in FILLER]
        if words:
            hints.append(" ".join(words))
    return hints


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
    query = " ".join(w for w in parts[0].split() if w.lower() not in FILLER) or parts[0]  # "Raipur district" -> "Raipur"
    query = NATIVE_PLACES.get(query, GEO_NAMES.get(query.lower(), query))
    results, f = [], None
    for lang in _search_langs(query):
        f = get_json(GEO_URL, {"name": query, "count": 10, "language": lang, "format": "json", "countryCode": "IN"}, ttl=86400)
        results = (f.data or {}).get("results") or [] if isinstance(f.data, dict) else []
        if results:
            break
    if not results:
        raise PlaceNotFound(place)
    rest = [p.lower() for p in parts[1:]]
    if parts[0] in NATIVE_PLACES:  # searched under the English name: a Devanagari state/district hint cannot match English records
        rest = [p for p in rest if p.isascii()]
    # The geocoder orders by name match, not importance: "Panaji" returns a Gujarat village before Goa's capital and
    # "Ahmednagar" a Gujarat town before the Maharashtra city. Rank by state/district hint first, then by population.
    best = max(results, key=lambda r: (_score(r, rest), r.get("population") or 0))
    wanted = [t for t in rest if t in INDIA_STATES]
    if wanted and not any(w in (best.get("admin1") or "").lower() for w in wanted):
        raise PlaceNotFound(f"{parts[0]} in {', '.join(wanted)}: the place finder has no match there; ask for the nearest bigger town or the district name")
    # Same rule for a typed district: "Sawantwadi, Sindhudurg" must not become the only Sawantwadi the geocoder knows
    # (a village in Latur): that would give the farmer another district's weather and prices without a word.
    hints = _district_hints(rest)
    where = f"{best.get('admin1', '')} {best.get('admin2', '')} {best.get('name', '')}".lower()
    if hints and not any(h in where for h in hints):
        raise PlaceNotFound(f"{parts[0]} in {', '.join(hints)}: the place finder only knows {parts[0]} in {best.get('admin2') or best.get('admin1')}; ask for the nearest bigger town")
    if _search_langs(query) != ["en"]:  # native-script hit: take the English names of the same place
        g = get_json(GEO_GET_URL, {"id": best["id"], "language": "en", "format": "json"}, ttl=86400)
        if not isinstance(g.data, dict) or not g.data.get("admin1"):
            raise PlaceNotFound(f"{parts[0]}: the place finder has no English record for it; ask for the nearest bigger town")
        best, f = {**best, **{k: g.data.get(k) for k in ("name", "admin1", "admin2")}}, g
    return {
        "name": best.get("name", parts[0]),
        "state": best.get("admin1", ""),
        "district": best.get("admin2", ""),
        "lat": best["latitude"],
        "lon": best["longitude"],
        "source": {"name": "Open-Meteo geocoding", "url": f.url, "fetched_at": f.fetched_at, "stale": f.stale},
    }
