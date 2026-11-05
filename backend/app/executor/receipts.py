from __future__ import annotations
import base64
import json
from pathlib import Path
from cryptography.hazmat.primitives.asymmetric import ed25519
from cryptography.hazmat.primitives import serialization

KEY_DIR = Path(__file__).resolve().parents[2] / "data" / "crypto"
KEY_FILE = KEY_DIR / "ed25519_key.pem"

def _get_signing_key() -> ed25519.Ed25519PrivateKey:
    KEY_DIR.mkdir(parents=True, exist_ok=True)
    if KEY_FILE.exists():
        try:
            return serialization.load_pem_private_key(KEY_FILE.read_bytes(), password=None)
        except Exception:
            pass
    key = ed25519.Ed25519PrivateKey.generate()
    pem = key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption()
    )
    KEY_FILE.write_bytes(pem)
    return key

_PRIVATE_KEY = _get_signing_key()

def get_public_key_b64() -> str:
    pub = _PRIVATE_KEY.public_key()
    pub_bytes = pub.public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw
    )
    return base64.b64encode(pub_bytes).decode("ascii")

def canonical_json(data: dict) -> bytes:
    # Deterministic JSON serialization: sorted keys, excluding signature and public_key, compact spacing
    d = {k: v for k, v in data.items() if k not in ("signature", "public_key")}
    return json.dumps(d, sort_keys=True, separators=(",", ":")).encode("utf-8")

def sign_receipt(receipt_data: dict) -> dict:
    """Signs a filing receipt with our Ed25519 private key."""
    payload = canonical_json(receipt_data)
    sig_bytes = _PRIVATE_KEY.sign(payload)
    sig_b64 = base64.b64encode(sig_bytes).decode("ascii")
    out = dict(receipt_data)
    out["signature"] = sig_b64
    out["public_key"] = get_public_key_b64()
    return out

def verify_receipt(receipt_data: dict, public_key_b64: str | None = None) -> bool:
    """Verifies that the Ed25519 signature on the receipt is mathematically valid and not tampered with."""
    sig_b64 = receipt_data.get("signature")
    if not sig_b64:
        return False
    pub_b64 = public_key_b64 or receipt_data.get("public_key") or get_public_key_b64()
    try:
        pub_bytes = base64.b64decode(pub_b64)
        sig_bytes = base64.b64decode(sig_b64)
        pub_key = ed25519.Ed25519PublicKey.from_public_bytes(pub_bytes)
        payload = canonical_json(receipt_data)
        pub_key.verify(sig_bytes, payload)
        return True
    except Exception:
        return False
