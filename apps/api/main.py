"""Klave Engine API. Routes orchestrate; the domain packages do the thinking."""

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from klave_engine.common.config import get_settings
from klave_engine.common.errors import KlaveEngineError
from klave_engine.common.logging import configure_logging

from apps.api.auth.account import router as account_router
from apps.api.auth.invitations import router as invitations_router
from apps.api.auth.middleware import AccessControlMiddleware
from apps.api.auth.recovery import router as recovery_router
from apps.api.auth.routes import router as auth_router
from apps.api.routes import (
    catalog,
    detections,
    entities,
    events,
    exports,
    geometry,
    graph,
    health,
    lectura,
    projects,
    reports,
    reviews,
)


def create_app() -> FastAPI:
    settings = get_settings()
    configure_logging(settings.log_level)
    app = FastAPI(title="Klave Engine", version="0.2.0")

    # Session-based access control. Added before CORS so CORS wraps it and
    # 401/403 responses still carry CORS headers the browser can read.
    app.add_middleware(AccessControlMiddleware)

    # Local-first single workspace: allow the Next.js dev server. Credentials
    # are required so the HttpOnly session cookie travels with fetch and SSE.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            "http://localhost:3000",
            "http://127.0.0.1:3000",
        ],
        allow_origin_regex=r"http://localhost:\d+",
        allow_methods=["*"],
        allow_headers=["*"],
        allow_credentials=True,
    )

    app.include_router(health.router)
    app.include_router(auth_router)
    app.include_router(invitations_router)
    app.include_router(recovery_router)
    app.include_router(account_router)
    app.include_router(events.router)
    app.include_router(projects.router)
    app.include_router(entities.router)
    app.include_router(geometry.router)
    app.include_router(graph.router)
    app.include_router(detections.router)
    app.include_router(reports.router)
    app.include_router(lectura.router)
    app.include_router(exports.router)
    app.include_router(reviews.router)
    app.include_router(catalog.router)

    @app.exception_handler(KlaveEngineError)
    async def klave_error_handler(request: Request, exc: KlaveEngineError) -> JSONResponse:
        return JSONResponse(
            status_code=400,
            content={"error_type": type(exc).__name__, "message": str(exc)},
        )

    return app


app = create_app()
