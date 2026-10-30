"""Tools with the network replaced by response-SHAPE fixtures (tests only; never used by the app)."""
import datetime as dt

import app.tools.location as location
import app.tools.mandi as mandi_mod
import app.tools.weather as weather_mod
from app.core.config import Settings
from app.tools import NeedsInput, PlaceNotFound
from app.tools.http import Fetched

GEO = {"results": [{"name": "Nashik", "latitude": 19.99, "longitude": 73.78, "admin1": "Maharashtra", "admin2": "Nashik", "country_code": "IN"}]}


def forecast(n=7, rain=None):
    rain = rain or [0.0] * n
    return {
        "current": {"temperature_2m": 28.0, "relative_humidity_2m": 60, "wind_speed_10m": 9.0},
        "daily": {
            "time": [f"2026-11-{i + 1:02d}" for i in range(n)],
            "temperature_2m_max": [33.0] * n, "temperature_2m_min": [20.0] * n, "precipitation_sum": rain,
            "precipitation_probability_max": [10] * n, "wind_speed_10m_max": [9.0] * n, "et0_fao_evapotranspiration": [4.0] * n,
        },
        "hourly": {"soil_moisture_3_to_9cm": [0.21] * 48},
    }


def mandi_records(day_price):
    out = []
    for date, prices in day_price.items():
        for i, p in enumerate(prices):
            out.append({"State": "Maharashtra", "District": "Nashik" if i == 0 else "Pune", "Market": f"M{i}", "Commodity": "Onion", "Arrival_Date": date, "Min_Price": p - 100, "Max_Price": p + 100, "Modal_Price": p})
    return out


def install(monkey_routes, key="k"):
    """monkey_routes: fn(url, params) -> data. Patches get_json in every tool module + settings."""
    def fake(url, params=None, ttl=None, timeout=None):
        return Fetched(monkey_routes(url, params or {}), url, "2026-11-01T10:00:00Z", False, 0)

    for m in (location, weather_mod, mandi_mod):
        m.get_json = fake
    mandi_mod.get_settings = lambda: Settings(data_gov_api_key=key)


def routes_ok(url, params):
    if "geocoding" in url:
        return GEO
    if "open-meteo" in url:
        return forecast(rain=[0, 70.0, 0, 0, 0, 0, 0])
    if "data.gov.in" in url:  # behaves like the live API: lower-case filters work, Title-case match nothing, date filter ignored
        if "filters[state]" not in params:
            return {"records": []}
        today = dt.date.today()
        recs = []
        for off, prices in {0: [2400, 2600], 1: [2000], 2: [2000], 3: [2000]}.items():  # history shape, in case the source ever returns it
            recs += mandi_records({(today - dt.timedelta(days=off)).strftime("%d/%m/%Y"): prices})
        return {"records": recs}
    raise AssertionError(url)


def test_weather_tool_builds_facts_cards_sources():
    install(routes_ok)
    r = weather_mod.weather("", {"place": "Nashik, Maharashtra"})
    assert r.ok and "RISK FLAG HEAVY_RAIN on 2026-11-02: 70.0 mm" in r.text
    assert "SOIL MOISTURE" in r.text and r.cards[0]["type"] == "forecast"
    assert r.facts["location"]["state"] == "Maharashtra" and any(s["name"] == "Open-Meteo forecast" for s in r.sources)


def test_tools_ask_for_missing_input():
    install(routes_ok)
    for fn in (weather_mod.weather, mandi_mod.mandi):
        try:
            fn("", {})
            raise AssertionError("expected NeedsInput")
        except NeedsInput as e:
            assert e.field == "place"
    try:
        mandi_mod.mandi("", {"place": "Nashik"})
        raise AssertionError("expected NeedsInput")
    except NeedsInput as e:
        assert e.field == "crop"


def test_mandi_without_key_is_explicit_failure_not_fake_data():
    install(routes_ok, key="")
    r = mandi_mod.mandi("", {"place": "Nashik", "crop": "onion"})
    assert not r.ok and "SOURCE UNAVAILABLE" in r.text and "DATA_GOV_API_KEY" in r.text and "Do NOT guess" in r.text


