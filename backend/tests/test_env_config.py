"""Env-file loading + startup diagnostics. No real secrets anywhere.

The `.env` files written here contain obvious placeholder values only.
"""

from app.config import Settings, _load_env_file
from app.services import ai_service
import pytest


def test_dotenv_loads_cwd_file_without_override(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".env").write_text("GEMINI_API_KEY=test-key-from-file-not-real\n", encoding="utf-8")
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("VERDANTRA_NO_DOTENV", raising=False)
    assert Settings().gemini_api_key == "test-key-from-file-not-real"
    # Real environment always wins over the file.
    monkeypatch.setenv("GEMINI_API_KEY", "test-key-from-env-not-real")
    assert Settings().gemini_api_key == "test-key-from-env-not-real"


def test_dotenv_opt_out_and_missing_file(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)  # empty dir: no .env anywhere relevant
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.setenv("VERDANTRA_NO_DOTENV", "1")
    (tmp_path / ".env").write_text("GEMINI_API_KEY=test-key-ignored-not-real\n", encoding="utf-8")
    assert _load_env_file() is None
    assert Settings().gemini_api_key == ""


def test_missing_key_maps_to_unavailable_not_other_codes():
    with pytest.raises(ai_service.AIError) as exc:
        ai_service.GeminiAdapter(model_id="gemma-4-26b-a4b-it", api_key="").analyze(
            b"img", "image/jpeg", None)
    assert (exc.value.code, exc.value.status) == ("ai_unavailable", 503)


def test_default_model_id_is_gemini_26b(monkeypatch):
    monkeypatch.setenv("VERDANTRA_NO_DOTENV", "1")
    monkeypatch.delenv("AI_MODEL_ID", raising=False)
    assert Settings().ai_model_id == "gemma-4-26b-a4b-it"


def test_startup_warns_on_missing_key_without_value(settings, monkeypatch):
    # Pure helper (lifespan thread output is not reliably capturable):
    # names the variable, never its value.
    from app.main import startup_ai_warning

    assert startup_ai_warning(settings) == (
        "verdantra: GEMINI_API_KEY not set; AI will report unavailable")
    monkeypatch.setenv("GEMINI_API_KEY", "placeholder-not-a-real-key")
    from app.config import Settings as FreshSettings
    assert startup_ai_warning(FreshSettings()) is None
