"""In-memory sliding-window rate limit for chat and other quota-spending routes (single process; enough for a demo deployment)."""
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
    """Two buckets: per client IP (3x the limit, so a shared venue network is not punished) and per IP+session.
    The IP bucket is what stops a client that simply rotates session_id. Best-effort anti-abuse: behind a proxy the IP
    comes from X-Forwarded-For, which a determined client can forge."""
    limit = get_settings().rate_limit_per_min
    if not limit:
        return
    ip = request.client.host if request.client else "?"
    if not check_rate(f"ip|{ip}", limit * 3) or not check_rate(f"{ip}|{session_id}", limit):
        raise HTTPException(429, "Too many requests. Please wait a minute and try again.", headers={"Retry-After": "60"})
