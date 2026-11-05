from __future__ import annotations
import re
import secrets
from pathlib import Path
from cryptography.fernet import Fernet

VAULT_DIR = Path(__file__).resolve().parents[2] / "data" / "vault"
VAULT_KEY_FILE = VAULT_DIR / "vault.key"

def _get_fernet() -> Fernet:
    VAULT_DIR.mkdir(parents=True, exist_ok=True)
    if VAULT_KEY_FILE.exists():
        key = VAULT_KEY_FILE.read_bytes()
    else:
        key = Fernet.generate_key()
        VAULT_KEY_FILE.write_bytes(key)
    return Fernet(key)

_FERNET = _get_fernet()

AADHAAR_REGEX = re.compile(r"\b\d{4}\s?\d{4}\s?\d{4}\b")

class VaultError(Exception):
    pass

class FarmerVault:
    def __init__(self):
        self._store: dict[str, bytes] = {}

    def put(self, key_name: str, secret_val: str) -> str:
        # Aadhaar refusal guardrail
        if "aadhaar" in key_name.lower() or AADHAAR_REGEX.search(secret_val):
            raise VaultError(
                "By security policy, KisaanMitra never stores or collects Aadhaar numbers. "
                "Farmers authenticate directly on official portals via government OTP."
            )
        token = secrets.token_hex(12)
        encrypted = _FERNET.encrypt(secret_val.encode("utf-8"))
        self._store[token] = encrypted
        return token

    def get(self, token: str) -> str | None:
        enc = self._store.get(token)
        if not enc:
            return None
        try:
            return _FERNET.decrypt(enc).decode("utf-8")
        except Exception:
            return None

    def mask(self, val: str) -> str:
        s = str(val or "").strip()
        if len(s) > 4:
            return f"••••{s[-4:]}"
        return "••••"

vault = FarmerVault()
