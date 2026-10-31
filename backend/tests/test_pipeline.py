"""Orchestrator behaviour with scripted LLM + stub tools. No network."""
from app.agents.orchestrator import Orchestrator
from app.domain import Domain, Intent
from app.guardrails.validators import grounded_numbers
from app.tools import NeedsInput, ToolResult
from tests.helpers import FakeLLM, StubStore, hit

DATA = ToolResult("WEATHER for Nashik: max 33.1 C, rain 70.2 mm", True, [{"name": "Open-Meteo forecast", "url": "u", "fetched_at": "t", "stale": False}], [{"type": "forecast", "title": "x"}], {"location": {"name": "Nashik", "state": "Maharashtra", "district": "Nashik", "lat": 1, "lon": 2}})
calls = []


def good(text, profile):
    calls.append("good")
    return DATA


def other(text, profile):
    calls.append("other")
    return ToolResult("MANDI PRICES: Rs 2450 per quintal", True, [{"name": "data.gov.in Agmarknet", "url": "u2", "fetched_at": "t", "stale": True}])


def needs(text, profile):
    raise NeedsInput("place", "nearest town")


def boom(text, profile):
    raise RuntimeError("bug")


def down(text, profile):
    return ToolResult("MANDI SOURCE UNAVAILABLE (x). Do NOT guess these values", False)


def post(text, profile):
    calls.append("post")
    return ToolResult("DECISION (computed in code): HOLD", True)


def domain(intent_tools, post_tools=None, tools=None):
    t = {"good": good, "other": other, "needs": needs, "boom": boom, "down": down, "post": post}
    t.update(tools or {})
    return Domain("t", "T", "t", "persona", [Intent("weather_advice", "d", "i", ["rain"]), Intent("general", "g", "i")], [grounded_numbers()], "SAFE", ["p"], tools=t, intent_tools={"weather_advice": intent_tools}, post_tools={"weather_advice": post_tools or []})


def run(intent_tools, llm, post_tools=None, hits=None, text="will it rain?", profile=None):
    return Orchestrator(domain(intent_tools, post_tools), llm, StubStore(hits)).run(text, profile=profile or {"place": "Nashik"})


def test_happy_path_trace_sources_cards_profile():
    llm = FakeLLM(["Max 33 C on that day and rain 70.2 mm."])
    r = run(["good", "other"], llm)
    agents = [t.agent for t in r.trace]
    assert agents[0] == "Router" and agents.count("Tool") == 2 and "Guardrail" in agents
    assert [s["name"] for s in r.live_sources] == ["Open-Meteo forecast", "data.gov.in Agmarknet"]
    assert r.cards and r.profile["state"] == "Maharashtra"
    assert r.degraded  # one source was stale -> flagged
    assert "CONTEXT" in llm.last_messages[0]["content"] and "MANDI PRICES" in llm.last_messages[0]["content"]


def test_ungrounded_number_is_rejected_then_corrected():
    r = run(["good"], FakeLLM(["Rain will be 85 mm.", "Rain will be 70.2 mm."]))
    assert [t.action for t in r.trace if t.agent == "Guardrail"] == ["REJECTED", "passed"]
    assert r.answer == "Rain will be 70.2 mm."


def test_persistent_hallucination_returns_safe_fallback():
    r = run(["good"], FakeLLM(["Rain will be 85 mm."]))
    assert r.answer == "SAFE" and r.warnings


def test_missing_input_makes_agent_ask_and_skips_post_tools():
    calls.clear()
    llm = FakeLLM(["Which town is your farm in?"])
    r = run(["needs"], llm, post_tools=["post"], profile={})
    ctx = llm.last_messages[0]["content"]
    assert "MISSING INFO" in ctx and "place" in ctx and "post" not in calls
    assert any("needs place" in t.action for t in r.trace)


def test_failed_source_continues_and_says_dont_guess():
    llm = FakeLLM(["The price source is not reachable right now."])
    r = run(["good", "down"], llm)
    ctx = llm.last_messages[0]["content"]
    assert "UNAVAILABLE" in ctx and "WEATHER for Nashik" in ctx and r.degraded
    assert any(t.agent == "Tool" and not t.ok for t in r.trace)


def test_crashing_tool_never_crashes_pipeline():
    r = run(["good", "boom"], FakeLLM(["Max 33 C."]))
    assert r.answer == "Max 33 C." and any("crashed" in t.action for t in r.trace)


def test_post_tools_run_after_main_tools():
    calls.clear()
    run(["good", "other"], FakeLLM(["Max 33 C."]), post_tools=["post"])
    assert calls[-1] == "post" and set(calls[:2]) == {"good", "other"}


def test_llm_outage_still_shows_real_live_data_not_fake_text():
    r = run(["good"], FakeLLM(off=True))
    assert r.degraded and r.answer.startswith("(AI summary unavailable - showing live data only)") and "rain 70.2 mm" in r.answer


def test_llm_outage_and_missing_input_asks_user():
    r = run(["needs"], FakeLLM(off=True), profile={})
    assert r.answer.startswith("To help you I need:")


def test_empty_input_and_documents_used():
    assert "type or speak" in run(["good"], FakeLLM(), text="   ").answer
    r = run([], FakeLLM(["Fine, 33 C."]), hits=[hit("Spray in the evening.", "icar.md")])
    assert r.sources == ["icar.md"]


def test_complete_inputs_tell_the_model_not_to_ask_again():
    llm = FakeLLM(["Rain 70.2 mm expected."])
    run(["good"], llm)
    assert "INPUTS COMPLETE" in llm.last_messages[0]["content"]
    llm = FakeLLM(["Which place?"])
    run(["needs"], llm)
    assert "INPUTS COMPLETE" not in llm.last_messages[0]["content"]


def test_safe_fallback_uses_the_farmers_language():
    d = domain(["good"])
    d.safe_fallback_by_lang, d.languages = {"mr": "SAFE-MR"}, {"en": "English", "mr": "Marathi"}
    r = Orchestrator(d, FakeLLM(["Rain will be 85 mm."]), StubStore()).run("will it rain?", language="mr", profile={"place": "Nashik"})
    assert r.answer == "SAFE-MR"
    r = Orchestrator(d, FakeLLM(["Rain will be 85 mm."]), StubStore()).run("will it rain?", language="en", profile={"place": "Nashik"})
    assert r.answer == "SAFE"


def test_offline_answer_hides_exception_text_and_urls_from_the_farmer():
    llm = FakeLLM(off=True)
    r = run(["good", "down"], llm)
    assert "WEATHER for Nashik" in r.answer  # the real data stays
    assert "Do NOT guess" not in r.answer and "SOURCE UNAVAILABLE" not in r.answer
    assert "not reachable right now" in r.answer


def test_every_supported_language_has_a_native_safe_fallback():
    from app.domain.farm import DOMAIN
    assert set(DOMAIN.languages) - {"en"} == set(DOMAIN.safe_fallback_by_lang)
