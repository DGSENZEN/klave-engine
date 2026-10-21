from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from klave_engine import __version__
from klave_engine.common.config import Settings, get_settings

from apps.api.readiness import check_readiness

router = APIRouter()


@router.get("/health")
def health() -> dict:
    return {"status": "ok", "version": __version__}


@router.get("/ready")
def ready(settings: Settings = Depends(get_settings)) -> JSONResponse:
    result = check_readiness(settings)
    return JSONResponse(result, status_code=200 if result["status"] == "ready" else 503)
