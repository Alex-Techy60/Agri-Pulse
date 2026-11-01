import json
import logging
import secrets

import httpx
from fastapi.concurrency import run_in_threadpool

from fastapi import APIRouter, File, Form, Header, HTTPException, Query, Request, UploadFile
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, Field

from app.agents.orchestrator import ChatResult, TraceStep, get_orchestrator
from app.api.ratelimit import enforce
from app.auth import google as auth
from app.core import stats
from app.core.config import get_settings, llm_keys
from app.llm.client import get_llm
from app.memory.chats import CHAT_ID, get_chats, owner_key
from app.memory.store import KNOWLEDGE, MEMORY, get_store
from app.tools import PlaceNotFound
from app.tools.reverse_geo import locate

router = APIRouter(prefix="/api")
log = logging.getLogger("api")
MAX_AUDIO_BYTES = 5_000_000
MAX_INGEST_TEXTS, MAX_INGEST_CHARS = 50, 5000


def _owner(request: Request, client_id: str | None) -> str | None:
    """Who owns the saved chats: the signed-in Google account if there is one, else the anonymous browser id."""
    user = auth.read_session(request.cookies.get(auth.COOKIE))
    return auth.owner_for_user(user) if user else owner_key(client_id)


def _error_result(language: str | None) -> dict:
    """A pipeline bug must degrade visibly, never become a 500 mid-demo (CLAUDE rule 1)."""
    msg = "Something went wrong on my side. Please try again in a moment."
    return ChatResult(msg, "general", language or "en", degraded=True, trace=[TraceStep("Pipeline", "internal error", "safe answer returned", 0, False)]).dict()


class ChatIn(BaseModel):
    message: str = Field("", max_length=4000)
    session_id: str = Field("default", max_length=100)
    language: str | None = None
    image_b64: str | None = Field(None, max_length=7_000_000)  # base64 JPEG (no data: prefix), ~5 MB
    profile: dict = Field(default_factory=dict)  # {place, crop, ...} from the UI profile bar


@router.get("/health")
def health():
    s = get_settings()
    st = get_store()
    return {
        "status": "ok",
        "domain": s.domain,
        "llm_configured": bool(llm_keys(s)),
        "mandi_key_configured": bool(s.data_gov_api_key),
        "fallback_configured": bool(s.fallback_api_key),
        "knowledge_chunks": st.count(KNOWLEDGE),
        "memories": st.count(MEMORY),
    }


@router.get("/stats")
def get_stats():
    """Aggregate counters since process start (no user text)."""
    return stats.snapshot()


@router.get("/domain")
def domain():
    d = get_orchestrator().domain
    return {"title": d.title, "tagline": d.tagline, "suggested_prompts": d.suggested_prompts, "suggested_prompts_by_lang": d.suggested_prompts_by_lang, "languages": d.languages, "profile_fields": d.profile_fields}


def _scoped_session(owner: str | None, body: ChatIn) -> str:
    """Saved chats key the model's context by owner+chat, so two people can never share a session by choosing the same id.
    A resumed chat gets its earlier turns back from the database. No client id (curl, tests) keeps the old anonymous behaviour."""
    if not owner or not CHAT_ID.match(body.session_id):
        return body.session_id
    sid = f"{owner[:16]}:{body.session_id}"
    orch = get_orchestrator()
    if sid not in orch.history:
        orch.restore_history(sid, get_chats().recent(owner, body.session_id, orch.s.history_turns * 2))
    return sid


def _save_turn(owner: str | None, body: ChatIn, result: dict) -> None:
    """Only real answers are saved: the 'something went wrong' fallback and an empty question are not history."""
    if not owner or not body.message.strip() or any(t.get("agent") == "Pipeline" for t in result.get("trace", [])):
        return
    user_text = f"📷 {body.message}" if body.image_b64 else body.message
    meta = {k: result.get(k) for k in ("cards", "live_sources", "sources", "degraded", "language", "live_only")}
    result["message_id"] = get_chats().append_turn(owner, body.session_id, user_text, result["answer"], meta)  # additive: lets the UI attach feedback to this answer


@router.post("/chat")
def chat(body: ChatIn, request: Request, x_client_id: str | None = Header(None)):
    enforce(request, body.session_id)
    owner = _owner(request, x_client_id)
    try:
        result = get_orchestrator().run(body.message, _scoped_session(owner, body), body.language, body.image_b64, body.profile).dict()
    except Exception:
        log.error("chat pipeline error", exc_info=True)
        return _error_result(body.language)
    _save_turn(owner, body, result)
    return result


