"""Klave Engine API. Routes orchestrate; the domain packages do the thinking."""

import traceback
from datetime import UTC, datetime
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from klave_engine.common.bitacora import ErrorRegistrado, anotar_error, redactar
from klave_engine.common.config import get_settings
from klave_engine.common.errors import KlaveEngineError
from klave_engine.common.logging import configure_logging, get_logger, request_id_var

from apps.api.auth.account import router as account_router
from apps.api.auth.invitations import router as invitations_router
from apps.api.auth.middleware import AccessControlMiddleware, allowed_origins
from apps.api.auth.recovery import router as recovery_router
from apps.api.auth.routes import router as auth_router
from apps.api.observability import RequestIdMiddleware
from apps.api.routes import ai as ai_routes
from apps.api.routes import (
    catalog,
    copilot,
    detections,
    entities,
    events,
    exports,
    geometry,
    graph,
    health,
    disciplinas,
    lectura,
    tablero,
    obra,
    projects,
    reports,
    reviews,
    workspace,
)
from apps.api.routes import croquis as croquis_routes
from apps.api.routes import versions as version_routes

# The repo-root .env is THE config file: pydantic-settings reads its KLAVE_*
# entries itself, but provider keys (GEMINI_API_KEY, ANTHROPIC_API_KEY) are
# read from os.environ at request time, so load it there too. Real env vars
# win over the file; a missing file is fine (Docker passes env directly).
load_dotenv(Path(__file__).resolve().parents[2] / ".env")


def _validate_production_config(settings) -> None:
    """KLAVE_ENV=production refuses to boot half-configured: better one clear
    message at start than a quiet cross-origin hole or a cookie over http."""
    problems: list[str] = []
    if settings.web_origin.startswith("http://") and "localhost" in settings.web_origin:
        problems.append("KLAVE_WEB_ORIGIN sigue apuntando a localhost")
    if not settings.web_origin.startswith("https://") and settings.cookie_secure is not True:
        problems.append(
            "KLAVE_WEB_ORIGIN no es https y KLAVE_COOKIE_SECURE no está forzado a true"
        )
    if "127.0.0.1" in settings.users_database_url and "klave@" in settings.users_database_url:
        problems.append("KLAVE_USERS_DATABASE_URL usa las credenciales locales de desarrollo")
    if problems:
        raise RuntimeError(
            "Configuración de producción incompleta: " + "; ".join(problems)
        )


logger = get_logger("klave.error")


def create_app() -> FastAPI:
    settings = get_settings()
    configure_logging(settings.log_level)
    app = FastAPI(title="Klave Engine", version="0.2.0")

    # Session-based access control. Added before CORS so CORS wraps it and
    # 401/403 responses still carry CORS headers the browser can read.
    app.add_middleware(AccessControlMiddleware)
    # Outermost: every log line of a request carries its id, every response
    # echoes it, every request logs its duration.
    app.add_middleware(RequestIdMiddleware)

    # Local-first single workspace: allow the Next.js dev server. Credentials
    # are required so the HttpOnly session cookie travels with fetch and SSE.
    dev = settings.env != "production"
    app.add_middleware(
        CORSMiddleware,
        allow_origins=(
            ["http://localhost:3000", "http://127.0.0.1:3000", *allowed_origins()]
            if dev
            else allowed_origins()
        ),
        # Any localhost port is a developer's browser — never in production.
        allow_origin_regex=r"http://(localhost|127\.0\.0\.1):\d+" if dev else None,
        allow_methods=["*"],
        allow_headers=["*"],
        allow_credentials=True,
        # Downloads go through fetch so a failed export is an error in the
        # page, not a JSON page; the browser needs the filename exposed.
        expose_headers=["Content-Disposition"],
    )
    if not dev:
        _validate_production_config(settings)

    @app.on_event("startup")
    def _repair_interrupted_jobs() -> None:
        # A crash mid-processing must not leave "Procesando…" forever.
        from apps.api.dependencies import ProjectStore
        from apps.api.jobs import JOB_STORE

        try:
            JOB_STORE.repair_orphans(ProjectStore(settings).roots(), settings)
        except Exception:  # noqa: BLE001 — repair is best-effort at boot
            pass

    app.include_router(health.router)
    app.include_router(auth_router)
    app.include_router(invitations_router)
    app.include_router(recovery_router)
    app.include_router(account_router)
    app.include_router(events.router)
    app.include_router(projects.router)
    app.include_router(entities.router)
    app.include_router(geometry.router)
    app.include_router(ai_routes.router)
    app.include_router(obra.router)
    app.include_router(obra.medidas)
    app.include_router(graph.router)
    app.include_router(detections.router)
    app.include_router(reports.router)
    app.include_router(lectura.router)
    app.include_router(tablero.router)
    app.include_router(disciplinas.router)
    app.include_router(exports.router)
    app.include_router(reviews.router)
    app.include_router(version_routes.router)
    app.include_router(croquis_routes.router)
    app.include_router(catalog.router)
    app.include_router(workspace.router)
    app.include_router(copilot.router)

    @app.exception_handler(KlaveEngineError)
    async def klave_error_handler(request: Request, exc: KlaveEngineError) -> JSONResponse:
        return JSONResponse(
            status_code=400,
            content={"error_type": type(exc).__name__, "message": str(exc)},
        )

    @app.exception_handler(Exception)
    async def registrar_lo_que_se_rompio(request: Request, exc: Exception) -> JSONResponse:
        """Lo que nadie previó queda anotado antes de contestar.

        Sin esto, un DWG que tumba al parser a las once de la noche se sabe
        cuando el taller escribe un correo — si lo escribe. La traza se queda
        en la máquina del taller: sus planos son de sus clientes."""
        anotar_error(
            settings.data_dir,
            ErrorRegistrado(
                ts=datetime.now(UTC).isoformat(),
                request_id=request_id_var.get() or "",
                ruta=request.url.path,
                metodo=request.method,
                tipo=type(exc).__name__,
                mensaje=redactar(str(exc)),
                traza=redactar("".join(traceback.format_tb(exc.__traceback__)[-4:]), 2400),
                workspace=str(
                    (getattr(request.state, "user", None) or {}).get("workspace_id") or ""
                ),
            ),
        )
        logger.exception("sin manejar en %s %s", request.method, request.url.path)
        return JSONResponse(
            status_code=500,
            content={
                "error_type": "error_interno",
                "message": (
                    "Algo se rompió de nuestro lado y quedó registrado. Si se repite, "
                    "pásale a tu administrador el identificador de esta petición."
                ),
                "request_id": request_id_var.get() or "",
            },
        )

    return app


app = create_app()
