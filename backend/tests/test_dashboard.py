"""/api/dashboard: one section per live source. No network: the tools are replaced by fakes."""
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app.api import routes
from app.main import app
from app.tools import ToolResult, SourceUnavailable


def _fake_orchestrator(tools: dict):
    return SimpleNamespace(domain=SimpleNamespace(tools=tools))


@pytest.fixture
def client():
    return TestClient(app)


def test_dashboard_without_place_returns_no_numbers(client):
    r = client.get("/api/dashboard")
    assert r.status_code == 200
    assert r.json()["sections"] == {}


def test_dashboard_passes_live_cards_through_and_marks_failures(client, monkeypatch):
    card = {"type": "prices", "title": "Onion - mandi prices", "signal": "HOLD"}

    def mandi(text, profile):
        assert profile == {"place": "Lasalgaon, Nashik", "crop": "Onion"}
        return ToolResult("MANDI ...", True, [{"name": "data.gov.in"}], [card], {})

    def weather(text, profile):
        return ToolResult("WEATHER SOURCE UNAVAILABLE", False)

    def soil(text, profile):
        raise SourceUnavailable("maps.isric.org down")

    tools = {"mandi": mandi, "weather": weather, "soil": soil}
    monkeypatch.setattr(routes, "get_orchestrator", lambda: _fake_orchestrator(tools))

    r = client.get("/api/dashboard", params={"place": "Lasalgaon, Nashik", "crop": "Onion"})
    assert r.status_code == 200
    sec = r.json()["sections"]

    assert sec["mandi"]["ok"] is True
    assert sec["mandi"]["cards"] == [card]
    assert sec["mandi"]["sources"] == [{"name": "data.gov.in"}]

    # a failed or raising source is shown as unavailable, with NO cards invented in its place
    assert sec["weather"] == {"ok": False, "cards": [], "sources": [], "error": "source unavailable"}
    assert sec["soil"]["ok"] is False and sec["soil"]["cards"] == []
    # a tool that is not registered for this domain is reported, not skipped silently
    assert sec["rain_history"] == {"ok": False, "cards": [], "sources": [], "error": "not configured"}


def test_dashboard_reports_missing_input(client, monkeypatch):
    from app.tools import NeedsInput

    def mandi(text, profile):
        raise NeedsInput("place")

    monkeypatch.setattr(routes, "get_orchestrator", lambda: _fake_orchestrator({"mandi": mandi}))
    r = client.get("/api/dashboard", params={"place": "Nashik", "crop": "Onion"})
    assert r.json()["sections"]["mandi"]["error"] == "needs place"
