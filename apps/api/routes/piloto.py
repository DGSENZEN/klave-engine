"""La medición del piloto: lo que el proyecto ya guarda, convertido en horas,
y lo que la oficina declara de su método anterior y de la entrega."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException
from klave_engine.common.config import Settings
from klave_engine.common.io import write_json
from klave_engine.costing.piloto import PILOTO_FILENAME, leer_declarado, medir
from pydantic import BaseModel, Field

from apps.api.dependencies import ProjectStore, get_settings, get_store
from apps.api.events import clean_actor

router = APIRouter(prefix="/projects", tags=["piloto"])


class Declarado(BaseModel):
    horas_metodo_anterior: float | None = Field(default=None, ge=0, le=10000)
    generadores_aceptados: bool | None = None
    export_importado: bool | None = None
    notas: str = Field(default="", max_length=2000)


@router.get("/{project_id}/piloto")
def get_piloto(
    project_id: str,
    store: ProjectStore = Depends(get_store),
    settings: Settings = Depends(get_settings),
) -> dict:
    control = store.get_root(project_id) / settings.processed_dir_name
    try:
        detections = store.read_artifact(project_id, "detections.json")
    except HTTPException:
        detections = []
    return medir(control, detections)


@router.put("/{project_id}/piloto")
def put_piloto(
    project_id: str,
    body: Declarado,
    x_actor: Annotated[str | None, Header()] = None,
    store: ProjectStore = Depends(get_store),
    settings: Settings = Depends(get_settings),
) -> dict:
    control = store.get_root(project_id) / settings.processed_dir_name
    declarado = {**leer_declarado(control), **body.model_dump(),
                 "actualizado": datetime.now(UTC).isoformat(),
                 "por": clean_actor(x_actor) or ""}
    write_json(control / PILOTO_FILENAME, declarado)
    return get_piloto(project_id, store, settings)
