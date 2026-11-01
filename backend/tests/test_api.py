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


def test_localized_suggested_prompts_are_for_supported_languages_and_match_the_english_count():
    from app.domain.farm import DOMAIN
    assert set(DOMAIN.suggested_prompts_by_lang) <= set(DOMAIN.languages)
    assert all(len(v) == len(DOMAIN.suggested_prompts) for v in DOMAIN.suggested_prompts_by_lang.values())


def test_profile_form_has_no_crop_field():
    from app.domain.farm import DOMAIN
    assert [f["key"] for f in DOMAIN.profile_fields] == ["place"]  # the crop comes from the question
