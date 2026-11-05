"""Verifies that advisory provenance receipts are generated deterministically and validated properly."""
import pytest
from app.agents.orchestrator import compute_advisory_digest


def test_advisory_digest_deterministic():
    sources = [{"name": "Open-Meteo", "fetched_at": "2026-11-05T02:00:00Z"}]
    cards = [{"type": "prices", "signal": "HOLD"}]
    
    d1 = compute_advisory_digest("Nashik, Maharashtra", "Onion", sources, cards)
    d2 = compute_advisory_digest("Nashik, Maharashtra", "Onion", sources, cards)
    
    assert d1 is not None
    assert d1 == d2
    assert d1.startswith("KM-")
    assert len(d1) == 15


def test_advisory_digest_empty():
    assert compute_advisory_digest("Nashik", "Onion", [], []) is None


def test_verify_endpoint():
    from fastapi.testclient import TestClient
    from app.main import app

    with TestClient(app) as client:
        # Valid digest
        res = client.get("/api/advisory/verify", params={"digest": "KM-A1B2C3D4E5F6"})
        assert res.status_code == 200
        data = res.json()
        assert data["valid"] is True
        assert data["status"] == "VERIFIED_GENUINE"
        assert "Code disposes" in data["guarantee"]

        # Invalid format
        bad_res = client.get("/api/advisory/verify", params={"digest": "INVALID-HASH"})
        assert bad_res.status_code == 400

        # Schemes API
        schemes_res = client.get("/api/schemes")
        assert schemes_res.status_code == 200
        assert "schemes" in schemes_res.json()
        assert len(schemes_res.json()["schemes"]) > 0

        # Grievance API & Board API
        board_res = client.get("/api/public/board")
        assert board_res.status_code == 200
        assert "total_reports" in board_res.json()

        grievance_payload = {
            "farmer_name": "Sunita Shinde",
            "mobile": "9823451234",
            "village": "Lasalgaon",
            "taluka": "Niphad",
            "district": "Nashik",
            "category": "CROP_LOSS_HAIL",
            "description": "Hailstorm caused onion rotting. 70% damage.",
            "language": "mr"
        }
        create_res = client.post("/api/grievances", json=grievance_payload)
        assert create_res.status_code == 200
        rep_data = create_res.json()
        rep_id = rep_data.get("id") or rep_data.get("report", {}).get("id")
        assert rep_id is not None

        # Receipts API
        pk_res = client.get("/api/receipts/public-key")
        assert pk_res.status_code == 200
        assert "public_key_b64" in pk_res.json()

        from app.executor.receipts import sign_receipt
        test_rec = sign_receipt({"receipt_id": "REC-TEST", "task_id": "1", "reference_no": "PMFBY/001"})
        verify_res = client.post("/api/receipts/verify", json=test_rec)
        assert verify_res.status_code == 200
        assert verify_res.json()["valid"] is True

        # Sandbox portal root
        sandbox_res = client.get("/sandbox/login")
        assert sandbox_res.status_code == 200
        assert "Farmer Sign-In" in sandbox_res.text
