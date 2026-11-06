"""Hugging Face Spaces entrypoint (Gradio SDK slot): serves the existing FastAPI app + built UI on port 7860."""
import os
import sys
from pathlib import Path

BACKEND = Path(__file__).parent / "backend"
os.chdir(BACKEND)  # config and relative data paths resolve from backend/
sys.path.insert(0, str(BACKEND))

import uvicorn  # noqa: E402
from app.main import app  # noqa: E402

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", 7860)),
                proxy_headers=True, forwarded_allow_ips="*")
