"""Shared fixtures: isolated env/tmp dirs, sample images, stub AI. No network."""

import io
import os
import sys

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.main import create_app  # noqa: E402
from app.config import Settings  # noqa: E402


VALID_ANALYSIS = {
    "observed_features": ["oval green leaves with smooth edges", "visible central vein"],
    "cautious_explanation": "The leaves appear broad and smooth-edged, which may be consistent "
                            "with many common garden plants. This photo alone cannot confirm more.",
    "uncertainty": ["Species cannot be determined from this photo"],
    "experiment": {
        "title": "Sun vs shade leaf check",
        "steps": ["Find two similar leaves", "Look closely for 2 minutes each",
                  "Write what surprised you"],
        "materials": ["paper", "pencil"],
        "safety_notes": ["Stay on paths", "Do not pick, touch, or taste plants"],
        "estimated_minutes": 10,
    },
    "model_id": "gemma-4-26b-a4b-it",
    "disclaimer": "AI prediction based only on this photo. May be wrong. "
                  "Your own observation is the record that counts.",
}


class StubAI:
    model_id = "gemma-4-26b-a4b-it"

    def __init__(self, behavior="ok", ping_result=True):
        self.behavior = behavior
        self._ping_result = ping_result
        self.calls = []

    def ping(self):
        return self._ping_result

    def analyze(self, image_bytes, mime, hint):
        from app.services import ai_service
        self.calls.append((mime, hint))
        if self.behavior == "ok":
            return dict(VALID_ANALYSIS)
        raise {"timeout": ai_service.AITimeout("slow"),
               "auth": ai_service.AIAuthError("bad key"),
               "quota": ai_service.AIQuotaError("limited"),
               "bad": ai_service.AIBadResponse("broken"),
               "down": ai_service.AIError("gone")}[self.behavior]


@pytest.fixture()
def settings(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "t.db"))
    monkeypatch.setenv("UPLOAD_DIR", str(tmp_path / "up"))
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    return Settings()


@pytest.fixture()
def app_client(settings):
    app = create_app(settings)
    with TestClient(app) as client:
        # Lifespan (above) installs the real adapter; swap the stub after
        # startup so routes see it per request.
        app.state.ai_service = StubAI("ok")
        yield client, app


def make_image(fmt="JPEG", size=(800, 600), exif=False):
    from PIL import Image
    img = Image.new("RGB", size, (34, 139, 34))
    buf = io.BytesIO()
    if exif:
        ex = Image.Exif()
        ex[271] = "TEST-CAMERA"
        img.save(buf, format=fmt, exif=ex)
    elif fmt == "JPEG":
        img.save(buf, format=fmt, quality=85)
    elif fmt == "PNG":
        img.save(buf, format=fmt, optimize=True)
    else:
        img.save(buf, format=fmt, quality=85)
    return buf.getvalue()
