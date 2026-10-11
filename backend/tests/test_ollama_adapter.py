"""Ollama adapter: request format, validation, failures. Provider fully mocked.

No network, no Ollama binary, no model needed. Live image analysis is NOT
verified by these tests — see AI_SYSTEM.md; the owner verifies with a real
image via the manual commands in the task report.
"""

import base64
import io
import json
import urllib.error

import pytest

from app.services import ai_service
from tests.conftest import VALID_ANALYSIS, make_image

HOST = "http://localhost:11434"
MODEL = "gemma4:e2b"


class FakeResp:
    def __init__(self, payload, status=200):
        self._body = json.dumps(payload).encode("utf-8")
        self.status = status

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def read(self):
        return self._body


def chat_ok(_req):
    return FakeResp({"message": {"content": json.dumps(VALID_ANALYSIS)}})


def adapter(**kw):
    kw.setdefault("model_id", MODEL)
    kw.setdefault("host", HOST)
    kw.setdefault("timeout_s", 30)
    return ai_service.OllamaAdapter(**kw)


def test_success_returns_validated_dict(monkeypatch):
    monkeypatch.setattr("urllib.request.urlopen", chat_ok)
    out = adapter().analyze(make_image("JPEG"), "image/jpeg", None)
    assert out["model_id"] == MODEL and out["analyzed_at"]
    assert out["observed_features"] == VALID_ANALYSIS["observed_features"]


def test_image_request_format_and_provider_isolation(monkeypatch):
    seen = {}

    def capture(req):
        seen["url"] = req.full_url
        seen["body"] = req.data.decode("utf-8")
        return chat_ok(req)

    monkeypatch.setattr("urllib.request.urlopen", capture)
    raw = make_image("JPEG")
    adapter().analyze(raw, "image/jpeg", "near the path")
    assert seen["url"] == HOST + "/api/chat"
    body = json.loads(seen["body"])
    assert body["model"] == MODEL and body["stream"] is False
    assert body["messages"][1]["images"] == [base64.b64encode(raw).decode("ascii")]
    assert "near the path" in body["messages"][1]["content"]
    # Isolation: nothing Google- or key-shaped may appear in the request.
    assert "googleapis" not in seen["body"] and "googleapis" not in seen["url"]
    assert "AIza" not in seen["body"] and "GEMINI" not in seen["body"]


def test_missing_model_is_safe_unavailable(monkeypatch):
    def gone(_req):
        raise urllib.error.HTTPError(HOST + "/api/chat", 404, "Not Found", {}, io.BytesIO(b""))
    monkeypatch.setattr("urllib.request.urlopen", gone)
    with pytest.raises(ai_service.AIError) as e:
        adapter().analyze(make_image("JPEG"), "image/jpeg", None)
    assert (e.value.code, e.value.status) == ("ai_unavailable", 503)


def test_connection_failure_is_safe_unavailable(monkeypatch):
    def down(_req):
        raise urllib.error.URLError("[WinError 10061] refused")
    monkeypatch.setattr("urllib.request.urlopen", down)
    with pytest.raises(ai_service.AIError) as e:
        adapter().analyze(make_image("JPEG"), "image/jpeg", None)
    assert (e.value.code, e.value.status) == ("ai_unavailable", 503)


def test_invalid_responses_then_repair(monkeypatch):
    calls = []

    def flaky(_req):
        calls.append(1)
        if len(calls) == 1:
            return FakeResp({"message": {"content": "not json {"}})
        return chat_ok(_req)

    monkeypatch.setattr("urllib.request.urlopen", flaky)
    adapter().analyze(make_image("JPEG"), "image/jpeg", None)
    assert len(calls) == 2

    def still_bad(_req):
        return FakeResp({"message": {"content": "still bad"}})

    monkeypatch.setattr("urllib.request.urlopen", still_bad)
    with pytest.raises(ai_service.AIBadResponse) as e:
        adapter().analyze(make_image("JPEG"), "image/jpeg", None)
    assert (e.value.code, e.value.status) == ("ai_bad_response", 502)

    def wrong_shape(_req):
        return FakeResp({"nope": 1})

    monkeypatch.setattr("urllib.request.urlopen", wrong_shape)
    with pytest.raises(ai_service.AIBadResponse):
        adapter().analyze(make_image("JPEG"), "image/jpeg", None)


def test_timeout(monkeypatch):
    import time

    def slow(_req):
        time.sleep(5)
        return chat_ok(_req)

    monkeypatch.setattr("urllib.request.urlopen", slow)
    with pytest.raises(ai_service.AITimeout):
        adapter(timeout_s=0).analyze(make_image("JPEG"), "image/jpeg", None)


def test_ping_checks_server_and_model(monkeypatch):
    monkeypatch.setattr("urllib.request.urlopen",
                        lambda _r, **_k: FakeResp({"models": [{"name": MODEL}]}))
    assert adapter().ping() is True
    monkeypatch.setattr("urllib.request.urlopen",
                        lambda _r, **_k: FakeResp({"models": [{"name": "other:tag"}]}))
    assert adapter().ping() is False

    def down(_r, **_k):
        raise urllib.error.URLError("refused")
    monkeypatch.setattr("urllib.request.urlopen", down)
    assert adapter().ping() is False


def test_build_service_selects_exactly_one_backend():
    gemini = ai_service.build_service("m", "k", 1, provider="gemini")
    ollama = ai_service.build_service("m", "k", 1, provider="ollama",
                                      ollama_host=HOST, ollama_model=MODEL)
    assert isinstance(gemini, ai_service.GeminiAdapter)
    assert isinstance(ollama, ai_service.OllamaAdapter)
    assert ollama.model_id == MODEL
    with pytest.raises(ValueError):
        ai_service.build_service("m", "k", 1, provider="mystery-cloud")
    with pytest.raises(ValueError):
        ai_service.build_service("m", "k", 1, provider="  OLLAMA-cloud ")


def test_analyze_route_with_ollama_provider(monkeypatch, tmp_path):
    # End-to-end wiring (route -> OllamaAdapter -> request format) with the
    # provider HTTP layer mocked: proves selection + contract, zero network.
    from fastapi.testclient import TestClient

    from app.config import Settings
    from app.main import create_app

    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "t.db"))
    monkeypatch.setenv("UPLOAD_DIR", str(tmp_path / "up"))
    monkeypatch.setenv("AI_PROVIDER", "ollama")
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.setattr("urllib.request.urlopen", chat_ok)
    with TestClient(create_app(Settings())) as client:
        res = client.post(
            "/api/v1/observations/analyze",
            files={"image": ("leaf.jpg", make_image("JPEG"), "image/jpeg")})
    assert res.status_code == 200, res.text
    assert res.json()["analysis"]["model_id"] == MODEL
