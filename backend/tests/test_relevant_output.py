"""The farmer sees only what answers the question: no forecast under a price answer, nothing beside a 'which crop?' question,
no unrelated table under the safe fallback, and a one-word reply keeps the topic of the question just asked. No network."""
from app.agents.orchestrator import Orchestrator
from app.domain import Domain, Intent
from app.guardrails.validators import grounded_numbers
from app.tools import NeedsInput, ToolResult
from tests.helpers import FakeLLM, StubStore

LOC = {"location": {"name": "Pune", "state": "Maharashtra", "district": "Pune", "lat": 1, "lon": 2}}
WX = ToolResult("WEATHER for Pune: max 30 C, rain 7.4 mm", True, [{"name": "Open-Meteo forecast", "url": "w", "fetched_at": "t", "stale": False}], [{"type": "forecast", "days": [1]}], LOC)
PRICE = ToolResult("MANDI PRICES: Rs 3750 per quintal (data.gov.in Agmarknet)", True, [{"name": "data.gov.in Agmarknet", "url": "m", "fetched_at": "t", "stale": False}], [{"type": "prices"}], LOC)
FIT = ToolResult("CROP FIT for Pune: Brinjal 100", True, [{"name": "Open-Meteo historical", "url": "h", "fetched_at": "t", "stale": False}], [{"type": "crop_fit", "crops": [1]}], LOC)


def weather(text, profile):
    return WX


def weather_down(text, profile):
    return ToolResult("WEATHER SOURCE UNAVAILABLE (x). Do NOT guess these values", False)


def weather_crash(text, profile):
    raise RuntimeError("bug")


def mandi(text, profile):
    if not profile.get("crop"):
        raise NeedsInput("crop", "which crop you grow")
    return PRICE


def cross(text, profile):
    return ToolResult("DECISION (computed in code): STEADY", True)


def crop_fit(text, profile):
    return FIT


INTENTS = [Intent("sell_or_hold", "s", "i", ["sell"]), Intent("weather_advice", "w", "i", ["rain"]), Intent("crop_suggest", "c", "i", ["which crop"]), Intent("general", "g", "i")]


def dom(wx=weather):
    return Domain(
        "t", "T", "t", "persona", INTENTS, [grounded_numbers()], "SAFE", ["p"],
        tools={"weather": wx, "mandi": mandi, "cross_check": cross, "crop_fit": crop_fit},
        intent_tools={"sell_or_hold": ["mandi", "weather"], "weather_advice": ["weather"], "crop_suggest": ["crop_fit", "weather"]},
        post_tools={"sell_or_hold": ["cross_check"]},
        intent_cards={"sell_or_hold": {"prices", "notice"}, "weather_advice": {"forecast"}, "crop_suggest": {"crop_fit"}},
        quiet_tools={"sell_or_hold": {"weather"}},
    )


class PlannerAddsWeather(FakeLLM):
    """Router answers with `route`; the planner (max_tokens=120) asks for weather, as the live planner did."""

    def chat_json(self, msgs, **kw):
        if kw.get("max_tokens") == 120:
            from app.llm.client import LLMResult
            return {"tools": ["weather"], "reason": "selling"}, LLMResult("{}", "primary")
        return super().chat_json(msgs, **kw)


def ask(o, text, profile, sid="s1"):
    return o.run(text, profile=profile, session_id=sid)


def test_sell_answer_runs_weather_but_shows_no_forecast_chip_or_weather_text():
    llm = PlannerAddsWeather(["Rs 3750 per quintal (data.gov.in Agmarknet)."], route="sell_or_hold")
    r = ask(Orchestrator(dom(), llm, StubStore()), "should I sell?", {"place": "Pune", "crop": "Onion"})
    assert [c["type"] for c in r.cards] == ["prices"]
    assert [s["name"] for s in r.live_sources] == ["data.gov.in Agmarknet"]
    assert "WEATHER for" not in llm.last_messages[0]["content"]
    tools = [t.action for t in r.trace if t.agent == "Tool"]
    assert any(a.startswith("weather") for a in tools) and any(a.startswith("cross_check") for a in tools)  # the trace still shows it ran


def test_weather_outage_does_not_cost_the_sell_decision():
    for wx in (weather_down, weather_crash):
        llm = FakeLLM(["Rs 3750 per quintal (data.gov.in Agmarknet)."], route="sell_or_hold")
        r = ask(Orchestrator(dom(wx), llm, StubStore()), "should I sell?", {"place": "Pune", "crop": "Onion"})
        ctx = llm.last_messages[0]["content"]
        assert "DECISION (computed in code)" in ctx and "UNAVAILABLE" not in ctx and "TOOL FAILED" not in ctx, wx.__name__


