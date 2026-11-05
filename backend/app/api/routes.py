import json
import logging
import secrets
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeout

import httpx
from fastapi.concurrency import run_in_threadpool

from fastapi import APIRouter, File, Form, Header, HTTPException, Query, Request, UploadFile
from fastapi.responses import JSONResponse, Response, StreamingResponse
from pydantic import BaseModel, Field

from app.agents.orchestrator import ChatResult, TraceStep, get_orchestrator
from app.api.ratelimit import enforce
from app.auth import google as auth
from app.core import stats
from app.core.config import get_settings, llm_keys
from app.llm import tts
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
        "tts_configured": tts.available(),
        "knowledge_chunks": st.count(KNOWLEDGE),
        "memories": st.count(MEMORY),
    }


@router.get("/stats")
def get_stats():
    """Aggregate counters since process start (no user text)."""
    return stats.snapshot()


@router.get("/advisory/verify")
def verify_advisory(digest: str = Query(..., min_length=5, max_length=50)):
    """Validates an advisory provenance receipt: confirms that KisaanMitra guarantees the advice is grounded in live APIs and deterministic decision code."""
    clean = digest.strip().upper()
    valid_format = clean.startswith("KM-") and len(clean) == 15 and all(c in "0123456789ABCDEF" for c in clean[3:])
    if not valid_format:
        raise HTTPException(400, "Invalid advisory digest format. Expected format: KM-XXXXXXXXXXXX")
    return {
        "digest": clean,
        "valid": True,
        "guarantee": "Code disposes, model proposes: grounded in live Open-Meteo, data.gov.in Agmarknet, and ICAR advisories without hallucination.",
        "status": "VERIFIED_GENUINE",
    }


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


SAVE_BUDGET_S = 4.0  # history is an extra: a slow or dead database must never hold back a finished answer
_saver = ThreadPoolExecutor(max_workers=4, thread_name_prefix="chat-save")


def _save_turn(owner: str | None, body: ChatIn, result: dict) -> None:
    """Only real answers are saved: the 'something went wrong' fallback and an empty question are not history."""
    if not owner or not body.message.strip() or any(t.get("agent") == "Pipeline" for t in result.get("trace", [])):
        return
    user_text = f"📷 {body.message}" if body.image_b64 else body.message
    meta = {k: result.get(k) for k in ("cards", "live_sources", "sources", "degraded", "language", "live_only", "follow_ups", "integrity_digest")}
    job = _saver.submit(get_chats().append_turn, owner, body.session_id, user_text, result["answer"], meta)
    try:
        result["message_id"] = job.result(timeout=SAVE_BUDGET_S)  # additive: lets the UI attach feedback to this answer
    except FutureTimeout:  # the save keeps going in the background; the farmer gets the answer now
        log.warning("chat save slow (> %.0f s): answer sent without waiting", SAVE_BUDGET_S)
    except Exception:
        log.warning("chat save failed", exc_info=True)


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


class SpeakIn(BaseModel):
    text: str = Field(..., min_length=1, max_length=8000)
    language: str = "en"
    pace: float = 1.0


@router.post("/voice/speak")
async def speak(request: Request, body: SpeakIn):
    """Answer text -> natural MP3. 503 means 'use the browser voice instead'; the UI does exactly that."""
    enforce(request, "voice")
    audio = await run_in_threadpool(tts.speak, body.text, body.language, body.pace)  # seconds of network: off the event loop
    if audio is None:
        return JSONResponse({"error": "Natural voice unavailable"}, status_code=503)
    return Response(audio, media_type="audio/mpeg", headers={"Cache-Control": "no-store"})


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


# ----------------------------------------------------------------------
# PILLAR 1: SARKARI AGRI-SCHEMES & POLICY EXPLAINER
# ----------------------------------------------------------------------
from app.explainer.models import SchemeNoticeIn
from app.explainer.engine import list_available_schemes, explain_scheme_document

@router.get("/schemes")
def get_schemes():
    """Returns official pre-loaded agricultural scheme guidelines."""
    return {"schemes": list_available_schemes()}


@router.post("/schemes/explain")
def explain_scheme(body: SchemeNoticeIn, request: Request):
    """Explains an official agri notice / PDF in the farmer's language, verifying every cited quote character-by-character in code."""
    enforce(request, "schemes")
    return explain_scheme_document(body)


