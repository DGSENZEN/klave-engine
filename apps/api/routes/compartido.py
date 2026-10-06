"""La liga para compartir: crearla y revocarla (dueño del proyecto) y, del
otro lado, lo que ve quien la abre sin cuenta — plano y generadores, nunca
el dinero."""

from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from fastapi.responses import Response
from klave_engine.common.config import Settings
from klave_engine.common.ids import slugify
from klave_engine.costing.exports import build_generadores_workbook
from klave_engine.costing.models import CostReport
from klave_engine.costing.reviews import load_reviews
from klave_engine.detection.results import Detection
from klave_engine.detection.views import SheetSegmentation
from pydantic import BaseModel, Field

from apps.api.auth.common import rate_limit
from apps.api.dependencies import ProjectStore, get_settings, get_store
from apps.api.events import clean_actor
from apps.api.routes.geometry import get_geometry
from apps.api.share_links import create_link, list_links, resolve, revoke_link

router = APIRouter(prefix="/projects")
public = APIRouter(prefix="/compartido")

XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


class ShareBody(BaseModel):
    days: int = Field(default=14, ge=1, le=90)


@router.post("/{project_id}/compartir", status_code=201)
def create_share(
    project_id: str,
    body: ShareBody | None = None,
    x_actor: Annotated[str | None, Header()] = None,
    store: ProjectStore = Depends(get_store),
    settings: Settings = Depends(get_settings),
) -> dict:
    store.get_root(project_id)  # 404 si el proyecto no existe
    entry = create_link(
        settings.data_dir, project_id, clean_actor(x_actor) or "", (body or ShareBody()).days
    )
    return {**entry, "url": f"{settings.web_origin.rstrip('/')}/compartido/{entry['token']}"}


@router.get("/{project_id}/compartir")
def list_shares(project_id: str, settings: Settings = Depends(get_settings)) -> dict:
    return {"links": list_links(settings.data_dir, project_id)}


@router.delete("/{project_id}/compartir/{token}")
def revoke_share(
    project_id: str, token: str, settings: Settings = Depends(get_settings)
) -> dict:
    if not revoke_link(settings.data_dir, project_id, token):
        raise HTTPException(status_code=404, detail={"error_type": "share_not_found"})
    return {"revoked": True}


def _project_for(request: Request, token: str, settings: Settings) -> str:
    rate_limit(request, "compartido", max_attempts=240, window_seconds=3600.0)
    project_id = resolve(settings.data_dir, token)
    if project_id is None:
        # Mismo mensaje para inexistente, caducada o revocada: la liga no dice
        # cuál de las tres es a quien no la tiene.
        raise HTTPException(
            status_code=404,
            detail={"error_type": "share_not_found",
                    "message": "Esta liga no existe, caducó o la revocaron."},
        )
    return project_id


@public.get("/{token}")
def shared_meta(
    request: Request,
    token: str,
    store: ProjectStore = Depends(get_store),
    settings: Settings = Depends(get_settings),
) -> dict:
    project_id = _project_for(request, token, settings)
    manifest = store.get_manifest(project_id)
    return {"project_name": manifest.project_name}


@public.get("/{token}/geometry")
def shared_geometry(
    request: Request,
    token: str,
    store: ProjectStore = Depends(get_store),
    settings: Settings = Depends(get_settings),
) -> dict:
    project_id = _project_for(request, token, settings)
    return get_geometry(project_id, store=store, settings=settings)


@public.get("/{token}/generadores.xlsx")
def shared_generadores(
    request: Request,
    token: str,
    store: ProjectStore = Depends(get_store),
    settings: Settings = Depends(get_settings),
) -> Response:
    project_id = _project_for(request, token, settings)
    manifest = store.get_manifest(project_id)
    report = CostReport.model_validate(store.read_artifact(project_id, "cost_report.json"))
    detections = [
        Detection.model_validate(d) for d in store.read_artifact(project_id, "detections.json")
    ]
    try:
        segmentation: SheetSegmentation | None = SheetSegmentation.model_validate(
            store.read_artifact(project_id, "views.json")
        )
    except HTTPException:
        segmentation = None
    try:
        inventory = store.read_artifact(project_id, "inventory.json")
    except HTTPException:
        inventory = None
    reviews = load_reviews(store.get_root(project_id) / settings.processed_dir_name)

    def link_path(visor: str) -> str:
        # Del lado compartido la liga abre el visor compartido, no el proyecto.
        query = visor.split("?", 1)[1] if "?" in visor else ""
        return f"/compartido/{token}?{query}" if query else f"/compartido/{token}"

    content = build_generadores_workbook(
        report, detections, reviews, segmentation=segmentation, inventory=inventory,
        web_origin=settings.web_origin, link_path=link_path,
    )
    filename = f"generadores_{slugify(manifest.project_name)[:40]}.xlsx"
    # Para el piloto: el otro lado bajó los generadores de la liga.
    from klave_engine.common.actividad import registrar

    registrar(store.get_root(project_id) / settings.processed_dir_name, "export", None,
              {"formato": "generadores_compartidos"})
    return Response(
        content=content, media_type=XLSX,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