def test_mandi_tool_signal_and_markets_with_lower_case_filters():
    install(routes_ok)
    r = mandi_mod.mandi("", {"place": "Nashik", "crop": "onion"})
    assert r.ok and "SIGNAL (computed in code): SELL_NOW" in r.text and "MARKETS in Nashik" in r.text
    assert r.facts["commodity"] == "Onion" and r.facts["price"]["signal"] in {"SELL_NOW", "NEUTRAL", "HOLD", "INSUFFICIENT_DATA"}
    assert r.cards[0]["type"] == "prices" and r.cards[0]["unit"] == "Rs/quintal"


def test_mandi_no_records_says_so():
    install(lambda url, p: GEO if "geocoding" in url else {"records": []})
    r = mandi_mod.mandi("", {"place": "Nashik", "crop": "onion"})
    assert r.ok and "no published records" in r.text and "do not estimate" in r.text


def test_cross_check_tool():
    install(routes_ok)
    r = mandi_mod.cross("", {"place": "Nashik", "crop": "onion"})
    assert r.ok and r.text.startswith("DECISION (computed in code)") and r.facts["decision"] in {"SELL_NOW", "HOLD", "NEUTRAL", "INSUFFICIENT_DATA"}


def test_place_not_found_is_graceful():
    install(lambda url, p: {"results": []})
    r = weather_mod.weather("", {"place": "Nowhereville"})
    assert not r.ok and "place not found" in r.text


def test_mandi_district_without_markets_falls_back_to_state_and_says_so():
    # Records exist for Maharashtra but none in the farmer's district (Satara): state-level markets + an explicit note.
    def routes(url, params):
        if "geocoding" in url:
            return {"results": [{"name": "Satara", "latitude": 17.7, "longitude": 74.0, "admin1": "Maharashtra", "admin2": "Satara", "country_code": "IN"}]}
        if "filters[state]" not in params:
            return {"records": []}
        return {"records": mandi_records({dt.date.today().strftime("%d/%m/%Y"): [2000, 2100, 2200]})}

    install(routes)
    r = mandi_mod.mandi("", {"place": "Satara", "crop": "onion"})
    assert r.ok and "NOTE: no markets reporting Onion in Satara" in r.text and "HIGHEST MARKETS in Maharashtra" in r.text
    assert "MARKETS in Satara" not in r.text and r.cards[0]["markets"]


def test_mandi_single_day_source_gives_market_position_and_honest_no_trend():
    def routes(url, params):
        if "geocoding" in url:
            return GEO
        if "filters[state]" not in params:
            return {"records": []}
        d = dt.date.today().strftime("%d/%m/%Y")
        return {"records": mandi_records({d: [3000, 2000, 2200, 2400]})}  # i==0 is Nashik (3000); others Pune

    install(routes)
    r = mandi_mod.mandi("", {"place": "Nashik", "crop": "onion"})
    assert r.ok and r.facts["price"]["signal"] == "INSUFFICIENT_DATA" and "trend is not available" in r.text
    pos = r.facts["position"]
    assert pos["state_median"] == 2300 and pos["local_median"] == 3000 and pos["label"] == "ABOVE_STATE_MEDIAN" and pos["best_price"] == 3000
    assert "MARKET POSITION" in r.text and "ABOVE_STATE_MEDIAN" in r.text and r.cards[0]["position"] == pos


def test_mandi_fetches_once_not_per_day():
    calls = []

    def routes(url, params):
        if "geocoding" in url:
            return GEO
        calls.append(params)
        return {"records": mandi_records({dt.date.today().strftime("%d/%m/%Y"): [2000, 2100, 2200]})}

    install(routes)
    mandi_mod.mandi("", {"place": "Nashik", "crop": "onion"})
    assert len(calls) == 1 and "filters[state]" in calls[0] and "filters[commodity]" in calls[0] and not any("arrival_date" in k.lower() for k in calls[0])