@router.post("/chat/stream")
def chat_stream(body: ChatIn, request: Request, x_client_id: str | None = Header(None)):
    """Server-sent events: one `trace` event per pipeline step, then one `final`."""
    enforce(request, body.session_id)
    orch = get_orchestrator()
    owner = _owner(request, x_client_id)

    def gen():
        try:
            for ev in orch.stream(body.message, _scoped_session(owner, body), body.language, body.image_b64, body.profile):
                if ev["type"] == "final":
                    ev = {"type": "final", "result": ev["result"].dict()}
                    _save_turn(owner, body, ev["result"])
                yield f"data: {json.dumps(ev, ensure_ascii=False)}\n\n"
        except Exception:
            log.error("chat stream error", exc_info=True)
            yield f"data: {json.dumps({'type': 'final', 'result': _error_result(body.language)}, ensure_ascii=False)}\n\n"

    return StreamingResponse(gen(), media_type="text/event-stream", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


def _owner_or_400(request: Request, x_client_id: str | None) -> str:
    owner = _owner(request, x_client_id)
    if not owner:
        raise HTTPException(400, "Missing or invalid X-Client-Id header.")
    return owner


@router.get("/chats")
def list_chats(request: Request, x_client_id: str | None = Header(None)):
    """This person's saved chats, newest first. Another person's chats are never visible: every query is scoped to the owner."""
    return {"chats": get_chats().list_chats(_owner_or_400(request, x_client_id))}


@router.get("/chats/{chat_id}")
def read_chat(chat_id: str, request: Request, x_client_id: str | None = Header(None)):
    chat = get_chats().get_chat(_owner_or_400(request, x_client_id), chat_id)
    if not chat:
        raise HTTPException(404, "Chat not found.")
    return chat


class FeedbackIn(BaseModel):
    message_id: int = Field(..., ge=1)
    value: str | None = Field(None, pattern="^(up|down)$")  # null clears the vote


class PrefsIn(BaseModel):
    lang: str | None = Field(None, max_length=8)
    speak: bool | None = None
    rate: float | None = Field(None, ge=0.5, le=2)
    profile: dict[str, str] | None = None


@router.get("/settings")
def read_settings(request: Request, x_client_id: str | None = Header(None)):
    """Language, profile (place, crop...), read-aloud and speed: kept per person so they follow the account across devices."""
    return {"settings": get_chats().load_prefs(_owner_or_400(request, x_client_id))}


@router.put("/settings")
def write_settings(body: PrefsIn, request: Request, x_client_id: str | None = Header(None)):
    owner = _owner_or_400(request, x_client_id)
    d = get_orchestrator().domain
    out: dict = {}
    if body.lang in d.languages:  # only values the app knows: this text is later trusted by the UI
        out["lang"] = body.lang
    if body.speak is not None:
        out["speak"] = body.speak
    if body.rate is not None:
        out["rate"] = body.rate
    if body.profile is not None:
        keys = {f["key"] for f in d.profile_fields}
        out["profile"] = {k: v.strip()[:100] for k, v in body.profile.items() if k in keys and v.strip()}
    return {"saved": get_chats().save_prefs(owner, out)}


@router.put("/feedback")
def feedback(body: FeedbackIn, request: Request, x_client_id: str | None = Header(None)):
    """Thumbs up/down on one answer. Scoped to the owner: another person's answer id is a 404, not a vote."""
    if not get_chats().set_feedback(_owner_or_400(request, x_client_id), body.message_id, body.value):
        raise HTTPException(404, "Answer not found.")
    return {"ok": True}


@router.delete("/chats/{chat_id}")
def remove_chat(chat_id: str, request: Request, x_client_id: str | None = Header(None)):
    owner = _owner_or_400(request, x_client_id)
    if not get_chats().delete_chat(owner, chat_id):
        raise HTTPException(404, "Chat not found.")
    get_orchestrator().forget_history(f"{owner[:16]}:{chat_id}")
    return {"deleted": True}


class GoogleIn(BaseModel):
    credential: str = Field(..., min_length=20, max_length=4096)  # the ID token from Google Identity Services


@router.get("/auth/config")
def auth_config():
    """Tells the UI whether to show 'Sign in with Google' (the client id is public by design)."""
    return {"enabled": auth.enabled(), "client_id": get_settings().google_client_id.strip() if auth.enabled() else ""}


@router.post("/auth/google")
async def auth_google(body: GoogleIn, request: Request):
    enforce(request, "auth")
    if not auth.enabled():
        raise HTTPException(404, "Sign-in is not configured.")
    try:
        claims = await run_in_threadpool(auth.verify_google_credential, body.credential)  # may fetch Google's keys: blocking
    except auth.AuthError as e:
        raise HTTPException(401, str(e))
    anon = owner_key(request.headers.get("x-client-id"))
    if anon:
        get_chats().adopt(anon, auth.owner_for_user(claims))  # chats made in this browser before signing in now belong to the account
    get_chats().record_user({**claims, "name": claims.get("name") or claims.get("email", "")})  # remembers the account; never blocks sign-in
    secure = request.headers.get("x-forwarded-proto", request.url.scheme) == "https"
    res = JSONResponse({"user": auth.public_user({**claims, "name": claims.get("name") or claims.get("email", "")})})
    res.set_cookie(auth.COOKIE, auth.make_session(claims), max_age=get_settings().session_days * 86400,
                   httponly=True, samesite="lax", secure=secure, path="/")
    return res


@router.get("/auth/me")
def auth_me(request: Request):
    user = auth.read_session(request.cookies.get(auth.COOKIE))
    return {"user": auth.public_user(user) if user else None}


@router.post("/auth/logout")
def auth_logout():
    res = JSONResponse({"ok": True})
    res.delete_cookie(auth.COOKIE, path="/")
    return res


@router.get("/live-check")
def live_check(request: Request, place: str = "Nashik, Maharashtra", crop: str = "Onion"):
    """Calls each live tool once and reports ok/source/first line. Use before every demo."""
    from app.tools import NeedsInput

    enforce(request, "live-check")  # it spends live-API quota, so it is rate limited like chat
    place, crop = place[:100], crop[:60]

    d, out = get_orchestrator().domain, {}
    for name in ("weather", "mandi", "rain_history"):
        if name not in d.tools:
            continue
        try:
            r = d.tools[name]("", {"place": place, "crop": crop})
            out[name] = {"ok": r.ok, "first_line": r.text.splitlines()[0] if r.text else "", "sources": r.sources}
        except NeedsInput as e:
            out[name] = {"ok": False, "first_line": f"needs {e.field}"}
        except Exception as e:
            out[name] = {"ok": False, "first_line": f"{type(e).__name__}: {e}"}
    return out


MIN_AUDIO_BYTES = 1000  # smaller than this cannot hold a spoken question
AUDIO_EXTS = {"flac", "mp3", "mp4", "mpeg", "mpga", "m4a", "ogg", "opus", "wav", "webm"}  # what the speech API accepts
AUDIO_TYPES = {"audio/webm": "webm", "video/webm": "webm", "audio/mp4": "m4a", "audio/x-m4a": "m4a", "audio/aac": "m4a", "audio/ogg": "ogg",
               "audio/wav": "wav", "audio/x-wav": "wav", "audio/mpeg": "mp3", "audio/flac": "flac"}


def audio_name(filename: str | None, content_type: str | None) -> str:
    """Name for the speech API, whose container detection follows the extension: Safari sends mp4, other browsers webm."""
    ext = (filename or "").rsplit(".", 1)[-1].lower() if "." in (filename or "") else ""
    if ext not in AUDIO_EXTS:
        ext = AUDIO_TYPES.get((content_type or "").split(";")[0].strip().lower(), "webm")
    return f"audio.{ext}"


@router.post("/voice/transcribe")
async def transcribe(request: Request, file: UploadFile = File(...), language: str | None = Form(None)):
    enforce(request, "voice")
    try:
        audio = await file.read(MAX_AUDIO_BYTES + 1)  # never buffer an unbounded upload
        if len(audio) > MAX_AUDIO_BYTES:
            return {"text": "", "error": "Audio is too large (limit 5 MB). Please record a shorter question."}
        if len(audio) < MIN_AUDIO_BYTES:
            return {"text": "", "error": "Audio is too short. Please speak a little longer."}
        domain = get_orchestrator().domain
        lang = language if language in domain.languages else None  # never pass a client-chosen string on to the provider
        # the call blocks for seconds: off the event loop, or every other request waits behind one transcription
        text = await run_in_threadpool(get_llm().transcribe, audio, audio_name(file.filename, file.content_type), lang, domain.stt_prompts.get(lang or ""))
        return {"text": text}
    except Exception as e:
        log.warning("transcription failed: %s", type(e).__name__)  # type only: the message holds the provider URL
        busy = isinstance(e, httpx.HTTPStatusError) and e.response.status_code == 429
        return {"text": "", "error": "The speech service is busy. Please try again in a minute." if busy else "Speech recognition failed. Please type your question."}


@router.get("/locate")
def locate_place(request: Request, lat: float = Query(..., ge=-90, le=90), lon: float = Query(..., ge=-180, le=180)):
    """'Use my location': coordinates -> a place name the weather and mandi tools resolve. Never stores or logs the coordinates."""
    enforce(request, "locate")
    try:
        return locate(lat, lon)
    except PlaceNotFound as e:
        return {"error": f"I could not match your location to a place in India ({e}). Please type your village or town."}
    except Exception as e:
        log.warning("locate failed: %s", type(e).__name__)
        return {"error": "The location service is not reachable right now. Please type your village or town."}


@router.post("/ingest")
def ingest(payload: dict, x_admin_key: str | None = Header(None)):
    """POST {"texts": ["...", "..."], "source": "name"} with header X-Admin-Key to add REAL knowledge live.
    Disabled unless INGEST_API_KEY is set: an open endpoint would let anyone plant text the agent then retrieves."""
    key = get_settings().ingest_api_key
    if not key:
        raise HTTPException(403, "Ingest is disabled (set INGEST_API_KEY to enable it).")
    if not x_admin_key or not secrets.compare_digest(x_admin_key.encode(), key.encode()):
        raise HTTPException(401, "Invalid admin key.")
    raw = payload.get("texts", [])
    texts = [t[:MAX_INGEST_CHARS] for t in (raw if isinstance(raw, list) else []) if isinstance(t, str) and t.strip()][:MAX_INGEST_TEXTS]
    source = str(payload.get("source", "live-upload"))[:100]
    n = get_store().add(KNOWLEDGE, texts, [{"source": source} for _ in texts])
    return {"added": n}
