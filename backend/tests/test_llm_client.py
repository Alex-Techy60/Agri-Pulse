"""LLM client fallback ladder with httpx.MockTransport (real environment: needs httpx)."""
import json

from app.core.config import Settings
from app.llm.client import LLMClient, parse_json, strip_think


def test_parse_helpers():
    assert parse_json('```json\n{"a": 1}\n```') == {"a": 1} and parse_json("x") is None
    assert strip_think("<think>t</think>Hi") == "Hi"


def test_ladder_primary_fallback_offline():
    import httpx

    def handler(req):
        host = req.url.host
        if host == "primary.test":
            return httpx.Response(429, json={"error": "rate"})
        return httpx.Response(200, json={"choices": [{"message": {"content": "from fallback"}}]})

    s = Settings(llm_api_key="k", llm_base_url="https://primary.test/v1", fallback_api_key="k2", fallback_base_url="https://fb.test/v1", fallback_model="m")
    r = LLMClient(s, transport=httpx.MockTransport(handler)).chat([{"role": "user", "content": "hi"}])
    assert r.text == "from fallback" and r.provider == "fallback" and r.degraded
    r2 = LLMClient(Settings(llm_api_key=""), transport=httpx.MockTransport(handler)).chat([{"role": "user", "content": "hi"}], offline="OFF")
    assert r2.provider == "offline" and r2.text == "OFF"


def test_short_429_is_waited_out_on_primary_before_using_fallback(monkeypatch):
    import httpx

    import app.llm.client as c

    slept, calls = [], {"primary": 0, "fb": 0}
    monkeypatch.setattr(c.time, "sleep", lambda s: slept.append(s))

    def handler(req):
        if req.url.host == "p.test":
            calls["primary"] += 1
            if calls["primary"] == 1:
                return httpx.Response(429, headers={"retry-after": "2"}, json={"error": "rate"})
            return httpx.Response(200, json={"choices": [{"message": {"content": "from primary"}}]})
        calls["fb"] += 1
        return httpx.Response(200, json={"choices": [{"message": {"content": "from fallback"}}]})

    s = Settings(llm_api_key="k", llm_base_url="https://p.test/v1", fallback_api_key="k2", fallback_base_url="https://f.test/v1", fallback_model="m")
    r = c.LLMClient(s, transport=httpx.MockTransport(handler)).chat([{"role": "user", "content": "hi"}])
    assert r.text == "from primary" and r.provider == "primary" and not r.degraded
    assert slept == [2.0] and calls == {"primary": 2, "fb": 0}


def test_long_or_missing_retry_after_goes_straight_to_fallback(monkeypatch):
    import httpx

    import app.llm.client as c

    slept = []
    monkeypatch.setattr(c.time, "sleep", lambda s: slept.append(s))
    for hdr in ({"retry-after": "30"}, {}):
        handler = lambda req, hdr=hdr: httpx.Response(429, headers=hdr) if req.url.host == "p.test" else httpx.Response(200, json={"choices": [{"message": {"content": "fb"}}]})
        s = Settings(llm_api_key="k", llm_base_url="https://p.test/v1", fallback_api_key="k2", fallback_base_url="https://f.test/v1", fallback_model="m")
        r = c.LLMClient(s, transport=httpx.MockTransport(handler)).chat([{"role": "user", "content": "hi"}])
        assert r.provider == "fallback" and r.degraded
    assert slept == []
