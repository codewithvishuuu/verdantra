"""Config: env-only, safe defaults, no secret printing."""

from app.config import APP_VERSION, Settings


def test_defaults_no_key(monkeypatch):
    monkeypatch.setenv("VERDANTRA_NO_DOTENV", "1")
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("AI_MODEL_ID", raising=False)
    monkeypatch.delenv("AI_TIMEOUT_S", raising=False)
    monkeypatch.delenv("MAX_IMAGE_MB", raising=False)
    s = Settings()
    assert s.ai_model_id == "gemma-4-26b-a4b-it"
    assert s.ai_timeout_s == 120  # provisional per AI_SYSTEM.md
    assert s.max_image_mb == 10
    assert s.max_image_bytes == 10 * 1024 * 1024
    assert s.has_ai_credentials is False
    assert s.cors_origins == ["http://localhost:5173"]
    assert APP_VERSION


def test_env_overrides(monkeypatch):
    monkeypatch.setenv("VERDANTRA_NO_DOTENV", "1")
    monkeypatch.setenv("GEMINI_API_KEY", "placeholder-not-a-real-key")
    monkeypatch.setenv("AI_TIMEOUT_S", "30")
    monkeypatch.setenv("CORS_ORIGINS", "https://a.example, https://b.example")
    s = Settings()
    assert s.has_ai_credentials is True
    assert s.ai_timeout_s == 30
    assert s.cors_origins == ["https://a.example", "https://b.example"]
