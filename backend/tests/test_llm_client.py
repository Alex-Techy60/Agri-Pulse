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
