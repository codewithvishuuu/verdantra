"""Automatic failover: mocked transports only. No network, no keys, no billing.

Live fallback with a real local model is NOT verified here — the owner runs
the manual commands in the task report (pull, serve, real photo).
"""

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


def auto(gemini_behavior="ok", ollama_behavior="ok"):
    return ai_service.AutoAdapter(FakeBackend(GEMINI_ID, gemini_behavior),
                                  FakeBackend(OLLAMA_ID, ollama_behavior))


def test_gemini_success_never_touches_ollama():
    gemini, ollama = FakeBackend(GEMINI_ID), FakeBackend(OLLAMA_ID)
    adapter = ai_service.AutoAdapter(gemini, ollama)
    assert adapter.model_id == GEMINI_ID  # primary id before any call
    out = adapter.analyze(b"img", "image/jpeg", None)
    assert out["model_id"] == GEMINI_ID and ollama.calls == 0
    assert adapter.model_id == GEMINI_ID


def test_transport_failures_fall_back_once():
    for behavior in ("boom", "timeout", "quota"):
        gemini, ollama = FakeBackend(GEMINI_ID, behavior), FakeBackend(OLLAMA_ID)
        out = ai_service.AutoAdapter(gemini, ollama).analyze(b"img", "image/jpeg", None)
        assert out["model_id"] == OLLAMA_ID
        assert gemini.calls == 1 and ollama.calls == 1  # exactly one local attempt


def test_auth_and_bad_output_never_masked():
    for behavior in ("auth", "bad"):
        gemini, ollama = FakeBackend(GEMINI_ID, behavior), FakeBackend(OLLAMA_ID)
        with pytest.raises(ai_service.AIError):
            ai_service.AutoAdapter(gemini, ollama).analyze(b"img", "image/jpeg", None)
        assert ollama.calls == 0


def test_both_down_is_safe_error_with_model_tracking():
    adapter = auto("boom", "down")
    with pytest.raises(ai_service.AIError) as e:
        adapter.analyze(b"img", "image/jpeg", None)
    assert (e.value.code, e.value.status) == ("ai_unavailable", 503)


def test_ping_prefers_configured_but_accepts_either():
    gemini, ollama = FakeBackend(GEMINI_ID), FakeBackend(OLLAMA_ID, "down")
    assert ai_service.AutoAdapter(gemini, ollama).ping() is True
    assert ollama.pings == 0  # no local traffic when hosted answers
    assert auto("down", "ok").ping() is True
    assert auto("down", "down").ping() is False


def test_explicit_modes_never_switch():
    assert isinstance(ai_service.build_service("m", "k", 1, provider="gemini"),
                      ai_service.GeminiAdapter)
    assert isinstance(ai_service.build_service("m", "k", 1, provider="ollama"),
                      ai_service.OllamaAdapter)
    with pytest.raises(ValueError):
        ai_service.build_service("m", "k", 1, provider="auto-pilot")


def test_route_reports_provider_and_preserves_save_without_ai(monkeypatch, tmp_path):
    from app.main import create_app
    from app.config import Settings
    from fastapi.testclient import TestClient

    monkeypatch.setenv("AI_PROVIDER", "auto")
    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "t.db"))
    monkeypatch.setenv("UPLOAD_DIR", str(tmp_path / "up"))
    app = create_app(Settings())
    with TestClient(app) as client:
        assert app.state.ai_service.model_id == GEMINI_ID  # primary until first call
        assert client.get("/healthz").json()["provider"] == "auto"
        # Hermetic double failure (no live backends involved): honest 503,
        # then save-without-AI still works.
        app.state.ai_service = ai_service.AutoAdapter(FakeBackend(GEMINI_ID, "boom"),
                                                      FakeBackend(OLLAMA_ID, "down"))
        res = client.post("/api/v1/observations/analyze",
                          files={"image": ("leaf.jpg", make_image("JPEG"), "image/jpeg")})
        assert res.status_code == 503
        temp_id = res.json()["error"]["details"]["temp_image_id"]
        save = client.post("/api/v1/journal-entries", json={
            "temp_image_id": temp_id, "ai_analysis": None,
            "user_notes": "Offline and AI-less; watched ants.", "experiment_done": False})
        assert save.status_code == 201, save.text
        assert save.json()["analysis"] is None
