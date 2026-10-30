"""Tools with the network replaced by response-SHAPE fixtures (tests only; never used by the app)."""
import datetime as dt

import app.tools.location as location
import app.tools.mandi as mandi_mod
import app.tools.weather as weather_mod
from app.core.config import Settings
from app.tools import NeedsInput
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
    if "data.gov.in" in url:  # price history: latest day higher than the earlier days
        d = params.get("filters[Arrival_Date]") or params.get("filters[arrival_date]")
        if "filters[State]" not in params:  # exercise the lower -> Title-case fallback
            return {"records": []}
        offset = (dt.date.today() - dt.datetime.strptime(d, "%d/%m/%Y").date()).days
        prices = {0: [2400, 2600], 1: [2000], 2: [2000], 3: [2000]}.get(offset, [])
        return {"records": mandi_records({d: prices}) if prices else []}
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


def test_mandi_tool_signal_markets_and_title_case_fallback():
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
        d = params.get("filters[Arrival_Date]") or params.get("filters[arrival_date]")
        if "filters[State]" not in params:
            return {"records": []}
        offset = (dt.date.today() - dt.datetime.strptime(d, "%d/%m/%Y").date()).days
        return {"records": mandi_records({d: [2000, 2100]})} if offset in (0, 1, 2) else {"records": []}

    install(routes)
    r = mandi_mod.mandi("", {"place": "Satara", "crop": "onion"})
    assert r.ok and "NOTE: no markets reporting Onion in Satara" in r.text and "HIGHEST MARKETS in Maharashtra" in r.text
    assert "MARKETS in Satara" not in r.text and r.cards[0]["markets"]
