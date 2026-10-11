"""Verdantra FastAPI application factory (ARCHITECTURE.md sections 1-3).

Single worker (`--workers 1`), env-only config, request-ID on every
response, envelope errors only. Routes never touch the model SDK:
all provider calls live behind AIService (ARCHITECTURE.md dependency rule).
"""

import os
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.config import Settings
from app.db import init_schema
from app.errors import (ApiError, RequestIdMiddleware, api_error_handler,
                        not_found_handler, request_id_of, unhandled_handler)
from app.routes import health, journal, observations
from app.services import ai_service
from app.services import journal as journal_service


def build_ai(settings: Settings) -> ai_service.AIService:
    return ai_service.build_service(
        model_id=settings.ai_model_id,
        api_key=settings.gemini_api_key,
        timeout_s=settings.ai_timeout_s,
        provider=settings.ai_provider,
        ollama_host=settings.ollama_host,
        ollama_model=settings.ollama_model,
        max_output_tokens=settings.gemini_max_output_tokens,
        ollama_num_ctx=settings.ollama_num_ctx,
        ollama_num_predict=settings.ollama_num_predict,
        ollama_keep_alive=settings.ollama_keep_alive,
        ollama_num_thread=settings.ollama_num_thread,
        auto_primary_timeout_s=settings.auto_primary_timeout_s)


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        os.makedirs(os.path.join(settings.upload_dir, "tmp"), exist_ok=True)
        try:
            init_schema(settings.database_path)
        except Exception:
            # Stay up so /healthz can report db_unavailable honestly (API.md).
            # No paths or tracebacks leave this process.
            print("verdantra: db init failed; serving degraded", flush=True)
        try:
            journal_service.sweep_temp(settings.upload_dir, settings.database_path)
        except Exception:
            pass  # sweep never breaks startup (DATABASE.md section 4)
        app.state.settings = settings
        app.state.ai_service = build_ai(settings)
        app.state.started_at = time.monotonic()
        yield

    app = FastAPI(title="Verdantra", version="0.2.0", lifespan=lifespan,
                  docs_url=None, redoc_url=None, openapi_url=None)
    app.add_middleware(RequestIdMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,  # exact origins only, never "*"
        allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
        allow_headers=["Content-Type", "X-Request-Id", "Accept"],
        allow_credentials=False,
        max_age=600,
    )
    app.add_exception_handler(ApiError, api_error_handler)
    app.add_exception_handler(StarletteHTTPException, not_found_handler)
    app.add_exception_handler(Exception, unhandled_handler)

    @app.exception_handler(RequestValidationError)
    async def validation_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
        body = {"error": {"code": "bad_request",
                          "message": "That request was malformed. Check your input and retry.",
                          "details": {}},
                "request_id": request_id_of(request)}
        return JSONResponse(status_code=400, content=body,
                            headers={"X-Request-Id": request_id_of(request)})

    app.include_router(health.router)
    app.include_router(observations.router)
    app.include_router(journal.router)
    return app


app = create_app()
