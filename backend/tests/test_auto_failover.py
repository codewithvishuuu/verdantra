"""Explicit provider isolation: mocked transports only. No network, no keys, no billing.

`AI_PROVIDER=auto` was removed: `build_service` rejects it, and these tests
prove each explicit mode stays inside its own backend. Live behavior with a
real local model is NOT verified here.
"""

import builtins
import json

import pytest

from app.services import ai_service
from tests.conftest import VALID_ANALYSIS, make_image

GEMINI_ID = "gemma-4-26b-a4b-it"
OLLAMA_ID = "gemma4:e2b"


class FakeBackend:
    def __init__(self, model_id, behavior="ok"):
        self.model_id = model_id
        self.behavior = behavior
        self._timeout_s = 120  # mirrors the real adapters' configured timeout
        self.calls = 0
        self.pings = 0

    def ping(self):
        self.pings += 1
        return self.behavior == "ok"

    def analyze(self, image_bytes, mime, hint):
        self.calls += 1
        if self.behavior == "ok":
            out = dict(VALID_ANALYSIS)
            out["model_id"] = self.model_id
            return out
        raise {"timeout": ai_service.AITimeout("slow"),
               "quota": ai_service.AIQuotaError("limited"),
               "auth": ai_service.AIAuthError("bad key"),
               "bad": ai_service.AIBadResponse("broken"),
               "boom": ai_service.AIError("gone"),
               "down": ai_service.AIError("gone")}[self.behavior]


def test_gemini_mode_never_touches_localhost(monkeypatch):
    def forbidden_urlopen(*args, **kwargs):
        raise AssertionError("gemini mode must not open any URL")

    def boom(_b, _m, _p):
        raise ai_service.AIAuthError("bad key")

    monkeypatch.setattr("urllib.request.urlopen", forbidden_urlopen)
    adapter = ai_service.build_service("m", "k", 120, provider="gemini")
    assert isinstance(adapter, ai_service.GeminiAdapter)
    # Caller seam fails like a rejected key; any localhost dial would trip above.
    failing = ai_service.GeminiAdapter(model_id="m", api_key="k", caller=boom)
    with pytest.raises(ai_service.AIAuthError):
        failing.analyze(b"img", "image/jpeg", None)


def test_ollama_mode_never_touches_google(monkeypatch):
    real_import = builtins.__import__

    def guarded(name, *args, **kwargs):
        assert not str(name).startswith("google"), "ollama mode must not import google SDKs"
        return real_import(name, *args, **kwargs)

    class FakeResp:
        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def read(self):
            return json.dumps({"message": {"content": json.dumps(VALID_ANALYSIS)}}).encode()

    monkeypatch.setattr("urllib.request.urlopen", lambda req: FakeResp())
    monkeypatch.setattr("builtins.__import__", guarded)
    adapter = ai_service.build_service("m", "k", 120, provider="ollama",
                                       ollama_host="http://localhost:11434",
                                       ollama_model=OLLAMA_ID)
    assert isinstance(adapter, ai_service.OllamaAdapter)
    out = adapter.analyze(b"img", "image/jpeg", None)
    assert out["model_id"] == OLLAMA_ID


def test_invalid_provider_fails_fast():
    # "auto" is rejected exactly like any other unknown value; empty/None
    # keeps the historical default-to-gemini behavior and is covered by config.
    for bad in ("auto", "auto-pilot", "gemini-cloud"):
        with pytest.raises(ValueError):
            ai_service.build_service("m", "k", 120, provider=bad)
    assert isinstance(ai_service.build_service("m", "k", 120, provider="GEMINI"),
                      ai_service.GeminiAdapter)
    assert isinstance(ai_service.build_service("m", "k", 120, provider=" Ollama "),
                      ai_service.OllamaAdapter)


def test_health_reports_selected_provider(monkeypatch, tmp_path):
    from app.main import create_app
    from app.config import Settings
    from fastapi.testclient import TestClient

    for provider, expected_id in (("gemini", GEMINI_ID), ("ollama", OLLAMA_ID)):
        monkeypatch.setenv("AI_PROVIDER", provider)
        monkeypatch.setenv("DATABASE_PATH", str(tmp_path / ("%s.db" % provider)))
        monkeypatch.setenv("UPLOAD_DIR", str(tmp_path / provider))
        with TestClient(create_app(Settings())) as client:
            body = client.get("/healthz").json()
            assert body["provider"] == provider
            assert body["model_id"] == expected_id


def test_explicit_failure_preserves_save_without_ai(monkeypatch, tmp_path):
    from app.main import create_app
    from app.config import Settings
    from fastapi.testclient import TestClient

    monkeypatch.setenv("AI_PROVIDER", "ollama")
    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "t.db"))
    monkeypatch.setenv("UPLOAD_DIR", str(tmp_path / "up"))
    app = create_app(Settings())
    with TestClient(app) as client:
        # Hermetic outage (no live backends involved): honest 503,
        # then save-without-AI still works.
        app.state.ai_service = FakeBackend(OLLAMA_ID, "down")
        res = client.post("/api/v1/observations/analyze",
                          files={"image": ("leaf.jpg", make_image("JPEG"), "image/jpeg")})
        assert res.status_code == 503
        temp_id = res.json()["error"]["details"]["temp_image_id"]
        save = client.post("/api/v1/journal-entries", json={
            "temp_image_id": temp_id, "ai_analysis": None,
            "user_notes": "Offline and AI-less; watched ants.", "experiment_done": False})
        assert save.status_code == 201, save.text
        assert save.json()["analysis"] is None
