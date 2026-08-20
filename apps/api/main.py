"""Klave Engine API. Routes orchestrate; the domain packages do the thinking."""

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from klave_engine.common.config import get_settings
from klave_engine.common.errors import KlaveEngineError
from klave_engine.common.logging import configure_logging

from apps.api.routes import (
    catalog,
    detections,
    entities,
    events,
    geometry,
    graph,
    health,
    projects,
    reports,
    reviews,
)


def create_app() -> FastAPI:
    settings = get_settings()
    configure_logging(settings.log_level)
    app = FastAPI(title="Klave Engine", version="0.2.0")

    # Local-first single workspace: allow the Next.js dev server.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            "http://localhost:3000",
            "http://127.0.0.1:3000",
        ],
        allow_origin_regex=r"http://localhost:\d+",
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(health.router)
    app.include_router(events.router)
    app.include_router(projects.router)
    app.include_router(entities.router)
    app.include_router(geometry.router)
    app.include_router(graph.router)
    app.include_router(detections.router)
    app.include_router(reports.router)
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
