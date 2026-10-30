"""In-memory sliding-window rate limit for chat routes (single process; enough for a demo deployment)."""
import threading
import time
from collections import defaultdict

from fastapi import HTTPException, Request

from app.core.config import get_settings

_hits: dict[str, list[float]] = defaultdict(list)
_lock = threading.Lock()


def check_rate(key: str, limit: int, now: float | None = None) -> bool:
    now = time.time() if now is None else now
    with _lock:
        recent = [t for t in _hits[key] if now - t < 60]
        if len(recent) >= limit:
            _hits[key] = recent
            return False
        recent.append(now)
        _hits[key] = recent
        return True


def enforce(request: Request, session_id: str) -> None:
    """Keyed by client IP + session: a fresh session_id alone cannot dodge the limit."""
    limit = get_settings().rate_limit_per_min
    ip = request.client.host if request.client else "?"
    if limit and not check_rate(f"{ip}|{session_id}", limit):
        raise HTTPException(429, "Too many requests. Please wait a minute and try again.", headers={"Retry-After": "60"})