def test_title_case_filter_fallback_still_works_if_lower_matches_nothing():
    def routes(url, params):
        if "geocoding" in url:
            return GEO
        if "filters[State]" not in params:
            return {"records": []}
        return {"records": mandi_records({dt.date.today().strftime("%d/%m/%Y"): [2000, 2100, 2200]})}

    install(routes)
    assert mandi_mod.mandi("", {"place": "Nashik", "crop": "onion"}).ok


def test_crop_is_found_as_a_whole_word_only():
    # "price" contains "rice" and "turmeric" contains "tur": neither may pick a crop by accident.
    for text in ("what is the price today", "any turmeric rates", "saturday market"):
        pick = None
        try:
            pick = mandi_mod.commodity_name({}, text)
        except NeedsInput:
            pick = "ASK"
        assert pick in ("ASK", "Turmeric"), (text, pick)
    try:
        mandi_mod.commodity_name({}, "what is the price today")
        raise AssertionError("expected NeedsInput")
    except NeedsInput as e:
        assert e.field == "crop"
    assert mandi_mod.commodity_name({}, "onion rates in nashik") == "Onion" and mandi_mod.commodity_name({}, "tur dal rate") == "Red gram/Arhar/Tur(whole)"


def test_aliases_use_names_verified_in_the_real_dataset():
    a = mandi_mod.ALIASES
    assert a["paddy"] == "Paddy(Common)" and a["onion"] == "Onion" and a["moong"] == "Green Gram(Moong)(Whole)" and a["chilli"] == "Green Chilli"
    assert "sugarcane" not in a  # no such commodity in the dataset


def test_loose_commodity_filter_results_are_cut_to_exact_matches():
    # Real behaviour (30 Oct 2026): filters[commodity]=Onion also returns 'Onion Green'; 'Potato' returns 'Sweet Potato'.
    today = dt.date.today().strftime("%d/%m/%Y")
    base = {"State": "Maharashtra", "District": "Pune", "Variety": "Other", "Grade": "Local", "Arrival_Date": today}
    loose = [
        {**base, "Market": "A", "Commodity": "Onion", "Min_Price": 3500, "Max_Price": 4000, "Modal_Price": 3800},
        {**base, "Market": "B", "Commodity": "Onion ", "Min_Price": 3500, "Max_Price": 4000, "Modal_Price": 3900},
        {**base, "Market": "C", "Commodity": "Onion Green", "Min_Price": 8, "Max_Price": 10, "Modal_Price": 9},
        {**base, "Market": "D", "Commodity": "onion", "Min_Price": 3600, "Max_Price": 4100, "Modal_Price": 3700},
    ]

    def routes(url, params):
        if "geocoding" in url:
            return GEO
        return {"records": loose, "total": len(loose)} if "filters[state]" in params else {"records": []}

    install(routes)
    r = mandi_mod.mandi("", {"place": "Nashik", "crop": "onion"})
    assert r.ok and "Onion Green" not in r.text
    assert r.facts["position"]["markets"] == 3 and r.facts["position"]["state_median"] == 3800  # Rs 9 never enters the median


def test_nothing_exact_means_honest_no_records():
    today = dt.date.today().strftime("%d/%m/%Y")
    only_loose = [{"State": "Maharashtra", "District": "Pune", "Market": "C", "Commodity": "Sweet Potato", "Variety": "x", "Grade": "y", "Arrival_Date": today, "Min_Price": 1, "Max_Price": 2, "Modal_Price": 2000}]

    def routes(url, params):
        return GEO if "geocoding" in url else {"records": only_loose, "total": 1}

    install(routes)
    r = mandi_mod.mandi("", {"place": "Nashik", "crop": "potato"})
    assert r.ok and "no published records" in r.text and "do not estimate" in r.text


