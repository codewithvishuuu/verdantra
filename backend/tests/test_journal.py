"""Journal CRUD: round-trip, validation codes, frozen snapshots, orphans, sweep."""

import os
import sqlite3

from app.services import journal as journal_service
from tests.conftest import StubAI, make_image


def test_round_trip_and_files_cleaned(app_client):
    client, app = app_client
    app.state.ai_service = StubAI("ok")
    res = client.post(
        "/api/v1/observations/analyze",
        files={"image": ("leaf.jpg", make_image("JPEG"), "image/jpeg")})
    assert res.status_code == 200
    analyzed = res.json()

    save = client.post("/api/v1/journal-entries", json={
        "temp_image_id": analyzed["temp_image_id"],
        "ai_analysis": analyzed["analysis"],
        "user_notes": "Sunny leaf looked curlier.",
        "experiment_done": True,
        "experiment_result": "Confirmed by eye.",
    })
    assert save.status_code == 201, save.text
    entry = save.json()
    assert entry["id"].startswith("entry_")
    assert entry["title"].startswith("Outdoor note · ")
    assert entry["analysis"] == analyzed["analysis"]  # frozen snapshot, byte-identical
    assert entry["experiment_result"] == "Confirmed by eye."

    listing = client.get("/api/v1/journal-entries").json()
    assert listing["total"] == 1 and listing["entries"][0]["id"] == entry["id"]
    assert listing["entries"][0]["has_ai"] is True

    detail = client.get("/api/v1/journal-entries/" + entry["id"])
    assert detail.status_code == 200 and detail.json() == entry

    img = client.get(entry["image_url"])
    assert img.status_code == 200 and "immutable" in img.headers["cache-control"]
    thumb = client.get(entry["thumbnail_url"])
    assert thumb.status_code == 200

    assert client.delete("/api/v1/journal-entries/" + entry["id"]).status_code == 204
    assert client.get("/api/v1/journal-entries/" + entry["id"]).json()["error"]["code"] \
        == "entry_not_found"
    assert client.delete("/api/v1/journal-entries/" + entry["id"]).status_code == 404
    assert client.get("/api/v1/journal-entries").json() == {"entries": [], "total": 0}
    # No orphan rows or files.
    conn = sqlite3.connect(os.environ["DATABASE_PATH"])
    leftovers = conn.execute("SELECT COUNT(*) FROM journal_entries").fetchone()[0]
    conn.close()
    assert leftovers == 0
    assert os.listdir(os.environ["UPLOAD_DIR"]) == ["tmp"]
    assert os.listdir(os.path.join(os.environ["UPLOAD_DIR"], "tmp")) == []


def test_save_without_ai_after_outage(app_client):
    client, app = app_client
    app.state.ai_service = StubAI("down")
    res = client.post("/api/v1/observations/analyze",
                      files={"image": ("leaf.jpg", make_image("JPEG"), "image/jpeg")})
    assert res.json()["error"]["code"] == "ai_unavailable"
    temp_id = res.json()["error"]["details"]["temp_image_id"]
    save = client.post("/api/v1/journal-entries", json={
        "temp_image_id": temp_id, "ai_analysis": None,
        "user_notes": "No AI today; watched ants instead.", "experiment_done": False})
    assert save.status_code == 201, save.text
    assert save.json()["analysis"] is None


def test_save_validation_codes(app_client):
    client, app = app_client
    app.state.ai_service = StubAI("ok")
    analyzed = client.post(
        "/api/v1/observations/analyze",
        files={"image": ("leaf.jpg", make_image("JPEG"), "image/jpeg")}).json()

    base = {"temp_image_id": analyzed["temp_image_id"], "ai_analysis": analyzed["analysis"],
            "user_notes": "Saw veins.", "experiment_done": False}
    assert client.post("/api/v1/journal-entries",
                       json=dict(base, user_notes="  ")).json()["error"]["code"] \
        == "notes_required"
    bad_model = dict(analyzed["analysis"], model_id="something-else")
    assert client.post("/api/v1/journal-entries",
                       json=dict(base, ai_analysis=bad_model)).json()["error"]["code"] \
        == "ai_model_mismatch"
    assert client.post("/api/v1/journal-entries",
                       json=dict(base, temp_image_id="tmp_gone123")).json()["error"]["code"] \
        == "temp_image_expired"
    assert client.post("/api/v1/journal-entries",
                       json=dict(base, experiment_done="yes")).status_code == 400
    assert client.post("/api/v1/journal-entries", content=b"nope",
                       headers={"Content-Type": "application/json"}).status_code == 400


def test_sweep_removes_expired_only(app_client):
    client, app = app_client
    settings = app.state.settings
    # Stale row + stale orphan file.
    conn = sqlite3.connect(settings.database_path)
    conn.execute("INSERT INTO ai_analyses (id, model_id, analyzed_at, analysis_json,"
                 " image_tmp_path, saved) VALUES (?, ?, ?, ?, ?, 0)",
                 ("tmp_old1", "m", "2020-01-01T00:00:00Z", "{}",
                  os.path.join("tmp", "tmp_old1.jpg")))
    conn.commit()
    conn.close()
    tmp_dir = os.path.join(settings.upload_dir, "tmp")
    os.makedirs(tmp_dir, exist_ok=True)
    with open(os.path.join(tmp_dir, "tmp_old1.jpg"), "wb") as fh:
        fh.write(make_image("JPEG"))
    with open(os.path.join(tmp_dir, "tmp_orphan.jpg"), "wb") as fh:
        fh.write(make_image("JPEG"))
    old = 1000000000.0  # year 2001: older than the 1-hour TTL for sure
    os.utime(os.path.join(tmp_dir, "tmp_old1.jpg"), (old, old))
    os.utime(os.path.join(tmp_dir, "tmp_orphan.jpg"), (old, old))

    # Fresh analyze keeps working and triggers the sweep.
    app.state.ai_service = StubAI("ok")
    res = client.post("/api/v1/observations/analyze",
                      files={"image": ("leaf.jpg", make_image("JPEG"), "image/jpeg")})
    assert res.status_code == 200
    fresh_tmp = res.json()["temp_image_id"] + ".jpg"
    remaining = sorted(os.listdir(tmp_dir))
    assert "tmp_old1.jpg" not in remaining and "tmp_orphan.jpg" not in remaining
    assert fresh_tmp in remaining
    conn = sqlite3.connect(settings.database_path)
    rows = conn.execute("SELECT COUNT(*) FROM ai_analyses WHERE id = 'tmp_old1'").fetchone()[0]
    conn.close()
    assert rows == 0
    # Second sweep is a no-op once everything expired is gone.
    assert journal_service.sweep_temp(settings.upload_dir,
                                      settings.database_path) == {"rows": 0, "files": 0}
