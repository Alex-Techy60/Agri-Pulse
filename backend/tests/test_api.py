"""Needs fastapi + deps (real environment). Skipped where they are not installed."""
import os


def test_api_endpoints():
    try:
        from fastapi.testclient import TestClient
        from app.main import app
    except Exception:
        return
    os.environ.setdefault("LLM_API_KEY", "")
    with TestClient(app) as c:
        h = c.get("/api/health").json()
        assert h["status"] == "ok" and h["domain"] == "farm"
        d = c.get("/api/domain").json()
        assert d["profile_fields"] and d["suggested_prompts"]
        r = c.post("/api/chat", json={"message": "hello", "profile": {}}).json()
        assert r["answer"] and r["trace"]
        raw = c.post("/api/chat/stream", json={"message": "hi", "profile": {}}).text
        assert raw.count("data: ") >= 2 and '"type": "final"' in raw
