"""
Configuration for the OpenRouter-backed invoice AI agent.

Values are read from backend/agent/.env (see .env.example). Real process
environment variables take precedence over the file.
"""
import os
from pathlib import Path

ENV_FILE = Path(__file__).resolve().parent / ".env"


def _load_env_file(path: Path) -> None:
    """Minimal .env loader (KEY=VALUE lines) without extra dependencies."""
    if not path.is_file():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key:
            os.environ.setdefault(key, value)


_load_env_file(ENV_FILE)

AI_PROVIDER = "openrouter"

OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "").strip()
OPENROUTER_BASE_URL = os.getenv(
    "OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1"
).rstrip("/")
AI_MODEL = os.getenv(
    "OPENROUTER_MODEL", "meta-llama/llama-3.3-70b-instruct:free"
).strip()
OPENROUTER_TIMEOUT = float(os.getenv("OPENROUTER_TIMEOUT", "60"))

# Optional OpenRouter attribution headers
OPENROUTER_APP_NAME = os.getenv("OPENROUTER_APP_NAME", "Invoice Processing System")
OPENROUTER_SITE_URL = os.getenv("OPENROUTER_SITE_URL", "http://localhost")

# Upper bound on invoice text sent to the model
AI_MAX_INPUT_CHARS = int(os.getenv("AI_MAX_INPUT_CHARS", "20000"))