def test_results_are_paged_until_total_is_reached():
    today = dt.date.today().strftime("%d/%m/%Y")
    rec = lambda i: {"State": "Maharashtra", "District": "Pune", "Market": f"M{i}", "Commodity": "Onion", "Variety": "x", "Grade": "y", "Arrival_Date": today, "Min_Price": 1000, "Max_Price": 3000, "Modal_Price": 2000 + i}
    seen_offsets = []

    def routes(url, params):
        if "geocoding" in url:
            return GEO
        off = int(params["offset"])
        seen_offsets.append(off)
        return {"records": [rec(i) for i in range(off, min(off + 500, 700))], "total": 700}

    install(routes)
    r = mandi_mod.mandi("", {"place": "Nashik", "crop": "onion"})
    assert seen_offsets == [0, 500] and r.facts["position"]["markets"] == 700


def test_state_names_are_translated_to_the_dataset_spelling():
    for geo, data in [("Kerala", "Keralam"), ("Chhattisgarh", "Chattisgarh"), ("National Capital Territory of Delhi", "NCT of Delhi"), ("Puducherry", "Pondicherry"), ("Maharashtra", "Maharashtra"), ("Sikkim", "Sikkim")]:
        assert mandi_mod.agmarknet_state(geo) == data


def test_kerala_farmer_queries_keralam_and_gets_records():
    asked = []

    def routes(url, params):
        if "geocoding" in url:
            return {"results": [{"name": "Kochi", "latitude": 9.9, "longitude": 76.2, "admin1": "Kerala", "admin2": "Ernakulam District", "country_code": "IN"}]}
        asked.append(params.get("filters[state]"))
        rec = lambda i: {"State": "Keralam", "District": "Ernakulam", "Market": f"M{i}", "Commodity": "Banana", "Variety": "x", "Grade": "y", "Arrival_Date": dt.date.today().strftime("%d/%m/%Y"), "Min_Price": 3000, "Max_Price": 4000, "Modal_Price": 3500 + i}
        return {"records": [rec(i) for i in range(4)], "total": 4} if params.get("filters[state]") == "Keralam" else {"records": []}

    install(routes)
    r = mandi_mod.mandi("", {"place": "Kochi", "crop": "banana"})
    assert asked[0] == "Keralam" and r.ok and r.facts["position"]["markets"] == 4
    assert r.facts["position"]["label"] in {"NEAR_STATE_MEDIAN", "ABOVE_STATE_MEDIAN", "BELOW_STATE_MEDIAN"}  # 'Ernakulam District' matched 'Ernakulam'


def test_geocoder_picks_the_most_populous_match_when_no_state_is_given():
    import app.tools.location as loc_mod

    results = [
        {"name": "Panaji", "latitude": 22.0, "longitude": 73.0, "admin1": "Gujarat", "admin2": "Kheda district", "population": 0},
        {"name": "Panaji", "latitude": 15.5, "longitude": 73.8, "admin1": "Goa", "admin2": "North Goa", "population": 114759},
    ]
    install(lambda url, p: {"results": results})
    assert loc_mod.resolve_location({"place": "Panaji"})["state"] == "Goa"
    assert loc_mod.resolve_location({"place": "Panaji, Gujarat"})["state"] == "Gujarat"  # an explicit state still wins


def test_a_state_the_farmer_typed_is_never_silently_replaced_by_another_state():
    import app.tools.location as loc_mod

    only_gujarat = [{"name": "Himatnagar", "latitude": 23.6, "longitude": 72.9, "admin1": "Gujarat", "admin2": "Sabar Kantha", "population": 81137}]
    install(lambda url, p: {"results": only_gujarat})
    try:
        loc_mod.resolve_location({"place": "Ahmednagar, Maharashtra"})
        raise AssertionError("expected PlaceNotFound")
    except PlaceNotFound as e:
        assert "maharashtra" in str(e).lower()
    assert loc_mod.resolve_location({"place": "Ahmednagar"})["state"] == "Gujarat"  # no state typed: first/most populous match
    assert loc_mod.resolve_location({"place": "Himatnagar, India"})["state"] == "Gujarat"  # 'India' is not a state: no rejection
    r = weather_mod.weather("", {"place": "Ahmednagar, Maharashtra"})
    assert not r.ok and "place not found" in r.text
