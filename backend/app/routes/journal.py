"""Journal routes (API.md section 3, M3). Validation codes follow the contract."""

import os
import re

from fastapi import APIRouter, Depends, Request
from fastapi.responses import FileResponse, JSONResponse

from app import schemas
from app.config import Settings
from app.errors import ApiError, request_id_of
from app.services import journal

router = APIRouter()

MEDIA_RE = re.compile(r"^(original|thumb_512)\.(jpg|png|webp)$")
MIME_BY_EXT = {"jpg": "image/jpeg", "png": "image/png", "webp": "image/webp"}


def get_settings(request: Request) -> Settings:
    return request.app.state.settings


def get_model_id(request: Request) -> str:
    return request.app.state.ai_service.model_id


@router.post("/api/v1/journal-entries", status_code=201)
async def save_entry(request: Request, settings: Settings = Depends(get_settings),
                     model_id: str = Depends(get_model_id)) -> dict:
    try:
        payload = await request.json()
    except Exception:
        raise ApiError(400, "bad_request",
                       "That request was malformed. Check your input and retry.", {})
    if not isinstance(payload, dict):
        raise ApiError(400, "bad_request",
                       "That request was malformed. Check your input and retry.", {})
    return journal.create_entry(settings, model_id, payload)


@router.get("/api/v1/journal-entries", response_model=schemas.JournalListResponse)
def list_entries(request: Request,
                 settings: Settings = Depends(get_settings)) -> dict:
    return journal.list_entries(settings)


@router.get("/api/v1/journal-entries/{entry_id}")
def entry_detail(entry_id: str, request: Request,
                 settings: Settings = Depends(get_settings)) -> dict:
    return journal.get_entry(settings, entry_id)


@router.delete("/api/v1/journal-entries/{entry_id}", status_code=204)
def delete_entry(entry_id: str, request: Request,
                 settings: Settings = Depends(get_settings)) -> JSONResponse:
    journal.delete_entry(settings, entry_id)
    return JSONResponse(status_code=204, content=None,
                        headers={"X-Request-Id": request_id_of(request)})


@router.get("/media/{entry_id}/{filename}")
def media_entry(entry_id: str, filename: str, request: Request,
                settings: Settings = Depends(get_settings)) -> FileResponse:
    if journal.ID_RE.match(entry_id) is None or entry_id == "tmp" \
            or entry_id.startswith("tmp_"):
        raise ApiError(400, "invalid_path", "That media path is invalid.", {})
    match = MEDIA_RE.match(filename)
    if match is None:
        raise ApiError(400, "invalid_path", "That media path is invalid.", {})
    _stem, ext = match.group(1), match.group(2)
    path = os.path.join(settings.upload_dir, entry_id, filename)
    if not os.path.isfile(path):
        raise ApiError(404, "entry_not_found", "That image no longer exists.", {})
    return FileResponse(path, media_type=MIME_BY_EXT[ext],
                        headers={"Cache-Control": "public, max-age=31536000, immutable"})
