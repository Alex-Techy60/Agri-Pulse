"""FAO-56 crop water need: stage timing, Kc ramps, the 7-day balance, and the crop_stage tool. No network."""
import datetime as dt
from types import SimpleNamespace

import app.tools.crop_stage as cs
from app.decision.crop_water import CROPS, crop_water_need, parse_sowing, stage_at
from app.tools import ToolResult

SOW = dt.date(2026, 10, 1)  # onion, dry: ini 15, dev 25, mid 70, late 40 (total 150)


def on(days_after):
    return SOW + dt.timedelta(days=days_after)


def test_onion_stage_boundaries_follow_fao56_stage_lengths():
    assert stage_at("onion", SOW, on(0))["stage"] == "initial"
    assert stage_at("onion", SOW, on(14))["stage"] == "initial"  # last of the 15 initial days
    assert stage_at("onion", SOW, on(15))["stage"] == "development"
    assert stage_at("onion", SOW, on(39))["stage"] == "development"  # last of the 25 development days
    assert stage_at("onion", SOW, on(40))["stage"] == "mid_season"
    assert stage_at("onion", SOW, on(109))["stage"] == "mid_season"  # 15 + 25 + 70 = 110 days before late season
    assert stage_at("onion", SOW, on(110))["stage"] == "late_season"
    assert stage_at("onion", SOW, on(149))["stage"] == "late_season"
    assert stage_at("onion", SOW, on(150))["stage"] == "cycle_complete"


def test_kc_ramps_linearly_and_lands_on_the_fao56_values():
    assert stage_at("onion", SOW, on(0))["kc"] == 0.7
    assert stage_at("onion", SOW, on(39))["kc"] == 1.05  # development ends at the mid value
    assert stage_at("onion", SOW, on(60))["kc"] == 1.05
    assert stage_at("onion", SOW, on(110))["kc"] == 1.04  # first late day: 1.05 - 0.30 / 40
    assert stage_at("onion", SOW, on(149))["kc"] == 0.75  # late season ends at the end value


def test_before_sowing_and_after_the_cycle_need_no_water_figure():
    assert stage_at("onion", SOW, on(-3))["stage"] == "not_sown"
    assert stage_at("onion", SOW, on(-3))["kc"] is None
    assert stage_at("onion", SOW, on(150))["kc"] is None


def test_every_crop_has_a_cited_table_row_and_consistent_kc_ordering():
    assert set(CROPS) == {"onion", "tomato", "soybean", "cotton", "wheat"}
    for name, c in CROPS.items():
        assert c["row"] and c["note"], name  # the row and the caveat are shown with every figure
        assert c["kc"]["ini"] <= c["kc"]["mid"] and c["kc"]["end"] <= c["kc"]["mid"], name
        assert all(v > 0 for v in c["stages"].values()), name
    assert stage_at("tomato", SOW, SOW) is not None and stage_at("unknown_crop", SOW, SOW) is None


def test_seven_day_balance_is_crop_kc_times_et0_against_rain():
    days = [{"date": (SOW + dt.timedelta(days=40 + i)).isoformat(), "et0_mm": 4.0, "rain_mm": 0.0} for i in range(7)]
    r = crop_water_need("onion", SOW, SOW + dt.timedelta(days=40), days)
    assert r["days"] == 7 and r["need_mm"] == 29.4  # 7 days x 1.05 x 4.0 mm
    assert r["rain_mm"] == 0.0 and r["balance_mm"] == -29.4 and r["label"] == "RAIN_SHORT_OF_CROP_NEED"
    assert r["source"].startswith("FAO-56")


def test_rain_that_covers_the_need_is_labelled_so():
    days = [{"date": (SOW + dt.timedelta(days=40 + i)).isoformat(), "et0_mm": 4.0, "rain_mm": 10.0} for i in range(7)]
    r = crop_water_need("onion", SOW, SOW + dt.timedelta(days=40), days)
    assert r["balance_mm"] > 0 and r["label"] == "RAIN_COVERS_CROP_NEED"


