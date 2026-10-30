import json

from fastapi import APIRouter, File, Form, Request, UploadFile
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from app.agents.orchestrator import get_orchestrator
from app.api.ratelimit import enforce
from app.core import stats
from app.core.config import get_settings
from app.llm.client import get_llm
from app.memory.store import KNOWLEDGE, MEMORY, get_store

router = APIRouter(prefix="/api")


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
    return {"title": d.title, "tagline": d.tagline, "suggested_prompts": d.suggested_prompts, "languages": d.languages, "profile_fields": d.profile_fields}


@router.post("/chat")
def chat(body: ChatIn, request: Request):
    enforce(request, body.session_id)
    return get_orchestrator().run(body.message, body.session_id, body.language, body.image_b64, body.profile).dict()


@router.post("/chat/stream")
def chat_stream(body: ChatIn, request: Request):
    """Server-sent events: one `trace` event per pipeline step, then one `final`."""
    enforce(request, body.session_id)
    orch = get_orchestrator()

    def gen():
        for ev in orch.stream(body.message, body.session_id, body.language, body.image_b64, body.profile):
            if ev["type"] == "final":
                ev = {"type": "final", "result": ev["result"].dict()}
            yield f"data: {json.dumps(ev, ensure_ascii=False)}\n\n"

    return StreamingResponse(gen(), media_type="text/event-stream", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@router.get("/live-check")
def live_check(place: str = "Nashik, Maharashtra", crop: str = "Onion"):
    """Calls each live tool once and reports ok/source/first line. Use before every demo."""
    from app.tools import NeedsInput

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


@router.post("/voice/transcribe")
async def transcribe(file: UploadFile = File(...), language: str | None = Form(None)):
    try:
        text = get_llm().transcribe(await file.read(), file.filename or "audio.webm", language)
        return {"text": text}
    except Exception as e:
        return {"text": "", "error": f"{type(e).__name__}: {e}"}


@router.post("/ingest")
def ingest(payload: dict):
    """POST {"texts": ["...", "..."], "source": "name"} to add knowledge live (great demo moment)."""
    texts = [t for t in payload.get("texts", []) if isinstance(t, str) and t.strip()]
    n = get_store().add(KNOWLEDGE, texts, [{"source": payload.get("source", "live-upload")} for _ in texts])
    return {"added": n}
