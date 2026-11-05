import pytest
import time
from unittest.mock import patch, MagicMock
from app.tools.http import get_json, Fetched, _public, _redact, _cache, _lock
from app.tools import SourceUnavailable

def test_public_url_removes_secrets():
    url = "https://api.data.gov.in/resource"
    params = {"api-key": "secret123", "format": "json", "limit": 10}
    public = _public(url, params)
    assert "secret123" not in public
    assert "api-key" not in public
    assert "format=json" in public
    assert "limit=10" in public

def test_redact_masks_secrets_in_errors():
    params = {"api-key": "supersecretkey999", "format": "json"}
    error_msg = "Failed to query https://api.data.gov.in with key supersecretkey999"
    redacted = _redact(error_msg, params)
    assert "supersecretkey999" not in redacted
    assert "***" in redacted

def test_http_stale_cache_on_failure():
    url = "https://mock.api/data"
    params = {"format": "json"}
    key = url + "|" + "&".join(f"{k}={v}" for k, v in sorted(params.items()))
    
    # Pre-seed cache with real response (expired TTL to force refresh)
    with _lock:
        _cache[key] = (time.time() - 100, {"records": [1, 2, 3]}, 10.0)
    
    # Simulate network failure on the active _client
    with patch("app.tools.http._client.get", side_effect=Exception("Connection timed out")):
        fetched = get_json(url, params, ttl=10)
        assert isinstance(fetched, Fetched)
        assert fetched.stale is True
        assert fetched.data == {"records": [1, 2, 3]}

def test_http_raises_source_unavailable_when_no_cache():
    url = "https://mock.unseen.api/data"
    params = {"format": "json"}
    
    with patch("app.tools.http._client.get", side_effect=Exception("Server Down")):
        with pytest.raises(SourceUnavailable):
            get_json(url, params, ttl=10)
