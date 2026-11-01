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

    # --- Sign in with Google (optional: empty client id = the button is hidden and the app works anonymously) ----
    google_client_id: str = ""  # OAuth 2.0 Web client ID from console.cloud.google.com (public value, not a secret)
    session_secret: str = ""  # signs the login cookie; empty = random per start (everyone is signed out on restart)
    session_days: int = 14

    # --- LLM providers (any OpenAI-compatible endpoint) -----------------
    # Primary: Groq (fast + free tier). Fallback: any second provider.
    llm_base_url: str = "https://api.groq.com/openai/v1"
    llm_api_key: str = ""
    llm_extra_api_keys: str = ""  # comma-separated spare keys (other Groq accounts): used when one key's free quota is spent
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

    database_url: str = ""  # hosted Postgres (e.g. Neon) for chats + users; empty or unreachable = SQLite below. Never log it: it holds the password
    chat_db_path: str = ""  # saved chats (SQLite); empty = backend/data/chats.db. Point at a mounted disk to survive redeploys

    # --- Agents ----------------------------------------------------------
    max_self_corrections: int = 2
    history_turns: int = 6


def llm_keys(s: "Settings") -> list[str]:
    """Every configured LLM key, main one first, no blanks or duplicates."""
    out: list[str] = []
    for k in [s.llm_api_key, *s.llm_extra_api_keys.split(",")]:
        k = k.strip()
        if k and k not in out:
            out.append(k)
    return out


@lru_cache
def get_settings() -> Settings:
    return Settings()
