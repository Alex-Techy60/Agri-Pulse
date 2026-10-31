import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.api.routes import router
from app.core.config import get_settings
from app.memory.store import KNOWLEDGE, get_store

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
for _noisy in ("httpx", "httpcore"):  # httpx logs full request URLs at INFO, and the data.gov.in key travels in the URL
    logging.getLogger(_noisy).setLevel(logging.WARNING)
KNOWLEDGE_DIR = Path(__file__).parent.parent / "data" / "knowledge"
DIST = Path(__file__).parent.parent.parent / "frontend" / "dist"


@asynccontextmanager
async def lifespan(_: FastAPI):
    store = get_store()
    if store.count(KNOWLEDGE) == 0 and KNOWLEDGE_DIR.exists():
        n = store.seed_dir(KNOWLEDGE_DIR)
        logging.getLogger("startup").info("seeded %d knowledge chunks", n)
    if not get_settings().llm_api_key:
        logging.getLogger("startup").warning("LLM_API_KEY not set -> running in OFFLINE mode (retrieval only)")
    yield


s = get_settings()
app = FastAPI(title=s.app_name, lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    # Explicit origins from CORS_ORIGINS env var (for deployed URLs).
    # allow_origin_regex covers every localhost port automatically so the app
    # works on any machine regardless of which port Vite picks (5173-5179…).
    allow_origins=[o.strip() for o in s.cors_origins.split(",") if o.strip()],
    allow_origin_regex=r"https?://(localhost|127\.0\.0\.1)(:\d+)?",
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(router)

def mount_spa(application: FastAPI, dist: Path) -> None:
    """One-container deploy: serve the built SPA from the API (`npm run build` first).
    Only real page routes fall back to index.html. A missing file (favicon.ico, robots.txt, a stale .js) or an unknown /api path
    is a 404: answering them with HTML 200 made browsers try to decode the page as an icon and hid API typos."""
    if not dist.exists():
        return
    application.mount("/assets", StaticFiles(directory=dist / "assets"), name="assets")

    @application.get("/{path:path}", include_in_schema=False)
    def spa(path: str):
        f = (dist / path).resolve()
        if path and f.is_file() and dist.resolve() in f.parents:  # block ../ traversal
            return FileResponse(f)
        if path.startswith("api/") or path == "api" or Path(path).suffix:
            raise HTTPException(404, "Not found.")
        return FileResponse(dist / "index.html")


mount_spa(app, DIST)
