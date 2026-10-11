"""Performance-path tests: transmit caps, provider bounds, timing logs, bench math.

All provider I/O is stubbed or faked. No network, no keys, no billing.
"""

import io
import json
import sys
import types as pytypes

from PIL import Image

from app.config import Settings
from app.services import ai_service
from app.services import images
from bench.bench_providers import summarize
from tests.conftest import StubAI, VALID_ANALYSIS, make_image


def open_size(data):
    with Image.open(io.BytesIO(data)) as img:
        img.load()
        return img.size, img.format


def test_transmit_passthrough_for_suitable_jpeg():
    src = make_image("JPEG", size=(800, 600))
    out, mime = images.prepare_transmit(src, "image/jpeg")
    assert out == src and mime == "image/jpeg"  # byte-identical, no rewrite


def test_transmit_caps_edge_and_preserves_aspect():
    src = make_image("JPEG", size=(3000, 1500))
    out, mime = images.prepare_transmit(src, "image/jpeg", max_edge=1000, quality=82)
    (w, h), fmt = open_size(out)
    assert max(w, h) == 1000 and mime == "image/jpeg" and fmt == "JPEG"
    assert abs(w / h - 2.0) < 0.02
    assert len(out) < len(src)


def test_transmit_converts_png_and_rgba_to_jpeg():
    out, mime = images.prepare_transmit(make_image("PNG", size=(900, 900)), "image/png")
    assert mime == "image/jpeg" and open_size(out)[1] == "JPEG"


def test_perf_defaults(monkeypatch):
    for var in ("TRANSMIT_MAX_EDGE", "TRANSMIT_JPEG_QUALITY", "GEMINI_MAX_OUTPUT_TOKENS",
                "OLLAMA_NUM_CTX", "OLLAMA_NUM_PREDICT", "OLLAMA_KEEP_ALIVE",
                "AI_PROVIDER", "OLLAMA_HOST", "OLLAMA_MODEL",
                "OLLAMA_NUM_THREAD"):
        monkeypatch.delenv(var, raising=False)
    s = Settings()
    assert (s.transmit_max_edge, s.transmit_jpeg_quality) == (2048, 82)
    assert s.gemini_max_output_tokens == 1024
    assert (s.ollama_num_ctx, s.ollama_num_predict, s.ollama_keep_alive) == (4096, 1024, "5m")
    assert (s.ai_provider, s.ollama_host, s.ollama_model) == (
        "gemini", "http://localhost:11434", "gemma4:e2b")
    assert s.ollama_num_thread == 0


def test_gemini_forwards_output_cap(monkeypatch):
    seen = {}

    class FakeCfg:
        def __init__(self, **kw):
            seen.update(kw)

    class FakeModels:
        def generate_content(self, **kw):
            seen["model"] = kw["model"]

            class R:
                text = json.dumps(VALID_ANALYSIS)
            return R()

    class FakeClient:
        def __init__(self, **kw):
            seen["client"] = True

        @property
        def models(self):
            return FakeModels()

    fake_types = pytypes.SimpleNamespace(
        Part=pytypes.SimpleNamespace(from_bytes=staticmethod(lambda **k: object())),
        GenerateContentConfig=FakeCfg)
    fake_genai = pytypes.SimpleNamespace(Client=FakeClient, types=fake_types)
    monkeypatch.setitem(sys.modules, "google.genai", fake_genai)
    monkeypatch.setitem(sys.modules, "google.genai.types", fake_types)
    out = ai_service.GeminiAdapter(model_id="m", api_key="k", max_output_tokens=512).analyze(
        b"img", "image/jpeg", None)
    assert seen["model"] == "m" and seen["response_mime_type"] == "application/json"
    assert seen["max_output_tokens"] == 512
    assert out["model_id"] == "m"


def test_ollama_sends_generation_bounds(monkeypatch):
    seen = {}

    class FakeResp:
        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def read(self):
            return json.dumps({"message": {"content": json.dumps(VALID_ANALYSIS)}}).encode()

    def capture(req):
        seen.update(json.loads(req.data.decode("utf-8")))
        return FakeResp()

    monkeypatch.setattr("urllib.request.urlopen", capture)
    ai_service.OllamaAdapter(model_id="m", host="http://h:1", num_ctx=2048,
                             num_predict=256, keep_alive="2m").analyze(
        b"img", "image/jpeg", None)
    assert seen["options"] == {"num_ctx": 2048, "num_predict": 256}
    assert seen["keep_alive"] == "2m"
    assert seen["format"] == "json"


def test_analyze_logs_timing_fields(app_client, capsys):
    client, app = app_client
    app.state.ai_service = StubAI("ok")
    res = client.post("/api/v1/observations/analyze",
                      files={"image": ("leaf.jpg", make_image("JPEG"), "image/jpeg")})
    assert res.status_code == 200
    line = capsys.readouterr().out
    for token in ("verdantra analyze", "model=gemma-4-26b-a4b-it", "pre_ms=",
                  "provider_ms=", "total_ms=", "img_bytes=", "tx_bytes=",
                  "outcome=ok"):
        assert token in line, token
    app.state.ai_service = StubAI("down")
    res = client.post("/api/v1/observations/analyze",
                      files={"image": ("leaf.jpg", make_image("JPEG"), "image/jpeg")})
    assert res.status_code == 503
    assert "outcome=ai_unavailable" in capsys.readouterr().out


def test_bench_summarize_splits_cold_warm_and_failures():
    # Synthetic timings only — arithmetic check, no model involved.
    recs = [{"ok": True, "cold": True, "pre_ms": 100, "provider_ms": 900, "total_ms": 1000}]
    recs += [{"ok": True, "cold": False, "pre_ms": 100, "provider_ms": p, "total_ms": p + 100}
             for p in (800, 900, 1000, 1100)]
    recs.append({"ok": False, "cold": False, "pre_ms": 0, "provider_ms": 0, "total_ms": 5})
    s = summarize(recs)
    assert (s["runs"], s["ok"], s["failed"], s["warm_n"]) == (6, 5, 1, 4)
    assert s["cold_total_ms"] == 1000
    assert s["warm"]["total_ms"]["mean"] == 1050.0
    assert s["warm"]["total_ms"]["p50"] == 1050.0


def test_build_wires_thread_lever():
    adapter = ai_service.build_service("m", "k", 120, provider="ollama",
                                       ollama_num_thread=4)
    assert isinstance(adapter, ai_service.OllamaAdapter)
    assert adapter._options.get("num_thread") == 4
    defaulted = ai_service.build_service("m", "k", 120, provider="ollama")
    assert "num_thread" not in defaulted._options  # server default kept


def test_busy_slot_rejects_second_analysis(app_client):
    from app.routes import observations

    client, _app = app_client
    assert observations._AI_SLOT.acquire(blocking=False)
    try:
        res = client.post("/api/v1/observations/analyze",
                          files={"image": ("leaf.jpg", make_image("JPEG"), "image/jpeg")})
    finally:
        observations._AI_SLOT.release()
    assert res.status_code == 503
    body = res.json()
    assert body["error"]["code"] == "ai_busy"
    assert body["request_id"] and res.headers["X-Request-Id"] == body["request_id"]
    # Slot released: next request proceeds normally.
    res = client.post("/api/v1/observations/analyze",
                      files={"image": ("leaf.jpg", make_image("JPEG"), "image/jpeg")})
    assert res.status_code == 200
