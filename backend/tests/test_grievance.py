import pytest
from app.grievance.models import FarmCrisisIn, ResolutionIn
from app.grievance.triage import triage_crisis, mask_phone
from app.grievance import store as grievance_store

def test_phone_masking():
    assert mask_phone("9823451234") == "••••1234"
    assert mask_phone("+91 98765 43210") == "••••3210"

def test_crisis_triage_urgency():
    inp_p1 = FarmCrisisIn(
        farmer_name="Sunita",
        farmer_phone="9823451234",
        place="Lasalgaon",
        category="TRANSFORMER_PUMP_FAILURE",
        description="Transformer burnt, no water for wheat crop.",
        language="mr"
    )
    rep = triage_crisis(inp_p1, "TEST-001")
    assert rep.urgency == "P1"
    assert rep.sla_deadline_hours == 24
    assert "Electricity" in rep.assigned_department

def test_grievance_store_and_board():
    board = grievance_store.get_board_stats()
    assert board["total_reports"] == len(board["hotspots"])  # no seeded or invented tickets
    assert "categories" in board

    # Create new report
    new_inp = FarmCrisisIn(
        farmer_name="Kisan Rao",
        farmer_phone="9988776655",
        place="Yeola",
        category="CROP_LOSS_HAIL",
        description="Severe hailstorm damaged onion field.",
        language="mr"
    )
    rep = grievance_store.create_report(new_inp)
    assert rep.id.startswith("KISAN-2026-")
    assert rep.farmer_phone_masked == "••••6655"

    # Resolve report
    res = grievance_store.resolve_report(rep.id, "Dr. Kulkarni (DAO)", "Inspected survey no 84. Panchnama submitted for PMFBY compensation.")
    assert res.status == "RESOLVED"
    assert res.resolution_proof_url is None  # no proof photo supplied, so none is invented
