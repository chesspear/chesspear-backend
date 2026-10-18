"""Environment-backed runtime settings. Secrets are read only from environment variables."""
from __future__ import annotations

import os
from dotenv import load_dotenv

load_dotenv()


def env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    normalized = value.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    # Fail closed for security-sensitive flags: a typo in AUTH_REQUIRED must not
    # silently disable authentication when the default is True.
    return default


def env_int(name: str, default: int, minimum: int, maximum: int) -> int:
    try:
        value = int(os.getenv(name, str(default)))
    except ValueError:
        value = default
    return max(minimum, min(value, maximum))


SERVICE_NAME = "chesspear-backend"
SERVICE_VERSION = "0.1.0"
API_PREFIX = "/api/v1"
AUTH_REQUIRED = env_bool("AUTH_REQUIRED", True)
SUPABASE_URL = os.getenv("SUPABASE_URL", "").rstrip("/")
SUPABASE_PUBLISHABLE_KEY = os.getenv("SUPABASE_PUBLISHABLE_KEY", os.getenv("SUPABASE_ANON_KEY", ""))
STOCKFISH_PATH = os.getenv("STOCKFISH_PATH", "/usr/local/bin/stockfish")
STOCKFISH_THREADS = env_int("STOCKFISH_THREADS", 1, 1, 8)
STOCKFISH_HASH_MB = env_int("STOCKFISH_HASH_MB", 128, 16, 1024)
MAX_ENGINE_CONCURRENCY = env_int("MAX_ENGINE_CONCURRENCY", 2, 1, 8)
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
REDIS_QUEUE_NAME = os.getenv("REDIS_QUEUE_NAME", "chesspear-analysis")
JOB_RESULT_TTL_SECONDS = env_int("JOB_RESULT_TTL_SECONDS", 86400, 3600, 604800)
JOB_TIMEOUT_SECONDS = env_int("JOB_TIMEOUT_SECONDS", 600, 60, 1800)
ALLOWED_ORIGINS = [
    origin.strip()
    for origin in os.getenv(
        "ALLOWED_ORIGINS",
        "http://localhost:3000,http://localhost:5173",
    ).split(",")
    if origin.strip()
]
