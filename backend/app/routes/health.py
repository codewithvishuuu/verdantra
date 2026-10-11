"""Health endpoint (API.md section 1). Honest db/ai reachability, never fake ok."""

import time

from fastapi import APIRouter, Depends, Request

from app import schemas
from app.config import APP_VERSION, Settings
from app.db import check_db
from app.errors import ApiError, request_id_of
from app.services import ai_service

router = APIRouter()


def get_settings(request: Request) -> Settings:
    return request.app.state.settings


def get_ai(request: Request) -> ai_service.AIService:
    return request.app.state.ai_service


@router.get("/healthz", response_model=schemas.HealthResponse)
def healthz(request: Request, settings: Settings = Depends(get_settings),
            ai: ai_service.AIService = Depends(get_ai)) -> dict:
    db_ok = check_db(settings.database_path)
    if not db_ok:
        raise ApiError(503, "db_unavailable",
                       "The journal store is unavailable right now. Please retry.", {})
    ai_ok = False
    try:
        ai_ok = bool(ai.ping())
    except Exception:
        ai_ok = False
    uptime = int(time.monotonic() - request.app.state.started_at)
    return {
        "status": "ok" if ai_ok else "degraded",
        "version": APP_VERSION,
        "db": "ok",
        "ai": "ok" if ai_ok else "unavailable",
        "model_id": ai.model_id,
        "uptime_s": uptime,
        "provider": settings.ai_provider,
    }
