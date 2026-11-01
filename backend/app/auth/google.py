"""Sign in with Google: verify Google's ID token, then keep our own signed session cookie.

Why this shape: the browser gets an ID token from Google (no client secret needed); we verify its signature, audience and
expiry with Google's public keys, then hand back a short HttpOnly cookie. The token itself is never stored. Login is optional:
the app keeps working anonymously, and a signed-in person's saved chats follow their account across devices."""
import base64
import hashlib
import hmac
import json
import logging
import secrets
import time

from app.core.config import get_settings

log = logging.getLogger("auth")
COOKIE = "km_session"
_ISSUERS = {"accounts.google.com", "https://accounts.google.com"}
_fallback_secret = secrets.token_bytes(32)  # used only when SESSION_SECRET is unset


class AuthError(Exception):
    """The credential is not acceptable. The message is safe to show; details stay in the log."""


def enabled() -> bool:
    return bool(get_settings().google_client_id.strip())


def _secret() -> bytes:
    s = get_settings().session_secret.strip()
    return s.encode() if s else _fallback_secret


def _b64(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).rstrip(b"=").decode()


def _unb64(s: str) -> bytes:
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


def _sign(body: str) -> str:
    return _b64(hmac.new(_secret(), body.encode(), hashlib.sha256).digest())


def verify_google_credential(credential: str) -> dict:
    """Check signature, audience (our client id), issuer and expiry. Returns Google's claims; raises AuthError otherwise."""
    from google.auth.transport import requests as g_requests
    from google.oauth2 import id_token

    client_id = get_settings().google_client_id.strip()
    try:
        # 60 s of skew: a laptop clock a few seconds behind Google makes a brand-new token look "used too early" and sign-in
        # fails for no visible reason. A token lives an hour, so this barely loosens the expiry check.
        claims = id_token.verify_oauth2_token(credential, g_requests.Request(), client_id, clock_skew_in_seconds=60)
    except Exception as e:  # bad signature, wrong audience, expired, or Google's key endpoint unreachable
        # The reason tells a clock problem ("Token used too early") from a wrong client id ("Token has wrong audience"). Only
        # those messages are logged: the library's parse errors can quote the token itself, which must never reach the log.
        reason = str(e)
        log.warning("google token rejected: %s%s", type(e).__name__,
                    f": {reason[:160]}" if reason.startswith(("Token used too early", "Token expired", "Token has wrong audience")) else "")
        raise AuthError("Google sign-in could not be verified. Please try again.") from e
    if claims.get("iss") not in _ISSUERS or not claims.get("sub"):
        raise AuthError("Google sign-in could not be verified. Please try again.")
    if not claims.get("email_verified", False):
        raise AuthError("Your Google email address is not verified.")
    return claims


def make_session(claims: dict) -> str:
    """Signed, expiring token holding only what the UI shows. `sub` is Google's stable account id (emails can change)."""
    exp = int(time.time()) + get_settings().session_days * 86400
    user = {"sub": claims["sub"], "name": str(claims.get("name") or claims.get("email", ""))[:80],
            "email": str(claims.get("email", ""))[:120], "picture": str(claims.get("picture", ""))[:300], "exp": exp}
    body = _b64(json.dumps(user, separators=(",", ":")).encode())
    return f"{body}.{_sign(body)}"


def read_session(token: str | None) -> dict | None:
    """The signed-in user, or None for a missing, tampered or expired cookie. Never raises."""
    if not token or "." not in token:
        return None
    body, sig = token.rsplit(".", 1)
    try:
        if not hmac.compare_digest(sig, _sign(body)):
            return None
        user = json.loads(_unb64(body))
    except Exception:
        return None
    if not isinstance(user, dict) or not user.get("sub") or user.get("exp", 0) < time.time():
        return None
    return user


def owner_for_user(user: dict) -> str:
    """Chat-owner key for an account. Prefixed so it can never collide with an anonymous browser's hashed id."""
    return hashlib.sha256(f"google:{user['sub']}".encode()).hexdigest()


def public_user(user: dict) -> dict:
    return {k: user.get(k, "") for k in ("name", "email", "picture")}
