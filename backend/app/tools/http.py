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

_cache: dict[str, tuple[float, object, float | None]] = {}  # key -> (fetched at, data, own ttl or None for the caller's)
EMPTY_TTL_S = 60.0  # an empty record list may be a blip of the shared free API: do not let it stand for half an hour
_lock = threading.Lock()
CACHE_MAX = 2000  # entries; oldest evicted first (unique places x days would otherwise grow without bound)

# Circuit breaker per host: a source that failed in two separate "rounds" (parallel calls that fail together count as one,
# and the orchestrator's single retry is the second) is not queried again for BREAKER_S seconds. Without it every question
# during an outage waits the full timeout twice. Stale-but-real cached data is still served while it is open.
BREAKER_S = 30.0
ROUND_GAP_S = 3.0
_fails: dict[str, dict] = {}
_client: httpx.Client | None = None
SECRET_PARAMS = {"api-key", "api_key", "apikey", "key"}
# data.gov.in's gateway hangs (502 after ~60 s) on the default "python-httpx" User-Agent but answers in <1 s when the
# client identifies itself. An honest, descriptive agent is also what API operators ask for.
USER_AGENT = "KisaanMitra/1.0 (FORGE 2026 hackathon; farm advisory)"


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


def _host(url: str) -> str:
    return httpx.URL(url).host


def _breaker_wait(host: str, now: float) -> float:
    st = _fails.get(host)
    if st and st["rounds"] >= 2 and now - st["last"] < BREAKER_S:
        return BREAKER_S - (now - st["last"])
    return 0.0


def _note_failure(host: str, now: float) -> None:
    with _lock:
        st = _fails.get(host)
        if st is None or now - st["last"] > 120:  # a long-quiet source starts from scratch
            _fails[host] = {"rounds": 1, "round_start": now, "last": now}
        else:
            if now - st["round_start"] > ROUND_GAP_S:
                st["rounds"] += 1
                st["round_start"] = now
            st["last"] = now


def _worth_counting(e: Exception) -> bool:
    """Outages count; a 400/403/404 is our request's fault and must not shut the source off."""
    if isinstance(e, httpx.HTTPStatusError):
        return e.response.status_code >= 500 or e.response.status_code == 429
    return isinstance(e, (httpx.TransportError, httpx.TimeoutException))


def get_json(url: str, params: dict | None = None, ttl: float | None = None, timeout: float | None = None) -> Fetched:
    global _client
    s = get_settings()
    ttl = s.cache_ttl_s if ttl is None else ttl
    key = url + "|" + "&".join(f"{k}={v}" for k, v in sorted((params or {}).items()))
    now = time.time()
    with _lock:
        hit = _cache.get(key)
    if hit and now - hit[0] < (hit[2] if hit[2] is not None else ttl):
        return Fetched(hit[1], _public(url, params), _iso(hit[0]), False, int(now - hit[0]))
    host = _host(url)
    with _lock:
        wait = _breaker_wait(host, now)
    if wait > 0:
        if hit:
            return Fetched(hit[1], _public(url, params), _iso(hit[0]), True, int(now - hit[0]))
        raise SourceUnavailable(f"{host} is temporarily unreachable (not retrying for {int(wait) + 1}s)")
    try:
        if _client is None:
            _client = httpx.Client(follow_redirects=True, headers={"User-Agent": USER_AGENT})
        r = _client.get(url, params=params, timeout=timeout or s.tool_timeout_s)
        r.raise_for_status()
        data = r.json()
        with _lock:
            empty = isinstance(data, dict) and isinstance(data.get("records"), list) and not data["records"]
            _cache[key] = (now, data, EMPTY_TTL_S if empty else None)
            if len(_cache) > CACHE_MAX:
                _cache.pop(next(iter(_cache)))
            _fails.pop(host, None)
        return Fetched(data, _public(url, params), _iso(now), False, 0)
    except Exception as e:
        if _worth_counting(e):
            _note_failure(host, time.time())  # when it FAILED, not when it started (a timeout started seconds earlier)
        if hit:  # earlier REAL response, clearly labelled stale
            return Fetched(hit[1], _public(url, params), _iso(hit[0]), True, int(now - hit[0]))
        raise SourceUnavailable(_redact(f"{type(e).__name__}: {e}", params)) from e
