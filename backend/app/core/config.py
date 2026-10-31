"""All configuration lives here. Never read os.environ anywhere else."""
from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# repo-root/.env (works whether you start the API from backend/ or the repo root)
ROOT_ENV = Path(__file__).resolve().parents[3] / ".env"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=(str(ROOT_ENV), ".env"), extra="ignore")

    app_name: str = "KisaanMitra"
    domain: str = "farm"  # which module in app/domain/ to load

    # --- Live data sources (NO dummy data: every value must come from a live source) --------------------
    data_gov_api_key: str = ""  # free key from data.gov.in (mandi prices)
    mandi_resource_id: str = "9ef84268-d588-465a-a308-a864a43d0070"  # confirm with `make check-live`
    mandi_history_resource_id: str = "35985678-0d79-46b4-9ed6-6f13308a1d24"  # dated prices; the resource above is today-only
    mandi_filter_style: str = "auto"  # auto | lower | title  (data.gov.in field-name case)
    mandi_days: int = 10  # history window: must reach the day the 7-day trend compares with (5-9 days back)
    cache_ttl_s: float = 900.0  # live-data cache (stale real data is shown labelled if the source is down)
    tool_timeout_s: float = 8.0
    cors_origins: str = ""  # comma-separated deployed origins (e.g. https://kisaanmitra.onrender.com); localhost is always allowed via regex in main.py
    ingest_api_key: str = ""  # empty = /api/ingest disabled; set to enable (send as X-Admin-Key)
    rate_limit_per_min: int = 20  # chat requests per client+session per minute (0 = off)

    # --- LLM providers (any OpenAI-compatible endpoint) -----------------
    # Primary: Groq (fast + free tier). Fallback: any second provider.
    llm_base_url: str = "https://api.groq.com/openai/v1"
    llm_api_key: str = ""
    llm_model: str = "openai/gpt-oss-120b"
    llm_fast_model: str = "openai/gpt-oss-20b"  # router / cheap calls
    llm_vision_model: str = "qwen/qwen3.8-27b"
    stt_model: str = "whisper-large-v3-turbo"

    fallback_base_url: str = ""  # e.g. https://openrouter.ai/api/v1
    fallback_api_key: str = ""
    fallback_model: str = ""

    # Extra fallback providers, tried in order after FALLBACK_* (all OpenAI-compatible, all optional).
    fallback2_base_url: str = ""
    fallback2_api_key: str = ""
    fallback2_model: str = ""
    fallback3_base_url: str = ""
    fallback3_api_key: str = ""
    fallback3_model: str = ""

    llm_timeout_s: float = 25.0
    llm_temperature: float = 0.3

    # --- Memory ----------------------------------------------------------
    qdrant_url: str = ""  # empty => in-process memory (zero setup)
    qdrant_api_key: str = ""
    embeddings: str = "hash"  # "hash" (offline, no download) | "fastembed"
    embed_dim: int = 256  # only for "hash"
    rag_top_k: int = 6
    rag_min_score: float = 0.05

    chat_db_path: str = ""  # saved chats (SQLite); empty = backend/data/chats.db. Point at a mounted disk to survive redeploys

    # --- Agricultural inputs (investment advisory) -----------------------
    # data.gov.in resource ID for live fertilizer price dataset (optional; leave empty to use Govt MRP only).
    fertilizer_resource_id: str = ""

    # Government-fixed fertilizer MRP (Rs per bag) — PIB/MoAFW notification, updated by policy (not market).
    # Set via env vars (FERTILIZER_MRP_UREA etc.) to override without code changes.
    # Defaults: 2025-2026 notified MRP (Source: PIB press release dated April 2024 / MoAFW circular).
    fertilizer_mrp_urea: float = 242.0   # 45 kg bag, N 46%
    fertilizer_mrp_dap: float = 1350.0   # 50 kg bag, N 18% P 46%
    fertilizer_mrp_mop: float = 1700.0   # 50 kg bag, K 60%
    fertilizer_mrp_npk: float = 1470.0   # 50 kg bag, NPK 10:26:26

    # --- Agents ----------------------------------------------------------
    max_self_corrections: int = 2
    history_turns: int = 6


@lru_cache
def get_settings() -> Settings:
    return Settings()
