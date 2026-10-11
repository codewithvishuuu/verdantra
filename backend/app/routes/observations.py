"""Analyze endpoint + tmp media (API.md sections 2 and 4, M1 scope).

POST /api/v1/observations/analyze validates (order: presence, type,
size, decodability, hint), sanitizes (EXIF-strip + re-encode), stores the
sanitized bytes under a server-generated id, calls AIService once, and
returns the validated analysis unpersisted. Nothing here invents results:
every failure is an envelope, never a fabricated analysis.
"""

import json
import os
import re
import secrets
import threading
import time
from functools import wraps

from fastapi import APIRouter, Depends, File, Form, Request, UploadFile
from fastapi.responses import FileResponse

from app import schemas
from app.config import Settings
from app.db import connect
from app.errors import ApiError, request_id_of
from app.services import ai_service
from app.services import images
from app.services import journal as journal_service

router = APIRouter()

TEMP_ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
MEDIA_RE = re.compile(r"^([A-Za-z0-9_-]{1,64})\.(jpg|png|webp)$")
MIME_BY_EXT = {"jpg": "image/jpeg", "png": "image/png", "webp": "image/webp"}


def get_settings(request: Request) -> Settings:
    return request.app.state.settings


def get_ai(request: Request) -> ai_service.AIService:
    return request.app.state.ai_service


def new_temp_id() -> str:
    return "tmp_" + secrets.token_hex(13)


# Single inference slot (single-worker assumption, matching --workers 1).
# Overlapping full-model inferences would exhaust an 8 GB host, so a second
# concurrent analyze fails fast with 503 ai_busy instead of queueing behind
# a minutes-long CPU-bound call. Fast routes (health, journal) are unaffected.
_AI_SLOT = threading.Lock()


