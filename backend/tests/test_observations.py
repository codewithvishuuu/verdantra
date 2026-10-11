"""Analyze route: validation order, envelope, provider mapping. AI is stubbed."""

from tests.conftest import StubAI, make_image


def post(client, data=None, files=None):
    return client.post("/api/v1/observations/analyze", data=data or {}, files=files or {})


def test_valid_upload_returns_200_shape_and_serves_preview(app_client):
    client, app = app_client
    body = make_image("JPEG")
    res = post(client, data={"notes_hint": "near the path"},
               files={"image": ("leaf.jpg", body, "image/jpeg")})
    assert res.status_code == 200, res.text
    payload = res.json()
    assert payload["temp_image_id"].startswith("tmp_")
    assert payload["image_preview_url"].startswith("/media/tmp/")
    assert payload["analysis"]["model_id"] == "gemma-4-26b-a4b-it"
    assert "request_id" not in payload  # success body has no envelope
    assert res.headers["X-Request-Id"].startswith("req_")
    preview = client.get(payload["image_preview_url"])
    assert preview.status_code == 200 and preview.headers["content-type"] == "image/jpeg"
    assert len(preview.content) > 0


def test_missing_invalid_small_and_long_hint(app_client):
    client, _app = app_client
    res = post(client)
    assert (res.status_code, res.json()["error"]["code"]) == (400, "no_image")
    res = post(client, files={"image": ("evil.exe", b"MZ\x90evil", "application/x-dosexec")})
    assert (res.status_code, res.json()["error"]["code"]) == (400, "invalid_image")
    res = post(client, files={"image": ("tiny.jpg", make_image("JPEG", (1, 1)), "image/jpeg")})
    assert (res.status_code, res.json()["error"]["code"]) == (422, "unusable_image")
    res = post(client, data={"notes_hint": "x" * 281},
               files={"image": ("leaf.jpg", make_image("JPEG"), "image/jpeg")})
    assert (res.status_code, res.json()["error"]["code"]) == (400, "hint_too_long")


def test_provider_failures_keep_temp_id_and_envelope(app_client):
    client, app = app_client
    cases = [("timeout", 504, "ai_timeout"), ("auth", 503, "api_auth_error"),
             ("quota", 503, "api_quota_exhausted"), ("bad", 502, "ai_bad_response"),
             ("down", 503, "ai_unavailable")]
    for behavior, status, code in cases:
        app.state.ai_service = StubAI(behavior)
        res = post(client, files={"image": ("leaf.jpg", make_image("JPEG"), "image/jpeg")})
        body = res.json()
        assert res.status_code == status, (behavior, res.text)
        assert body["error"]["code"] == code
        assert body["error"]["details"]["temp_image_id"].startswith("tmp_")
        assert body["request_id"] and res.headers["X-Request-Id"] == body["request_id"]
        assert "placeholder" not in res.text  # no credential material anywhere


def test_outage_messages_follow_binding_copy(app_client):
    # API.md section 6 declares message text binding UI copy. The unavailable
    # message must match verbatim; sibling outage codes keep the same
    # photo-kept / save-without-AI pattern with distinct reasons.
    client, app = app_client
    app.state.ai_service = StubAI("down")
    body = post(client,
                files={"image": ("leaf.jpg", make_image("JPEG"), "image/jpeg")}).json()
    assert body["error"]["message"] == (
        "The AI helper is unavailable right now. Your photo is kept \u2014 "
        "retry or save your own observation.")
    for behavior in ("auth", "quota", "timeout", "bad"):
        app.state.ai_service = StubAI(behavior)
        msg = post(client,
                   files={"image": ("leaf.jpg", make_image("JPEG"), "image/jpeg")}
                   ).json()["error"]["message"]
        assert "Your photo is kept" in msg and "save your own observation" in msg


def test_media_guards(app_client):
    client, _app = app_client
    res = client.get("/media/tmp/..%2Fsecret.jpg")
    assert res.status_code in (400, 404)
    res = client.get("/media/tmp/tmp_doesnotexist123.jpg")
    assert res.json()["error"]["code"] == "entry_not_found"
