"""When the question names another place than the form at the top, the reply starts by saying which one it used."""
from app.agents.orchestrator import Orchestrator
from app.domain.farm import contradiction_note, question_overrides
from tests.helpers import FakeLLM, StubStore
from tests.test_pipeline import domain, good


def test_other_place_is_pointed_out():
    n = contradiction_note({"place": "Nashik"}, {"place": "Pune"}, "en")
    assert "Nashik" in n and "Pune" in n


def test_no_contradiction_means_no_note():
    assert contradiction_note({"place": "Nashik"}, {}, "en") == ""
    assert contradiction_note({}, {"place": "Pune"}, "en") == ""  # empty form: nothing to correct
    assert contradiction_note({"place": ""}, {"place": "Pune"}, "en") == ""


def test_hindi_and_marathi_get_their_own_text_other_languages_get_english():
    assert "आपने ऊपर" in contradiction_note({"place": "Nashik"}, {"place": "Pune"}, "hi")
    assert "तुम्ही वर" in contradiction_note({"place": "Nashik"}, {"place": "Pune"}, "mr")
    assert "You set" in contradiction_note({"place": "Nashik"}, {"place": "Pune"}, "ta")


def _orch(llm=None):
    d = domain(["good"], tools={"good": good})
    d.question_overrides = question_overrides
    d.contradiction_note = contradiction_note
    return Orchestrator(d, llm or FakeLLM(["Max 33 C."]), StubStore())


def test_reply_starts_with_the_correction_and_the_trace_shows_it():
    llm = FakeLLM(["Max 33 C."])
    llm.place = "Pune"  # the router found Pune in the question
    r = _orch(llm).run("What is the price of potato in Pune?", profile={"place": "Nashik"})
    assert r.answer.startswith("You set Nashik at the top") and r.answer.endswith("Max 33 C.")
    assert any(t.action == "contradiction notice" for t in r.trace)


def test_no_note_when_question_matches_the_form():
    r = _orch().run("What is the price of onion?", profile={"place": "Nashik"})
    assert "You set" not in r.answer
