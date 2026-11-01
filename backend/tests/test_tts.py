"""Read-aloud: natural voice via Sarvam when a key is set, a clean 503 (UI uses the browser voice) when not. No network."""
import base64

from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.llm import tts
from app.main import app


def test_chunks_split_at_sentence_ends_and_cap_length():
    text = "पहला वाक्य। " * 400  # ~5000 chars of Hindi sentences
    parts = tts.chunks(text)
    assert 1 < len(parts) <= tts.MAX_CHUNKS
    assert all(len(p) <= tts.CHUNK for p in parts)
    assert all(p.endswith("।") for p in parts)


def test_chunks_cut_one_giant_sentence_at_spaces():
    parts = tts.chunks("word " * 1000)
    assert all(len(p) <= tts.CHUNK for p in parts) and all(not p.startswith(" ") for p in parts)


def test_no_key_means_no_audio_and_route_says_unavailable(monkeypatch):
    monkeypatch.setattr(get_settings(), "sarvam_api_key", "")
    assert tts.speak("hello", "en") is None
    with TestClient(app) as c:
        assert c.get("/api/health").json()["tts_configured"] is False
        r = c.post("/api/voice/speak", json={"text": "hello", "language": "en"})
    assert r.status_code == 503


def test_speak_returns_mp3_and_caches(monkeypatch):
    monkeypatch.setattr(get_settings(), "sarvam_api_key", "test-key")
    tts._cache.clear()
    calls = []

    class FakeResp:
        def raise_for_status(self):
            pass

        def json(self):
            return {"audios": [base64.b64encode(b"ID3fake").decode()]}

    class FakeClient:
        def __init__(self, **kw):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *a):
            pass

        def post(self, url, json, headers):
            calls.append(json)
            return FakeResp()

    monkeypatch.setattr(tts.httpx, "Client", FakeClient)
    with TestClient(app) as c:
        r = c.post("/api/voice/speak", json={"text": "प्याज अभी बेचें।", "language": "hi", "pace": 9})
    assert r.status_code == 200 and r.headers["content-type"] == "audio/mpeg" and r.content == b"ID3fake"
    assert calls[0]["language_code"] == "hi-IN" and calls[0]["pace"] == 2.0  # pace clamped to Sarvam's range
    assert tts.speak("प्याज अभी बेचें।", "hi", 9) == b"ID3fake" and len(calls) == 1  # second play is cached


def test_service_failure_and_unknown_language_give_none(monkeypatch):
    monkeypatch.setattr(get_settings(), "sarvam_api_key", "test-key")
    tts._cache.clear()

    class Boom:
        def __init__(self, **kw):
            raise RuntimeError("down")

    monkeypatch.setattr(tts.httpx, "Client", Boom)
    assert tts.speak("hello", "en") is None
    assert tts.speak("hello", "xx") is None
