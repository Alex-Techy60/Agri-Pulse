"""Fixes from the test run of 1 Nov 2026: each test names the answer that went wrong."""
import pytest

from app.agents.orchestrator import Orchestrator
from app.agents.planner import Planner
from app.domain import Intent
from app.domain.farm import DOMAIN, missing_info_is_a_question, never_ask_for_prices, no_steady_without_trend, own_market_claim
from app.guardrails.validators import plain_text
from app.tools import NeedsInput
from app.tools.mandi import commodity_name, crops_in_text
from tests.helpers import FakeLLM, StubStore
from tests.test_pipeline import domain, good

NO_TREND = "SIGNAL: INSUFFICIENT_DATA (no comparable day)\nDECISION (computed in code): NO PRICE TREND (no comparable day about a week earlier)"


# ---- crop names --------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("text,crops", [
    ("वाट इस द ओनियन वंडी रेट टोड़े", ["onion"]),  # English "onion" written in Devanagari by speech-to-text
    ("टमातर, कांदा, मुल्ली", ["tomato", "onion"]),
    ("पोटेटो का भाव", ["potato"]),
    ("खाना बनाना है", []),  # "बनाना" means "to make": never banana
])
def test_devanagari_spellings_of_english_crop_names(text, crops):
    assert crops_in_text(text) == crops


def test_several_crops_ask_which_one_even_with_a_remembered_crop():
    with pytest.raises(NeedsInput):
        commodity_name({"crop": "Bajra"}, "onion or potato, which to sell?")
    assert commodity_name({"crop": "Bajra"}, "should I sell?") == "Bajra(Pearl Millet/Cumbu)"


# ---- guardrail checks ----------------------------------------------------------------------------------------------
def test_no_trend_must_not_be_called_steady():
    check = no_steady_without_trend()
    bad = "कोई स्पष्ट संकेत नहीं, कीमतें स्थिर हैं\n\nपिछले 7 दिनों में कीमत में बदलाव नहीं दिखा"
    assert check(bad, NO_TREND)
    assert check("Prices are steady this week.", NO_TREND)
    assert not check("आज भाव का रुझान उपलब्ध नहीं है।\n\nआज 2200 रुपये प्रति क्विंटल।", NO_TREND)
    assert not check("No clear signal: prices are steady this week.", "SIGNAL (computed in code): STEADY")  # a real STEADY trend is fine


def test_your_mandi_in_every_hindi_and_marathi_form():
    check = own_market_claim()
    for text in ("पुणे (आपका मंडी) आज 2200 रुपये", "आपकी मंडी में", "आपके बाज़ार में", "तुमच्या बाजारात", "तुमचा बाजार"):
        assert check(text, "MARKETS in Pune"), text
    assert not check("आपका मंडी", "YOUR MARKET on 2026-11-01: Pune Rs 2200")


def test_never_ask_the_farmer_for_prices():
    check = never_ask_for_prices()
    assert check("टमाटर, कांदा, मुल्ली, प्याज की वर्तमान मंडी कीमतें बताइए, फिर मैं सबसे लाभदायक फसल सुझा दूँगा।")
    assert check("Please tell me the current mandi prices.")
    assert check("आजचे भाव सांगा")
    assert not check("I cannot tell the price next week; I cannot forecast prices.")
    assert not check("मैं अगले हफ्ते के भाव नहीं बता सकता।")
    assert not check("Please tell me which crop you want to sell?")


def test_missing_input_answer_is_a_question_not_unavailable():
    check = missing_info_is_a_question()
    ctx = "MISSING INFO: ask the user, in one friendly question, for: crop (which crop the farmer grows or wants to sell)."
    assert check("No clear signal: price data not available now\n\nSource: live market feed, unavailable", ctx)
    assert not check("कृपया बताइए, आप कौन-सी फसल बेचना चाहते हैं?", ctx)
    assert not check("Price data not available.", "MANDI PRICES: no published records")  # only when an input is missing


def test_hard_rules_are_registered():
    names = {v.__qualname__.split(".")[0] for v in DOMAIN.validators}
    assert {"no_steady_without_trend", "never_ask_for_prices", "missing_info_is_a_question"} <= names


# ---- doubled answer ------------------------------------------------------------------------------------------------
def test_answer_written_twice_is_shown_once():
    once = "No clear signal: price data not available now\n\nSource: live market feed, unavailable"
    assert plain_text(once + once) == once
    assert plain_text(once + "\n\n" + once) == once
    assert plain_text("Rs 2200 today. Rs 2200 today.") == "Rs 2200 today. Rs 2200 today."  # short repeats are left alone
    assert plain_text(once) == once


# ---- no data tools for a photo or a document question ---------------------------------------------------------------
class BoomLLM:
    def chat_json(self, *a, **kw):
        raise AssertionError("the planner must not call the LLM for an intent that needs no live data")


