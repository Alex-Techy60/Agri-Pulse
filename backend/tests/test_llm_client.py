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


def test_fallback_gets_enough_tokens_to_finish_json_after_reasoning():
    import httpx

    seen = {}

    def handler(req):
        if req.url.host == "p.test":
            return httpx.Response(401, json={"error": "bad key"})
        seen.update(json.loads(req.content))
        return httpx.Response(200, json={"choices": [{"message": {"content": "{}"}}]})

    s = Settings(llm_api_key="k", llm_base_url="https://p.test/v1", llm_fast_model="small", fallback_api_key="k2", fallback_base_url="https://fb.test/v1", fallback_model="m")
    LLMClient(s, transport=httpx.MockTransport(handler)).chat_json([{"role": "user", "content": "hi"}], fast=True, max_tokens=80)
    assert seen["max_tokens"] >= 400


def test_primary_only_skips_the_fallback():
    import httpx

    hosts = []

    def handler(req):
        hosts.append(req.url.host)
        return httpx.Response(401, json={"error": "bad key"})

    s = Settings(llm_api_key="k", llm_base_url="https://p.test/v1", fallback_api_key="k2", fallback_base_url="https://fb.test/v1", fallback_model="m")
    r = LLMClient(s, transport=httpx.MockTransport(handler)).chat([{"role": "user", "content": "hi"}], primary_only=True, offline="OFF")
    assert hosts == ["p.test"] and r.provider == "offline"


def test_a_dropped_connection_is_retried_once_before_the_fallback(monkeypatch):
    import httpx

    import app.llm.client as c

    monkeypatch.setattr(c.time, "sleep", lambda s: None)
    calls = {"p": 0, "fb": 0}

    def handler(req):
        if req.url.host == "p.test":
            calls["p"] += 1
            if calls["p"] == 1:
                raise httpx.RemoteProtocolError("Server disconnected without sending a response.", request=req)
            return httpx.Response(200, json={"choices": [{"message": {"content": "from primary"}}]})
        calls["fb"] += 1
        return httpx.Response(200, json={"choices": [{"message": {"content": "from fallback"}}]})

    s = Settings(llm_api_key="k", llm_base_url="https://p.test/v1", fallback_api_key="k2", fallback_base_url="https://fb.test/v1", fallback_model="m")
    r = LLMClient(s, transport=httpx.MockTransport(handler)).chat([{"role": "user", "content": "hi"}])
    assert r.text == "from primary" and not r.degraded and calls == {"p": 2, "fb": 0}


def test_speech_text_drops_silence_but_keeps_real_speech():
    from app.llm.client import speech_text

    silent = {"text": " Thank you.", "segments": [{"text": " Thank you.", "no_speech_prob": 0.92, "avg_logprob": -1.7}]}
    assert speech_text(silent) == ""  # Whisper's habitual phrase on silence is not a question
    mixed = {"segments": [{"text": " Thank you.", "no_speech_prob": 0.9, "avg_logprob": -1.5}, {"text": " Should I sell my onions", "no_speech_prob": 0.02, "avg_logprob": -0.3}]}
    assert speech_text(mixed) == "Should I sell my onions"
    unsure_but_speech = {"segments": [{"text": " mera pyaaz", "no_speech_prob": 0.1, "avg_logprob": -1.4}]}
    assert speech_text(unsure_but_speech) == "mera pyaaz"  # low confidence alone is not silence
    assert speech_text({"text": " plain text only "}) == "plain text only"  # a provider without segment scores
    assert speech_text({}) == "" and speech_text(None) == ""


def test_transcribe_sends_language_vocabulary_hint_and_zero_temperature():
    import httpx

    seen = {}

    def handler(req):
        seen["body"] = req.read().decode("latin-1")
        seen["url"] = str(req.url)
        return httpx.Response(200, json={"text": "x", "segments": [{"text": " कांदा विकू का", "no_speech_prob": 0.01, "avg_logprob": -0.2}]})

    s = Settings(llm_api_key="k", llm_base_url="https://p.test/v1")
    out = LLMClient(s, transport=httpx.MockTransport(handler)).transcribe(b"x" * 2000, "audio.m4a", "mr", "कांदा, पाऊस")
    assert out == "कांदा विकू का" and seen["url"].endswith("/audio/transcriptions")
    body = seen["body"]
    assert 'name="response_format"' in body and "verbose_json" in body and 'name="temperature"' in body and 'name="language"' in body and 'filename="audio.m4a"' in body


def test_transcribe_retries_a_dropped_connection_once(monkeypatch):
    import httpx

    import app.llm.client as client_mod

    monkeypatch.setattr(client_mod.time, "sleep", lambda s: None)
    calls = []

    def handler(req):
        calls.append(1)
        if len(calls) == 1:
            raise httpx.RemoteProtocolError("dropped")
        return httpx.Response(200, json={"text": "should I sell"})

    s = Settings(llm_api_key="k", llm_base_url="https://p.test/v1")
    assert LLMClient(s, transport=httpx.MockTransport(handler)).transcribe(b"x" * 2000) == "should I sell" and len(calls) == 2


def test_stock_silence_phrases_and_punctuation_only_output_are_dropped_even_when_the_provider_is_confident():
    from app.llm.client import speech_text

    confident = {"segments": [{"text": " Thank you.", "no_speech_prob": 0, "avg_logprob": -0.29}]}  # what Groq really returned for 4 s of silence
    assert speech_text(confident) == "" and speech_text({"text": " ."}) == "" and speech_text({"text": "..."}) == ""
    assert speech_text({"text": " धन्यवाद।"}) == "" and speech_text({"text": "Thanks for watching!"}) == ""
    assert speech_text({"text": "Thank you, should I sell my onions?"}) == "Thank you, should I sell my onions?"  # only the bare phrase is dropped
    assert speech_text({"text": " मी कांदा विकू का?"}) == "मी कांदा विकू का?"