def test_a_question_for_missing_input_comes_with_no_cards_or_chips():
    r = ask(Orchestrator(dom(), FakeLLM(["Which crop are you growing?"], route="sell_or_hold"), StubStore()), "should I sell?", {"place": "Pune"})
    assert r.cards == [] and r.live_sources == []


def test_a_one_word_reply_keeps_the_question_just_asked():
    llm = FakeLLM(["Which crop?"], route="sell_or_hold")
    o = Orchestrator(dom(), llm, StubStore())
    ask(o, "should I sell?", {"place": "Pune"})
    llm.route, llm.answers, llm.n = "crop_suggest", ["Rs 3750 per quintal (data.gov.in Agmarknet)."], 0  # the router alone misreads "onion"
    r = ask(o, "onion", {"place": "Pune", "crop": "Onion"})
    assert r.intent == "sell_or_hold" and [c["type"] for c in r.cards] == ["prices"]


def test_a_new_question_after_a_missing_input_is_routed_normally():
    llm = FakeLLM(["Which crop?"], route="sell_or_hold")
    o = Orchestrator(dom(), llm, StubStore())
    ask(o, "should I sell?", {"place": "Pune"})
    llm.route, llm.answers, llm.n = "weather_advice", ["Rain 7.4 mm (Open-Meteo)."], 0
    assert ask(o, "will it rain this week", {"place": "Pune"}).intent == "weather_advice"  # carries a keyword


def test_the_waiting_intent_is_used_once_and_never_in_the_shared_session():
    llm = FakeLLM(["Which crop?"], route="sell_or_hold")
    o = Orchestrator(dom(), llm, StubStore())
    ask(o, "should I sell?", {"place": "Pune"}, sid="default")
    llm.route = "crop_suggest"
    assert ask(o, "onion", {"place": "Pune", "crop": "Onion"}, sid="default").intent == "crop_suggest"


def test_weather_question_still_gets_the_forecast_card():
    r = ask(Orchestrator(dom(), FakeLLM(["Rain 7.4 mm (Open-Meteo)."], route="weather_advice"), StubStore()), "will it rain?", {"place": "Pune"})
    assert [c["type"] for c in r.cards] == ["forecast"] and r.live_sources[0]["name"] == "Open-Meteo forecast"


def test_an_unrelated_card_from_a_planner_added_tool_is_not_shown():
    class AddsFit(PlannerAddsWeather):
        def chat_json(self, msgs, **kw):
            if kw.get("max_tokens") == 120:
                from app.llm.client import LLMResult
                return {"tools": ["crop_fit"], "reason": "x"}, LLMResult("{}", "primary")
            return FakeLLM.chat_json(self, msgs, **kw)

    r = ask(Orchestrator(dom(), AddsFit(["Rain 7.4 mm (Open-Meteo)."], route="weather_advice"), StubStore()), "will it rain?", {"place": "Pune"})
    assert "crop_fit" not in [c["type"] for c in r.cards]


def test_follow_up_questions_come_with_an_answer_in_its_language_but_not_with_a_question():
    from app.domain.farm import DOMAIN

    d = dom()
    d.languages = {"en": "English", "hi": "Hindi", "ta": "Tamil"}
    d.follow_ups = {"sell_or_hold": {"en": ["Which market pays the most?"], "hi": ["सबसे ऊँचा भाव कहाँ?"]}}
    o = Orchestrator(d, FakeLLM(["Rs 3750 per quintal (data.gov.in Agmarknet)."], route="sell_or_hold"), StubStore())
    assert ask(o, "should I sell?", {"place": "Pune", "crop": "Onion"}).follow_ups == ["Which market pays the most?"]
    assert ask(o, "should I sell?", {"place": "Pune"}, sid="s2").follow_ups == []  # waiting for the crop: no distractions
    assert o.run("क्या बेचूँ?", profile={"place": "Pune", "crop": "Onion"}, language="hi").follow_ups == ["सबसे ऊँचा भाव कहाँ?"]
    assert o.run("should I sell?", profile={"place": "Pune", "crop": "Onion"}, language="ta").follow_ups == ["Which market pays the most?"]  # other languages: English
    for intent in DOMAIN.intents:  # every intent offers something, in English, Hindi and Marathi
        f = DOMAIN.follow_ups.get(intent.name, {})
        assert f.get("en") and f.get("hi") and f.get("mr"), intent.name


def test_every_follow_up_reaches_a_real_topic_even_on_keyword_routing():
    from app.domain.farm import DOMAIN

    o = Orchestrator(DOMAIN, FakeLLM(off=True), StubStore())  # the LLM router is down: keywords alone must still find the topic
    for intent, by_lang in DOMAIN.follow_ups.items():
        if intent == "general":
            continue
        for lang, qs in by_lang.items():
            for q in qs:
                assert o._route(q, lang)[0].name != "general", (lang, q)
