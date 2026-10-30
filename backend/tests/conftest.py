"""Tests must be hermetic (CLAUDE.md rule 8): no network, no keys. Real keys in .env would otherwise leak into
Settings() and make tests call live APIs. Env vars take priority over the .env file, so blank them here."""
import os

for _k in ("LLM_API_KEY", "FALLBACK_API_KEY", "DATA_GOV_API_KEY", "QDRANT_URL", "QDRANT_API_KEY"):
    os.environ[_k] = ""

from app.core.config import get_settings  # noqa: E402

get_settings.cache_clear()
