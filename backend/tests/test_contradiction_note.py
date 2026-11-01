"""When the question names another crop or place than the form at the top, the reply starts by saying which one it used."""
from app.agents.orchestrator import Orchestrator
from app.domain.farm import contradiction_note, question_overrides
from tests.helpers import FakeLLM, StubStore
from tests.test_pipeline import domain, good


def test_other_crop_is_pointed_out_with_both_names():
    n = contradiction_note({"crop": "Onion"}, {"crop": "Potato"}, "en")
    assert "Onion" in n and "Potato" in n and "answered for Potato" in n


def test_misspelt_crop_is_called_unrecognised_not_silently_searched():
    n = contradiction_note({"crop": "Onion"}, {"crop": "आलो"}, "en")
    assert "do not recognise" in n and "आलो" in n and "Onion" in n


def test_other_place_is_pointed_out():
    n = contradiction_note({"place": "Nashik"}, {"place": "Pune"}, "en")
    assert "Nashik" in n and "Pune" in n


def test_no_contradiction_means_no_note():
    assert contradiction_note({"crop": "Onion"}, {}, "en") == ""
    assert contradiction_note({}, {"crop": "Potato", "place": "Pune"}, "en") == ""  # empty form: nothing to correct
    assert contradiction_note({"crop": ""}, {"crop": "Potato"}, "en") == ""


def test_hindi_and_marathi_get_their_own_text_other_languages_get_english():
    assert "आपने ऊपर" in contradiction_note({"crop": "Onion"}, {"crop": "Potato"}, "hi")
    assert "तुम्ही वर" in contradiction_note({"crop": "Onion"}, {"crop": "Potato"}, "mr")
    assert "You selected" in contradiction_note({"crop": "Onion"}, {"crop": "Potato"}, "ta")


def _orch(llm=None):
    d = domain(["good"], tools={"good": good})
    d.question_overrides = question_overrides
    d.contradiction_note = contradiction_note
    return Orchestrator(d, llm or FakeLLM(["Max 33 C."]), StubStore())


def test_reply_starts_with_the_correction_and_the_trace_shows_it():
    r = _orch().run("What is the price of potato?", profile={"place": "Nashik", "crop": "Onion"})
    assert r.answer.startswith("You selected Onion at the top") and r.answer.endswith("Max 33 C.")
    assert any(t.action == "contradiction notice" for t in r.trace)


def test_no_note_when_question_matches_the_form():
    r = _orch().run("What is the price of onion?", profile={"place": "Nashik", "crop": "Onion"})
    assert "You selected" not in r.answer


def test_live_only_marker_stays_first_so_the_ui_still_folds_the_text():
    r = _orch(FakeLLM(off=True)).run("Will it rain on my potato?", profile={"place": "Nashik", "crop": "Onion"})
    assert r.live_only and r.answer.startswith("(AI summary unavailable") and "You selected Onion" in r.answer