def test_a_day_with_missing_values_is_left_out_not_counted_as_zero():
    days = [
        {"date": (SOW + dt.timedelta(days=40)).isoformat(), "et0_mm": 4.0, "rain_mm": 0.0},
        {"date": (SOW + dt.timedelta(days=41)).isoformat(), "et0_mm": None, "rain_mm": 0.0},
    ]
    r = crop_water_need("onion", SOW, SOW + dt.timedelta(days=40), days)
    assert r["days"] == 1 and r["skipped"] == 1 and r["need_mm"] == 4.2


def test_no_usable_forecast_gives_no_number():
    r = crop_water_need("onion", SOW, SOW + dt.timedelta(days=40), [{"date": SOW.isoformat(), "et0_mm": None, "rain_mm": None}])
    assert r["days"] == 0 and r["need_mm"] is None and r["label"] is None


def test_sowing_date_must_be_iso_and_is_otherwise_treated_as_not_given():
    assert parse_sowing("2026-10-01") == SOW
    assert parse_sowing("01/10/2026") is None and parse_sowing(None) is None and parse_sowing(12) is None


def _forecast(start: dt.date, n: int = 7, et0=4.0, rain=0.0):
    return [{"date": (start + dt.timedelta(days=i)).isoformat(), "et0_mm": et0, "rain_mm": rain, "tmax": 31.0, "tmin": 19.0, "rain_prob": 10, "wind_kmh": 8.0} for i in range(n)]


def _fake_weather(days):
    return lambda profile: SimpleNamespace(facts={"location": {"state": "Maharashtra"}, "days": days})


def test_tool_gives_a_crop_water_card_when_a_sowing_date_is_known(monkeypatch):
    today = dt.date(2026, 11, 5)
    monkeypatch.setattr(cs, "get_weather", _fake_weather(_forecast(today)))
    r = cs.crop_stage("", {"place": "Nashik, Maharashtra", "crop": "Onion", "sowing_date": "2026-07-28"})
    assert r.ok and "CROP WATER (FAO-56, computed in code)" in r.text and "Kc today" in r.text
    card = next(c for c in r.cards if c["type"] == "crop_water")
    assert card["stage"] in ("mid_season", "development", "late_season") and card["source"].startswith("FAO-56")
    assert card["label"] in ("RAIN_COVERS_CROP_NEED", "RAIN_SHORT_OF_CROP_NEED") and "not tuned to Nashik" in r.text


def test_tool_asks_for_the_sowing_date_and_invents_nothing_without_it(monkeypatch):
    monkeypatch.setattr(cs, "get_weather", _fake_weather(_forecast(dt.date(2026, 11, 5))))
    r = cs.crop_stage("", {"place": "Nashik, Maharashtra", "crop": "Onion"})
    assert "no sowing date given" in r.text and "Ask the farmer" in r.text
    assert not any(c.get("type") == "crop_water" for c in r.cards)


def test_tool_reports_a_future_sowing_date(monkeypatch):
    monkeypatch.setattr(cs, "get_weather", _fake_weather(_forecast(dt.date(2026, 11, 5))))
    r = cs.crop_stage("", {"place": "Nashik, Maharashtra", "crop": "Onion", "sowing_date": "2026-12-01"})
    assert "to be sown on 2026-12-01" in r.text and "No crop water need yet" in r.text


def test_tool_passes_no_water_figure_for_a_crop_it_does_not_know(monkeypatch):
    monkeypatch.setattr(cs, "get_weather", _fake_weather(_forecast(dt.date(2026, 11, 5))))
    r = cs.crop_stage("", {"place": "Nashik, Maharashtra", "crop": "Grapes", "sowing_date": "2026-07-28"})
    assert not any(c.get("type") == "crop_water" for c in r.cards) and "CROP WATER" not in r.text