@pytest.mark.parametrize("intent", ["crop_health", "scheme_info"])
def test_photo_and_document_questions_run_no_live_tools(intent):
    names, _, fallback = Planner(BoomLLM(), DOMAIN).plan("My onion leaves have yellow spots", {"place": "Pune"}, Intent(intent, "", ""))
    assert names == [] and not fallback


# ---- the crop a question names carries over within the chat ----------------------------------------------------------
def test_crop_named_in_a_question_is_remembered_for_the_follow_up():
    seen = []

    def spy(text, profile):
        seen.append(dict(profile))
        return good(text, profile)

    d = domain(["spy"], tools={"spy": spy})
    d.question_overrides = lambda profile, named, text: {"crop": "Bajra"} if "bajra" in text.lower() else {"crop": "Onion"} if "onion" in text.lower() else {}
    o = Orchestrator(d, FakeLLM(["Max 33 C."]), StubStore())
    o.run("I want to sell bajra", session_id="c1", profile={"place": "Pune"})
    o.run("should I sell now?", session_id="c1", profile={"place": "Pune"})
    assert seen[1]["crop"] == "Bajra"
    o.run("and onion?", session_id="c1", profile={"place": "Pune"})
    o.run("sell now?", session_id="c1", profile={"place": "Pune"})
    assert seen[3]["crop"] == "Onion"  # the latest crop named wins


# ---- several crops in one price question ("नासिक मंडी के प्याज और आलू के भाव", 1 Nov 2026) ----------------------------
def _two_crop_routes(fail_potato=False):
    import datetime as dt

    from tests.test_tools import GEO, forecast, mandi_records

    def routes(url, params):
        if "geocoding" in url:
            return GEO
        if "open-meteo" in url:
            return forecast(rain=[0] * 7)
        crop = params.get("filters[commodity]") or params.get("filters[Commodity]")
        if crop == "Potato" and fail_potato:
            from app.tools import SourceUnavailable
            raise SourceUnavailable("timeout")
        if "filters[state]" not in params and "filters[State]" not in params:
            return {"records": []}
        today = dt.date.today()
        base = {"Onion": (2500, 2000), "Potato": (1500, 1500)}[crop]  # onion rising, potato steady
        recs = []
        for off, p in ((0, base[0]), (7, base[1])):
            recs += [dict(r, Commodity=crop) for r in mandi_records({(today - dt.timedelta(days=off)).strftime("%d/%m/%Y"): [p] * 6})]
        return {"records": recs}

    return routes


def test_two_crops_in_one_question_get_prices_for_both():
    from app.tools import mandi as mandi_mod
    from tests.test_tools import install

    install(_two_crop_routes())
    r = mandi_mod.mandi("नासिक मंडी के प्याज और आलू के भाव बताएं", {"place": "Nashik"})
    assert r.ok and "PRICES FOR 2 CROPS (Onion, Potato)" in r.text
    assert "MANDI PRICES for Onion" in r.text and "MANDI PRICES for Potato" in r.text
    assert [c["title"].split(" - ")[0] for c in r.cards] == ["Onion", "Potato"]
    assert len([s for s in r.sources if s["name"] == "data.gov.in Agmarknet"]) == 1  # one source chip, not one per crop
    cross = mandi_mod.cross("प्याज और आलू बेचूं?", {"place": "Nashik"})
    assert "DECISION for Onion (computed in code): HOLD" in cross.text and "DECISION for Potato (computed in code): STEADY" in cross.text


def test_one_crop_failing_keeps_the_other_crops_real_prices():
    from app.tools import mandi as mandi_mod
    from tests.test_tools import install

    install(_two_crop_routes(fail_potato=True))
    r = mandi_mod.mandi("onion and potato price", {"place": "Nashik"})
    assert r.ok and "MANDI PRICES for Onion" in r.text and "MANDI PRICES for Potato: this live source did not answer" in r.text
    assert [c["title"].split(" - ")[0] for c in r.cards] == ["Onion"]


def test_more_than_three_crops_asks_to_choose():
    from app.tools.mandi import commodity_names

    with pytest.raises(NeedsInput):
        commodity_names({}, "onion, potato, tomato and wheat prices")
    assert commodity_names({"crop": "Bajra"}, "onion and potato prices") == ["Onion", "Potato"]  # the question's crops, not the remembered one


def test_mixed_signals_do_not_trip_the_steady_and_neutral_checks():
    from app.domain.farm import no_advice_on_neutral

    ctx = "SIGNAL (computed in code): HOLD - prices are RISING\nSIGNAL (computed in code): STEADY - prices are roughly STEADY\nSIGNAL: INSUFFICIENT_DATA"
    assert not no_advice_on_neutral()("For potato it is better to hold.", ctx)
    assert not no_steady_without_trend()("Onion prices are steady.", ctx)