def exclusive_ai_slot(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        if not _AI_SLOT.acquire(blocking=False):
            raise ApiError(503, "ai_busy",
                           "The AI helper is busy with another request right now. "
                           "Please wait a moment and retry.", {})
        try:
            return func(*args, **kwargs)
        finally:
            _AI_SLOT.release()
    return wrapper


def clean_hint(raw: str | None) -> str:
    if not raw:
        return ""
    text = "".join(ch for ch in raw if ch == "\n" or ch == "\t" or ord(ch) >= 32)
    return text.strip()


def tmp_path(settings: Settings, temp_id: str, ext: str) -> str:
    return os.path.join(settings.upload_dir, "tmp", temp_id + "." + ext)


@router.post("/api/v1/observations/analyze", response_model=schemas.AnalyzeResponse)
@exclusive_ai_slot
def analyze(request: Request,
            settings: Settings = Depends(get_settings),
            ai: ai_service.AIService = Depends(get_ai),
            image: UploadFile | None = File(default=None),
            notes_hint: str | None = Form(default=None)) -> dict:
    # Opportunistic temp sweep (DATABASE.md section 4); never breaks analysis.
    try:
        journal_service.sweep_temp(settings.upload_dir, settings.database_path)
    except Exception:
        pass
    t_arrive = time.perf_counter()  # latency instrumentation starts here
    if image is None or not image.filename:
        raise ApiError(400, "no_image",
                       "Please choose a photo first.", {})
    # Streamed read with a hard cap (never buffer unbounded input).
    limit = settings.max_image_bytes + 1024 * 1024
    chunks: list[bytes] = []
    received = 0
    while True:
        piece = image.file.read(65536)
        if not piece:
            break
        received += len(piece)
        if received > limit:
            raise ApiError(413, "too_large",
                           "That photo is over %d MB. Choose a smaller one."
                           % settings.max_image_mb, {})
        chunks.append(piece)
    data = b"".join(chunks)

    mime = images.sniff_mime(data[:12])
    if mime is None or mime not in images.ALLOWED:
        raise ApiError(400, "invalid_image",
                       "Please choose a JPEG, PNG, or WebP photo.", {})
    if len(data) > settings.max_image_bytes:
        raise ApiError(413, "too_large",
                       "That photo is over %d MB. Choose a smaller one."
                       % settings.max_image_mb, {})
    # Decodability + dimensions (raises 422 unusable_image).
    images.validate_bytes(data, settings.max_image_bytes)

    hint = clean_hint(notes_hint)
    if notes_hint is not None and len(notes_hint) > 280:
        raise ApiError(400, "hint_too_long",
                       "Context must be 280 characters or fewer.", {})

    full_bytes, _thumb = images.sanitize(data, mime)
    # Smaller provider payload; stored files above are unaffected.
    tx_bytes, tx_mime = images.prepare_transmit(
        full_bytes, mime, settings.transmit_max_edge, settings.transmit_jpeg_quality)
    pre_ms = int((time.perf_counter() - t_arrive) * 1000)
    temp_id = new_temp_id()
    ext = images.ext_for(mime)
    if not TEMP_ID_RE.match(temp_id):
        raise ApiError(500, "internal_error",
                       "Something went wrong. Please retry.", {})
    dest = tmp_path(settings, temp_id, ext)
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    with open(dest, "wb") as fh:
        fh.write(full_bytes)

    base_details = {"model_id": ai.model_id, "temp_image_id": temp_id}
    outcome = "ok"
    t_ai_start = time.perf_counter()
    t_ai_ms = 0
    try:
        analysis = ai.analyze(tx_bytes, tx_mime, hint or None)
    except ai_service.AITimeout as exc:
        outcome = "ai_timeout"
        raise ApiError(504, "ai_timeout",
                       "The AI helper took too long. Your photo is kept — retry or save your own observation.",
                       dict(base_details)) from exc
    except ai_service.AIAuthError as exc:
        outcome = "api_auth_error"
        raise ApiError(503, "api_auth_error",
                       "The AI helper isn't working right now. Your photo is kept — retry or save your own observation.",
                       dict(base_details)) from exc
    except ai_service.AIQuotaError as exc:
        outcome = "api_quota_exhausted"
        raise ApiError(503, "api_quota_exhausted",
                       "The AI helper is rate-limited right now. Your photo is kept — retry later or save your own observation.",
                       dict(base_details)) from exc
    except ai_service.AIBadResponse as exc:
        outcome = "ai_bad_response"
        raise ApiError(502, "ai_bad_response",
                       "The AI helper returned an unusable answer. Your photo is kept — retry or save your own observation.",
                       dict(base_details)) from exc
    except ai_service.AIError as exc:
        outcome = "ai_unavailable"
        raise ApiError(503, "ai_unavailable",
                       "The AI helper is unavailable right now. Your photo is kept — retry or save your own observation.",
                       dict(base_details)) from exc
    finally:
        # Lengths and codes only — never keys, prompts, bytes, or paths.
        t_ai_ms = int((time.perf_counter() - t_ai_start) * 1000)
        total_ms = int((time.perf_counter() - t_arrive) * 1000)
        print("verdantra analyze model=%s pre_ms=%d provider_ms=%d total_ms=%d "
              "img_bytes=%d tx_bytes=%d outcome=%s"
              % (ai.model_id, pre_ms, t_ai_ms, total_ms,
                 len(data), len(tx_bytes), outcome), flush=True)

    # Record the successful (still unsaved) analysis for later promotion (M3)
    # and for the temp sweep. Failures here must not mask a good analysis.
    try:
        conn = connect(settings.database_path)
        try:
            conn.execute(
                "INSERT OR IGNORE INTO ai_analyses"
                " (id, model_id, analysis_json, image_tmp_path, saved)"
                " VALUES (?, ?, ?, ?, 0)",
                (temp_id, ai.model_id, json.dumps(analysis),
                 os.path.join("tmp", temp_id + "." + ext)))
            conn.commit()
        finally:
            conn.close()
    except Exception:
        pass

    rel = "tmp/" + temp_id + "." + ext
    return {"temp_image_id": temp_id,
            "image_preview_url": "/media/" + rel,
            "analysis": analysis}


@router.get("/media/tmp/{filename}")
def media_tmp(filename: str, request: Request,
              settings: Settings = Depends(get_settings)) -> FileResponse:
    match = MEDIA_RE.match(filename)
    if match is None:
        raise ApiError(400, "invalid_path", "That media path is invalid.", {})
    _temp_id, ext = match.group(1), match.group(2)
    path = os.path.join(settings.upload_dir, "tmp", filename)
    if not os.path.isfile(path):
        raise ApiError(404, "entry_not_found", "That image no longer exists.", {})
    return FileResponse(path, media_type=MIME_BY_EXT[ext],
                        headers={"Cache-Control": "no-store"})
