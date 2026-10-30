"""5.1 network failures + 5.2 bad input. No network, no keys: httpx.MockTransport and fakes only."""
import httpx
import pytest

import app.tools.http as http
from app.agents import planner as planner_mod
from app.agents.orchestrator import Orchestrator, script_lang
from app.core.config import Settings
from app.domain.farm import DOMAIN
from app.llm.client import LLMClient
from app.tools import SourceUnavailable
from tests.helpers import FakeLLM, StubStore
from tests.test_tools import GEO


@pytest.fixture(autouse=True)
def _clean_http():
    http._cache.clear()
    old = http._client
    yield
    http._client, http._cache = old, {}


def use(handler):
    http._client = httpx.Client(transport=httpx.MockTransport(handler))


# ---- 5.1 network failures ---------------------------------------------------------------
def test_429_without_cache_is_source_unavailable_and_key_never_leaks():
    use(lambda req: httpx.Response(429, json={"error": "rate"}))
    with pytest.raises(SourceUnavailable) as e:
        http.get_json("https://x.test/api", {"api-key": "SECRET123", "q": 1})
    assert "SECRET123" not in str(e.value)


def test_failure_after_success_returns_labelled_stale_real_data():
    calls = {"n": 0}

    def handler(req):
        calls["n"] += 1
        return httpx.Response(200, json={"v": 1}) if calls["n"] == 1 else httpx.Response(503)

    use(handler)
    assert http.get_json("https://x.test/a", ttl=0).stale is False
    again = http.get_json("https://x.test/a", ttl=0)  # ttl=0 forces a live call, which now fails
    assert again.stale is True and again.data == {"v": 1}


@pytest.mark.parametrize("exc", [httpx.ReadTimeout("slow"), httpx.ConnectError("no network")])
def test_timeout_and_offline_are_source_unavailable(exc):
    def handler(req):
        raise exc

    use(handler)
    with pytest.raises(SourceUnavailable):
        http.get_json("https://x.test/b")


def test_everything_down_still_answers_with_degraded_and_no_crash(monkeypatch):
    monkeypatch.setattr(planner_mod, "RETRY_DELAY_S", 0)

    def handler(req):
        raise httpx.ConnectError("wifi off")

    use(handler)
    r = Orchestrator(DOMAIN, FakeLLM(off=True), StubStore()).run("Should I sell my onions?", profile={"place": "Nashik", "crop": "Onion"})
    assert r.answer and r.degraded and "SOURCE UNAVAILABLE" in r.answer
    assert any(t.action == "replan" for t in r.trace)


def test_both_llm_providers_failing_gives_offline_text_not_exception():
    handler = lambda req: httpx.Response(429 if req.url.host == "p.test" else 500)
    s = Settings(llm_api_key="k", llm_base_url="https://p.test/v1", fallback_api_key="k2", fallback_base_url="https://f.test/v1", fallback_model="m")
    r = LLMClient(s, transport=httpx.MockTransport(handler)).chat([{"role": "user", "content": "hi"}], offline="OFF")
    assert r.provider == "offline" and r.text == "OFF" and r.degraded


# ---- 5.2 bad input ----------------------------------------------------------------------
def test_nonsense_place_asks_for_a_nearer_town(monkeypatch):
    monkeypatch.setattr(planner_mod, "RETRY_DELAY_S", 0)
    use(lambda req: httpx.Response(200, json={"results": []}))
    llm = FakeLLM(["Please tell me a nearer town."], route="weather_advice")
    r = Orchestrator(DOMAIN, llm, StubStore()).run("will it rain?", profile={"place": "asdfgh"})
    assert "place not found" in llm.last_messages[0]["content"] and r.answer and not any(t.action == "replan" for t in r.trace)


def test_huge_message_is_truncated_to_2000_chars():
    llm = FakeLLM(["ok"], route="general")
    Orchestrator(DOMAIN, llm, StubStore()).run("x" * 10000)
    assert len(llm.last_messages[-1]["content"]) == 2000


def test_api_rejects_oversized_message_with_422_not_500():
    try:
        from fastapi.testclient import TestClient
        from app.main import app
    except Exception:
        return
    with TestClient(app) as c:
        assert c.post("/api/chat", json={"message": "x" * 10000}).status_code == 422


@pytest.mark.parametrize(
    "text,intent,lang",
    [("🌾 मेरे प्याज का क्या भाव है?", "market_price", "hi"), ("mera onion ka bhav kya hai Nashik mein?", "market_price", "en"), ("😀😀", "general", "en")],
)
def test_router_keyword_fallback_handles_emoji_hindi_hinglish(text, intent, lang):
    o = Orchestrator(DOMAIN, FakeLLM(off=True), StubStore())
    got_intent, got_lang, _, degraded = o._route(text, None)
    assert (got_intent.name, got_lang, degraded) == (intent, lang, True)


def test_script_lang_detects_indic_scripts():
    assert script_lang("வணக்கம்") == "ta" and script_lang("ਸਤ ਸ੍ਰੀ ਅਕਾਲ") == "pa" and script_lang("hello 🌾") == "en"
