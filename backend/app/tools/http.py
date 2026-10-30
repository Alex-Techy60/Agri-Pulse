"""The ONLY place tools touch the network.

Live GET with a short TTL cache. If the live call fails but we hold an earlier
REAL response, we return it flagged `stale=True` with its true timestamp (the UI
shows "data from 12 min ago"). We never fabricate: no cache + failure -> SourceUnavailable.
"""
from __future__ import annotations

import datetime as dt
import threading
import time
from dataclasses import dataclass

import httpx

from app.core.config import get_settings
from app.tools import SourceUnavailable

_cache: dict[str, tuple[float, object]] = {}
_lock = threading.Lock()
_client: httpx.Client | None = None
SECRET_PARAMS = {"api-key", "api_key", "apikey", "key"}


@dataclass
class Fetched:
    data: object
    url: str  # public URL (secrets removed) - safe to show in UI
    fetched_at: str  # ISO-8601 UTC of the real fetch
    stale: bool
    age_s: int


def _iso(ts: float) -> str:
    return dt.datetime.fromtimestamp(ts, dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _public(url: str, params: dict | None) -> str:
    safe = {k: v for k, v in (params or {}).items() if k.lower() not in SECRET_PARAMS}
    return url + ("?" + "&".join(f"{k}={v}" for k, v in safe.items()) if safe else "")


def _redact(msg: str, params: dict | None) -> str:
    for k, v in (params or {}).items():
        if k.lower() in SECRET_PARAMS and v:
            msg = msg.replace(str(v), "***")
    return msg


def get_json(url: str, params: dict | None = None, ttl: float | None = None, timeout: float | None = None) -> Fetched:
    global _client
    s = get_settings()
    ttl = s.cache_ttl_s if ttl is None else ttl
    key = url + "|" + "&".join(f"{k}={v}" for k, v in sorted((params or {}).items()))
    now = time.time()
    with _lock:
        hit = _cache.get(key)
    if hit and now - hit[0] < ttl:
        return Fetched(hit[1], _public(url, params), _iso(hit[0]), False, int(now - hit[0]))
    try:
        if _client is None:
            _client = httpx.Client(follow_redirects=True)
        r = _client.get(url, params=params, timeout=timeout or s.tool_timeout_s)
        r.raise_for_status()
        data = r.json()
        with _lock:
            _cache[key] = (now, data)
        return Fetched(data, _public(url, params), _iso(now), False, 0)
    except Exception as e:
        if hit:  # earlier REAL response, clearly labelled stale
            return Fetched(hit[1], _public(url, params), _iso(hit[0]), True, int(now - hit[0]))
        raise SourceUnavailable(_redact(f"{type(e).__name__}: {e}", params)) from e
