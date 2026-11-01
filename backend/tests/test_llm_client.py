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
    assert set(hosts) == {"p.test"} and r.provider == "offline"  # the reserve model shares the provider; the slow fallback is skipped


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


def test_reserve_model_answers_when_the_big_models_quota_is_spent_before_the_slow_fallback():
    import httpx

    models = []

    def handler(req):
        body = json.loads(req.content)
        models.append((req.url.host, body["model"]))
        if body["model"] == "big":
            return httpx.Response(429, json={"error": "tokens per day"})
        return httpx.Response(200, json={"choices": [{"message": {"content": "from small"}}]})

    s = Settings(llm_api_key="k", llm_base_url="https://p.test/v1", llm_model="big", llm_fast_model="small", fallback_api_key="k2", fallback_base_url="https://f.test/v1", fallback_model="m")
    r = LLMClient(s, transport=httpx.MockTransport(handler)).chat([{"role": "user", "content": "hi"}])
    assert r.text == "from small" and r.provider == "reserve" and r.model == "small" and not r.degraded
    assert all(h == "p.test" for h, _ in models)  # the slow fallback was never needed


def test_a_segment_that_loops_on_one_phrase_is_dropped_but_ordinary_speech_with_a_normal_ratio_is_kept():
    from app.llm.client import speech_text

    looping = {"segments": [{"text": "बारिश बारिश बारिश बारिश बारिश बारिश", "avg_logprob": -0.1, "no_speech_prob": 0, "compression_ratio": 3.1}]}
    ordinary = {"segments": [{"text": "Should I sell my onions now?", "avg_logprob": -0.14, "no_speech_prob": 0, "compression_ratio": 0.79}]}
    assert speech_text(looping) == "" and speech_text(ordinary) == "Should I sell my onions now?"
    assert speech_text({"segments": [{"text": "a", "compression_ratio": 3.0}, {"text": "kept", "compression_ratio": 1.2}]}) == "kept"


def test_deadline_stops_the_provider_ladder_and_returns_offline_text():
    """A request past its deadline must not wait on another slow provider (the UI gives up at 90 s)."""
    import time

    import httpx

    hits = []

    def handler(req):
        hits.append(req.url.host)
        return httpx.Response(200, json={"choices": [{"message": {"content": "late"}}]})

    s = Settings(llm_api_key="k", llm_base_url="https://primary.test/v1", fallback_api_key="k2", fallback_base_url="https://fb.test/v1", fallback_model="m")
    r = LLMClient(s, transport=httpx.MockTransport(handler)).chat([{"role": "user", "content": "hi"}], offline="OFF", deadline=time.time() - 1)
    assert r.provider == "offline" and r.text == "OFF" and hits == []
    # a deadline that has not passed changes nothing
    ok = LLMClient(s, transport=httpx.MockTransport(handler)).chat([{"role": "user", "content": "hi"}], deadline=time.time() + 60)
    assert ok.text == "late" and hits == ["primary.test"]


def _rotation_settings(**kw):
    from app.core.config import Settings
    return Settings(llm_api_key="k1", llm_extra_api_keys=" k2, ,k3,k1", llm_base_url="https://primary.test/v1", **kw)


def test_extra_keys_are_listed_once_and_in_order():
    from app.core.config import llm_keys
    assert llm_keys(_rotation_settings()) == ["k1", "k2", "k3"]
    assert llm_keys(Settings(llm_api_key="")) == []
    assert llm_keys(Settings(llm_api_key="", llm_extra_api_keys="x")) == ["x"]


