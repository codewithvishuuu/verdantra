"""Health: honest db/ai status, envelope on db outage."""

from app.main import create_app
from fastapi.testclient import TestClient
from tests.conftest import StubAI


def test_health_degraded_without_key(app_client):
    client, app = app_client
    # Mirror the real keyless adapter: ping is False when unconfigured.
    app.state.ai_service = StubAI("ok", ping_result=False)
    res = client.get("/healthz")
    assert res.status_code == 200
    body = res.json()
    assert body["status"] == "degraded" and body["db"] == "ok"
    assert body["ai"] == "unavailable" and body["model_id"] == "gemma-4-26b-a4b-it"
    assert isinstance(body["uptime_s"], int)


def test_health_db_outage_is_503_envelope(settings, tmp_path):
    import os
    settings.database_path = str(tmp_path / "is_a_directory")
    os.mkdir(settings.database_path)  # sqlite cannot open a directory
    app = create_app(settings)
    with TestClient(app) as client:
        app.state.ai_service = StubAI("ok")
        res = client.get("/healthz")
    assert res.status_code == 503
    assert res.json()["error"]["code"] == "db_unavailable"
    assert res.headers["X-Request-Id"]
