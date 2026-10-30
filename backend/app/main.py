import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.api.routes import router
from app.core.config import get_settings
from app.memory.store import KNOWLEDGE, get_store

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
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
    allow_origins=[o.strip() for o in s.cors_origins.split(",") if o.strip()],
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(router)

# One-container deploy: serve the built SPA from the API (`npm run build` first).
if DIST.exists():
    app.mount("/assets", StaticFiles(directory=DIST / "assets"), name="assets")

    @app.get("/{path:path}", include_in_schema=False)
    def spa(path: str):
        f = (DIST / path).resolve()
        safe = path and f.is_file() and DIST.resolve() in f.parents  # block ../ traversal
        return FileResponse(f if safe else DIST / "index.html")
