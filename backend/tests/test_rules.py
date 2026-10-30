from app.decision import price_rules as pr
from app.decision import weather_rules as wr
from app.guardrails.validators import forbid_patterns, grounded_numbers, max_words, numbers_in, numeric_limit, run_all


def daily(n=7, **over):
    base = {
        "time": [f"2026-11-{i + 1:02d}" for i in range(n)],
        "temperature_2m_max": [32.0] * n, "temperature_2m_min": [20.0] * n,
        "precipitation_sum": [0.0] * n, "precipitation_probability_max": [10] * n,
        "wind_speed_10m_max": [9.0] * n, "et0_fao_evapotranspiration": [4.0] * n,
    }
    base.update(over)
    return base


def test_weather_flags_and_windows():
    d = daily(precipitation_sum=[0, 70.0, 0, 0, 0, 0, 0], temperature_2m_max=[32, 32, 41, 32, 32, 32, 32], wind_speed_10m_max=[9, 9, 9, 22, 9, 9, 9])
    a = wr.analyze(wr.days_from_daily(d))
    kinds = {(f["flag"], f["day"]) for f in a["flags"]}
    assert ("HEAVY_RAIN", "2026-11-02") in kinds and ("HEAT_STRESS", "2026-11-03") in kinds
    assert "2026-11-04" not in a["spray_ok_days"]  # wind 22 km/h
    assert a["irrigation"] == "SKIP_IRRIGATION" and a["rain_next_48h_mm"] == 70.0


def test_dry_spell_and_missing_values():
    a = wr.analyze(wr.days_from_daily(daily()))
    assert a["dry_spell"] and a["irrigation"] == "IRRIGATE_IF_SOIL_DRY" and a["flags"] == []
    a2 = wr.analyze(wr.days_from_daily(daily(precipitation_sum=[None] * 7)))  # None must not crash
    assert isinstance(a2["flags"], list)


def rec(date, modal):
    return {"arrival_date": date, "modal_price": modal}


def test_price_series_and_signal():
    recs = [rec("01/11/2026", 2000), rec("01/11/2026", 2200), rec("02/11/2026", 2100), rec("03/11/2026", "2,150"), rec("04/11/2026", 2600), rec("bad", 5), rec("05/11/2026", None)]
    s = pr.build_series(recs)
    assert [p["date"] for p in s] == ["2026-11-01", "2026-11-02", "2026-11-03", "2026-11-04"]
    assert s[0]["modal"] == 2100 and s[0]["n"] == 2
    sig = pr.signal(s)
    assert sig["signal"] == "SELL_NOW" and sig["pct_vs_baseline"] > 5 and sig["trend_per_day"] > 0


def test_build_series_zero_and_blank_prices():
    recs = [rec("01/11/2026", v) for v in (0, "0", "", None, "abc", -5)] + [rec("02/11/2026", 2000)]
    assert pr.build_series(recs) == [{"date": "2026-11-02", "modal": 2000, "n": 1}]


def test_build_series_outliers_dropped():
    recs = [rec("01/11/2026", v) for v in (100, 200, 150, 50000)]
    s = pr.build_series(recs)
    assert s[0]["n"] == 3 and s[0]["modal"] == 150
    low = pr.build_series([rec("01/11/2026", v) for v in (2000, 2100, 2200, 5)])
    assert low[0]["n"] == 3


def test_build_series_duplicates_average_out():
    s = pr.build_series([rec("01/11/2026", 2000)] * 3)
    assert s == [{"date": "2026-11-01", "modal": 2000, "n": 3}]


def test_two_days_of_data_is_insufficient():
    s = pr.build_series([rec("01/11/2026", 2000), rec("02/11/2026", 2500)])
    assert pr.signal(s)["signal"] == "INSUFFICIENT_DATA"


def test_price_signal_hold_neutral_insufficient():
    mk = lambda vals: [{"date": f"2026-11-{i + 1:02d}", "modal": v, "n": 3} for i, v in enumerate(vals)]
    assert pr.signal(mk([2000, 2000, 2000, 1800]))["signal"] == "HOLD"
    assert pr.signal(mk([2000, 2010, 1990, 2005]))["signal"] == "NEUTRAL"
    assert pr.signal(mk([2000, 2010]))["signal"] == "INSUFFICIENT_DATA"
    assert pr.signal([])["signal"] == "INSUFFICIENT_DATA"


def test_cross_check():
    heavy = {"flags": [{"flag": "HEAVY_RAIN", "day": "2026-11-02", "day_index": 1, "value": 70.0}]}
    assert pr.cross_check({"signal": "SELL_NOW"}, heavy)[0].startswith("SELL_BEFORE_RAIN")
    assert pr.cross_check({"signal": "HOLD"}, heavy)[0].startswith("STORAGE_RISK")
    assert pr.cross_check({"signal": "HOLD"}, {"flags": []}) == []
    assert "too short" in pr.cross_check({"signal": "INSUFFICIENT_DATA"}, {"flags": []})[0]


def test_numbers_in_handles_commas_and_indic_digits():
    assert numbers_in("Rs 2,450 and 33.0 C") == {"2450", "33"}
    assert "25" in numbers_in("तापमान २५ डिग्री")


def test_grounded_numbers():
    v = grounded_numbers()
    ctx = "max 33.1 C, rain 70.2 mm, Rs 2,450 on 2026-11-02"
    assert v("Rs 2450, about 33 C, rain 70.2 mm on 2 Nov", ctx) == []
    bad = v("Price will reach Rs 3100 and rain 85 mm", ctx)
    assert bad and "3100" in bad[0] and "85" in bad[0]
    assert v("wait 3 days", ctx) == []  # small integers are not checked


def test_run_all_mixes_context_and_plain_validators():
    vs = [grounded_numbers(), max_words(4), forbid_patterns({"guarantee": "no guarantee"}), numeric_limit("dose", r"([\d.]+) ml per litre", hi=0.0)]
    assert run_all(vs, "ok fine", "") == []
    out = run_all(vs, "I guarantee 99 and 5 ml per litre today please now", "")
    assert len(out) == 4