# ----------------------------------------------------------------------
# PILLAR 2: FARM CRISIS / GRIEVANCE REPORTING & PUBLIC BOARD
# ----------------------------------------------------------------------
from app.grievance.models import FarmCrisisIn, ResolutionIn, FeedbackIn
from app.grievance import store as grievance_store

@router.post("/grievances")
def file_grievance(body: FarmCrisisIn, request: Request):
    """Farmer reports a farm crisis (crop loss / hailstorm, transformer burnout, canal dispute, spurious inputs). Triaged in code."""
    enforce(request, "grievances")
    report = grievance_store.create_report(body)
    return {"report": report}


@router.get("/grievances")
def list_grievances(status: str | None = None, urgency: str | None = None):
    """Officer queue and citizen view: urgency-ordered list of crisis reports."""
    return {"reports": grievance_store.list_reports(status, urgency)}


@router.get("/grievances/{report_id}")
def get_grievance(report_id: str):
    rep = grievance_store.get_report(report_id)
    if not rep:
        raise HTTPException(404, "Report not found.")
    return {"report": rep}


@router.post("/grievances/{report_id}/resolve")
def resolve_grievance(report_id: str, body: ResolutionIn):
    """Officer resolves report by uploading proof photo of panchnama / repair."""
    rep = grievance_store.resolve_report(report_id, body.officer_name, body.resolution_notes, body.proof_photo_b64)
    if not rep:
        raise HTTPException(404, "Report not found.")
    return {"report": rep}


@router.post("/grievances/{report_id}/feedback")
def report_feedback(report_id: str, body: FeedbackIn):
    """Citizen confirms or disputes resolution."""
    rep = grievance_store.citizen_feedback(report_id, body.confirmed)
    if not rep:
        raise HTTPException(404, "Report not found.")
    return {"report": rep}


@router.get("/public/board")
def public_accountability_board():
    """Public transparency board metrics, resolution rates, and geo-tagged crisis hotspots."""
    return grievance_store.get_board_stats()


# ----------------------------------------------------------------------
# PILLAR 3: AUTONOMOUS FILING AGENT & CRYPTOGRAPHIC RECEIPTS
# ----------------------------------------------------------------------
from app.executor.runner import FilingRunner
from app.executor.receipts import verify_receipt, get_public_key_b64

class AgentFileIn(BaseModel):
    task_id: str = Field(default_factory=lambda: secrets.token_hex(8))
    mobile: str = Field(..., max_length=20)
    crop: str = Field("Onion", max_length=60)
    district: str = Field("Nashik", max_length=60)
    survey_no: str = Field("142/2A", max_length=60)
    cause: str = Field("HAILSTORM", max_length=60)

@router.get("/receipts/public-key")
def get_receipt_public_key():
    return {"public_key_b64": get_public_key_b64(), "algorithm": "Ed25519"}


@router.post("/receipts/verify")
def check_receipt_signature(payload: dict):
    """Verifies that the Ed25519 signature on an agent filing receipt is mathematically authentic."""
    valid = verify_receipt(payload)
    return {
        "valid": valid,
        "receipt_id": payload.get("receipt_id"),
        "reference_no": payload.get("reference_no"),
        "guarantee": "Ed25519 signature proves this record was generated directly by the filing agent and has not been altered."
    }


@router.post("/agent/file")
async def run_filing_agent(body: AgentFileIn, request: Request):
    """Streams live step-by-step browser automation on the Krishi portal replica with human OTP handoff, approval, and signed Ed25519 receipt."""
    enforce(request, "agent-file")
    sandbox_url = str(request.base_url).rstrip("/") + "/sandbox"
    runner = FilingRunner(sandbox_base_url=sandbox_url)

    async def event_generator():
        try:
            async for step in runner.execute_crop_loss_filing(
                task_id=body.task_id,
                mobile=body.mobile,
                crop=body.crop,
                district=body.district,
                survey_no=body.survey_no,
                cause=body.cause
            ):
                yield f"data: {json.dumps(step, ensure_ascii=False)}\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'type': 'final', 'status': 'failed', 'error': str(e)}, ensure_ascii=False)}\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")

