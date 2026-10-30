"""API safety nets: pipeline bug -> degraded answer (not 500); ingest locked; voice upload bounded."""
import pytest

fastapi = pytest.importorskip("fastapi")
from fastapi.testclient import TestClient  # noqa: E402

from app.api import ratelimit  # noqa: E402
from app.core.config import get_settings  # noqa: E402
from app.main import app  # noqa: E402


@pytest.fixture
def client():
    ratelimit._hits.clear()
    with TestClient(app) as c:
        yield c
    ratelimit._hits.clear()


def _break(monkeypatch):
    import app.api.routes as routes

    class Boom:
        def run(self, *a, **k):
            raise RuntimeError("bug")

        def stream(self, *a, **k):
            yield {"type": "trace", "step": {"agent": "Router", "action": "x", "detail": "", "ms": 0, "ok": True}}
            raise RuntimeError("bug")

    monkeypatch.setattr(routes, "get_orchestrator", lambda: Boom())


def test_pipeline_bug_returns_degraded_answer_not_500(client, monkeypatch):
    _break(monkeypatch)
    r = client.post("/api/chat", json={"message": "hi", "language": "hi"})
    assert r.status_code == 200 and r.json()["degraded"] and r.json()["answer"] and r.json()["language"] == "hi"


def test_stream_bug_still_ends_with_a_final_event(client, monkeypatch):
    _break(monkeypatch)
    raw = client.post("/api/chat/stream", json={"message": "hi"}).text
    assert raw.count("data: ") == 2 and raw.rstrip().endswith("}") and '"type": "final"' in raw and "internal error" in raw


def test_ingest_is_disabled_by_default_and_needs_the_key(client):
    s = get_settings()
    old = s.ingest_api_key
    try:
        s.ingest_api_key = ""
        assert client.post("/api/ingest", json={"texts": ["x"]}).status_code == 403
        s.ingest_api_key = "secret-xyz"
        assert client.post("/api/ingest", json={"texts": ["x"]}).status_code == 401
        assert client.post("/api/ingest", json={"texts": ["x"]}, headers={"X-Admin-Key": "wrong"}).status_code == 401
        ok = client.post("/api/ingest", json={"texts": ["Real advisory text.", 5, "  "], "source": "t"}, headers={"X-Admin-Key": "secret-xyz"})
        assert ok.status_code == 200 and ok.json()["added"] >= 1
    finally:
        s.ingest_api_key = old


def test_voice_upload_over_limit_is_refused_without_500(client):
    big = b"0" * 5_000_100
    r = client.post("/api/voice/transcribe", files={"file": ("a.webm", big, "audio/webm")})
    assert r.status_code == 200 and "too large" in r.json()["error"]


def test_live_check_is_rate_limited(client, monkeypatch):
    import types

    import app.api.routes as routes

    monkeypatch.setattr(routes, "get_orchestrator", lambda: types.SimpleNamespace(domain=types.SimpleNamespace(tools={})))  # no live calls
    s = get_settings()
    old, s.rate_limit_per_min = s.rate_limit_per_min, 1
    try:
        codes = [client.get("/api/live-check?place=x&crop=y").status_code for _ in range(4)]
        assert codes[0] == 200 and 429 in codes
    finally:
        s.rate_limit_per_min = old