def test_spent_key_rotates_to_next_key_and_is_not_retried(monkeypatch):
    """Daily quota gone on key 1 (429): key 2 answers on the same model, and the next request skips key 1."""
    import httpx

    import app.llm.client as c

    monkeypatch.setattr(c, "_parked", {})
    monkeypatch.setattr(c.time, "sleep", lambda s: None)
    seen = []

    def handler(req):
        key = req.headers["authorization"].split()[-1]
        seen.append((key, json.loads(req.content)["model"]))
        if key == "k1":
            return httpx.Response(429, json={"error": {"message": "tokens per day"}}, headers={"retry-after": "600"})
        return httpx.Response(200, json={"choices": [{"message": {"content": "from k2"}}]})

    llm = LLMClient(_rotation_settings(), transport=httpx.MockTransport(handler))
    r = llm.chat([{"role": "user", "content": "hi"}])
    assert r.text == "from k2" and r.provider == "primary" and not r.degraded
    assert seen == [("k1", "openai/gpt-oss-120b"), ("k2", "openai/gpt-oss-120b")]
    seen.clear()
    llm.chat([{"role": "user", "content": "hi"}])
    assert seen == [("k2", "openai/gpt-oss-120b")]  # key 1 is parked for this model


def test_all_keys_spent_falls_through_to_reserve_model_then_offline(monkeypatch):
    import httpx

    import app.llm.client as c

    monkeypatch.setattr(c, "_parked", {})
    monkeypatch.setattr(c.time, "sleep", lambda s: None)

    def handler(req):
        return httpx.Response(429, json={"error": "limit"})

    r = LLMClient(_rotation_settings(), transport=httpx.MockTransport(handler)).chat([{"role": "user", "content": "hi"}], offline="OFF")
    assert r.provider == "offline" and r.text == "OFF"
    assert "k1" not in r.error and "k2" not in r.error  # keys never appear in errors or logs


def test_fallback2_and_fallback3_catch_when_fallback1_also_fails():
    """FALLBACK2 and FALLBACK3 entries are tried in order when every earlier provider fails."""
    import httpx

    hits: list[str] = []

    def handler(req):
        host = req.url.host
        hits.append(host)
        if host in ("primary.test", "fb1.test", "fb2.test"):
            return httpx.Response(429, json={"error": "rate"})
        # fb3.test answers
        return httpx.Response(200, json={"choices": [{"message": {"content": "from fallback3"}}]})

    s = Settings(
        llm_api_key="k", llm_base_url="https://primary.test/v1",
        fallback_api_key="k2", fallback_base_url="https://fb1.test/v1", fallback_model="m1",
        fallback2_api_key="k3", fallback2_base_url="https://fb2.test/v1", fallback2_model="m2",
        fallback3_api_key="k4", fallback3_base_url="https://fb3.test/v1", fallback3_model="m3",
    )
    r = LLMClient(s, transport=httpx.MockTransport(handler)).chat([{"role": "user", "content": "hi"}])
    assert r.text == "from fallback3" and r.provider == "fallback3" and r.degraded
    assert "fb3.test" in hits  # the third fallback was actually reached


def test_fallback2_is_reached_before_fallback3_and_short_circuits():
    """When FALLBACK2 succeeds, FALLBACK3 is never called."""
    import httpx

    hits: list[str] = []

    def handler(req):
        host = req.url.host
        hits.append(host)
        if host in ("primary.test", "fb1.test"):
            return httpx.Response(429, json={"error": "rate"})
        return httpx.Response(200, json={"choices": [{"message": {"content": "from fb2"}}]})

    s = Settings(
        llm_api_key="k", llm_base_url="https://primary.test/v1",
        fallback_api_key="k2", fallback_base_url="https://fb1.test/v1", fallback_model="m1",
        fallback2_api_key="k3", fallback2_base_url="https://fb2.test/v1", fallback2_model="m2",
        fallback3_api_key="k4", fallback3_base_url="https://fb3.test/v1", fallback3_model="m3",
    )
    r = LLMClient(s, transport=httpx.MockTransport(handler)).chat([{"role": "user", "content": "hi"}])
    assert r.text == "from fb2" and r.provider == "fallback2" and r.degraded
    assert "fb3.test" not in hits  # fallback3 was never contacted

