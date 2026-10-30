"""Tests must be hermetic (CLAUDE.md rule 8): no network, no keys. Real keys in .env would otherwise leak into
Settings() and make tests call live APIs. Env vars take priority over the .env file, so blank them here."""
import os

for _k in ("LLM_API_KEY", "FALLBACK_API_KEY", "DATA_GOV_API_KEY", "QDRANT_URL", "QDRANT_API_KEY"):
    os.environ[_k] = ""

from app.core.config import get_settings  # noqa: E402

get_settings.cache_clear()

import pytest  # noqa: E402

import app.tools.location as _location  # noqa: E402
import app.tools.mandi as _mandi  # noqa: E402
import app.tools.rain_history as _rain  # noqa: E402
import app.tools.weather as _weather  # noqa: E402

_MODULES = (_location, _mandi, _rain, _weather)
_ORIGINAL = {m: {n: getattr(m, n) for n in ("get_json", "get_settings") if hasattr(m, n)} for m in _MODULES}


@pytest.fixture(autouse=True)
def _restore_tool_network():
    """Some tests replace get_json / get_settings on the tool modules; undo it so tests cannot leak into each other."""
    yield
    for m, attrs in _ORIGINAL.items():
        for n, fn in attrs.items():
            setattr(m, n, fn)
