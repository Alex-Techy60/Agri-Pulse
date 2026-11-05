import pytest
from app.executor.receipts import sign_receipt, verify_receipt
from app.executor.vault import vault, VaultError

def test_ed25519_receipt_signing_and_tampering():
    data = {
        "receipt_id": "REC-TEST001",
        "task_id": "task_1234",
        "portal": "PMFBY Sandbox",
        "reference_no": "PMFBY/MH/2026/001234",
        "submitted_at": "2026-11-05T02:00:00Z"
    }
    signed = sign_receipt(data)
    assert "signature" in signed
    assert "public_key" in signed
    assert verify_receipt(signed) is True

    # Tampering test (Phase 2.5: altering one field must fail verification)
    tampered = dict(signed)
    tampered["reference_no"] = "PMFBY/MH/2026/999999"
    assert verify_receipt(tampered) is False

def test_vault_encryption_and_aadhaar_refusal():
    # Regular secret
    tok = vault.put("mobile", "9823451234")
    assert vault.get(tok) == "9823451234"
    assert vault.mask("9823451234") == "••••1234"

    # Aadhaar refusal (CLAUDE.md & Phase 1.4 non-negotiable rule)
    with pytest.raises(VaultError) as excinfo:
        vault.put("aadhaar_no", "1234 5678 9012")
    assert "never stores or collects Aadhaar" in str(excinfo.value)
