"""Verdantra backend configuration — environment only (ARCHITECTURE.md section 4).

Every value comes from the process environment. No defaults for secrets,
no secret values in code, logs, or errors. See SECURITY.md section 2.
"""

import os

APP_VERSION = "0.2.0"

AI_MODEL_ID_DEFAULT = "gemma-4-26b-a4b-it"


def _getenv(name: str, default: str = "") -> str:
    return os.environ.get(name, default)


class Settings:
    """Snapshot of process-env configuration. Construct per use (tests override env)."""

    def __init__(self) -> None:
        self.database_path = _getenv("DATABASE_PATH", "data/verdantra.db")
        self.upload_dir = _getenv("UPLOAD_DIR", "data/uploads")
        # Secret: presence is checkable, value is never printed/logged/returned.
        self.gemini_api_key = _getenv("GEMINI_API_KEY", "")
        self.ai_model_id = _getenv("AI_MODEL_ID", AI_MODEL_ID_DEFAULT)
        # Provider selection: "gemini" (hosted, default — preserves behavior)
        # or "ollama" (local-only; never calls Google). Unknown values fail
        # fast at startup instead of silently picking a backend.
        self.ai_provider = _getenv("AI_PROVIDER", "gemini").strip().lower()
        self.ollama_host = _getenv("OLLAMA_HOST", "http://localhost:11434").rstrip("/")
        self.ollama_model = _getenv("OLLAMA_MODEL", "gemma4:e2b")
        self.ai_timeout_s = int(_getenv("AI_TIMEOUT_S", "120"))  # provisional (see AI_SYSTEM.md)
        self.max_image_mb = int(_getenv("MAX_IMAGE_MB", "10"))
        # Provider payload + generation bounds (all provisional, documented per-call).
        self.transmit_max_edge = int(_getenv("TRANSMIT_MAX_EDGE", "2048"))
        self.transmit_jpeg_quality = int(_getenv("TRANSMIT_JPEG_QUALITY", "82"))
        self.gemini_max_output_tokens = int(_getenv("GEMINI_MAX_OUTPUT_TOKENS", "1024"))
        self.ollama_num_ctx = int(_getenv("OLLAMA_NUM_CTX", "4096"))
        self.ollama_num_predict = int(_getenv("OLLAMA_NUM_PREDICT", "1024"))
        self.ollama_keep_alive = _getenv("OLLAMA_KEEP_ALIVE", "5m")
        # Auto-mode primary bound (provisional): hosted should answer fast or
        # fail fast; the patient budget belongs to the local fallback. Without
        # this, one request could wait AI_TIMEOUT_S twice (see AI_SYSTEM.md).
        self.auto_primary_timeout_s = int(_getenv("AUTO_PRIMARY_TIMEOUT_S", "60"))
        # CPU lever, Ollama-only: 0 = server default (all cores, fastest but
        # loudest); set 2-4 to trade speed for thermals. Never sent to Gemini.
        self.ollama_num_thread = int(_getenv("OLLAMA_NUM_THREAD", "0"))
        raw_origins = _getenv("CORS_ORIGINS", "http://localhost:5173")
        self.cors_origins = [o.strip() for o in raw_origins.split(",") if o.strip()]

    @property
    def has_ai_credentials(self) -> bool:
        return bool(self.gemini_api_key)

    @property
    def max_image_bytes(self) -> int:
        return self.max_image_mb * 1024 * 1024
