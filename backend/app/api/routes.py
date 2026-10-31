import json
import logging
import secrets

import httpx
from fastapi.concurrency import run_in_threadpool

from fastapi import APIRouter, File, Form, Header, HTTPException, Request, UploadFile
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from app.agents.orchestrator import ChatResult, TraceStep, get_orchestrator
from app.api.ratelimit import enforce
from app.core import stats
from app.core.config import get_settings
from app.llm.client import get_llm
from app.memory.store import KNOWLEDGE, MEMORY, get_store

router = APIRouter(prefix="/api")
log = logging.getLogger("api")
MAX_AUDIO_BYTES = 5_000_000
MAX_INGEST_TEXTS, MAX_INGEST_CHARS = 50, 5000


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
        "llm_configured": bool(s.llm_api_key),
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


@router.post("/chat")
def chat(body: ChatIn, request: Request):
    enforce(request, body.session_id)
    try:
        return get_orchestrator().run(body.message, body.session_id, body.language, body.image_b64, body.profile).dict()
    except Exception:
        log.error("chat pipeline error", exc_info=True)
        return _error_result(body.language)


@router.post("/chat/stream")
def chat_stream(body: ChatIn, request: Request):
    """Server-sent events: one `trace` event per pipeline step, then one `final`."""
    enforce(request, body.session_id)
    orch = get_orchestrator()

    def gen():
        try:
            for ev in orch.stream(body.message, body.session_id, body.language, body.image_b64, body.profile):
                if ev["type"] == "final":
                    ev = {"type": "final", "result": ev["result"].dict()}
                yield f"data: {json.dumps(ev, ensure_ascii=False)}\n\n"
        except Exception:
            log.error("chat stream error", exc_info=True)
            yield f"data: {json.dumps({'type': 'final', 'result': _error_result(body.language)}, ensure_ascii=False)}\n\n"

    return StreamingResponse(gen(), media_type="text/event-stream", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


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
