"""A place named in the question is used for that question, with no notice about the form; without one, the form's place is used."""
from app.agents.orchestrator import Orchestrator
from app.domain.farm import question_overrides
from tests.helpers import FakeLLM, StubStore
from tests.test_pipeline import domain, good


def _orch(seen):
    def spy(text, profile):
        seen.append(dict(profile))
        return good(text, profile)

    d = domain(["spy"], tools={"spy": spy})
    d.question_overrides = question_overrides
    return Orchestrator(d, FakeLLM(["Max 33 C."]), StubStore())


def test_question_place_is_used_silently_and_the_form_place_comes_back():
    seen = []
    o = _orch(seen)
    o.llm.place = "Pune"  # the router found Pune in the question
    r = o.run("What is the price of potato in Pune?", session_id="q1", profile={"place": "Nashik"})
    assert seen[0]["place"] == "Pune"
    assert r.answer == "Max 33 C."  # no "you set Nashik at the top" text
    assert any(t.action == "question overrides profile" for t in r.trace)  # still visible in the trace
    o.llm.place = ""
    o.run("and should I sell?", session_id="q1", profile={"place": "Nashik"})
    assert seen[1]["place"] == "Nashik"  # no place in the question: the one at the top


def test_native_spelling_of_the_top_place_is_not_an_override():
    assert question_overrides({"place": "Nashik"}, {"place": "नासिक"}, "नासिक मंडी") == {}
    assert question_overrides({"place": "Nashik, Maharashtra"}, {"place": "पुणे"}, "पुणे मंडी") == {"place": "पुणे"}
