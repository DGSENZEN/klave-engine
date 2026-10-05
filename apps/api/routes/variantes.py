"""Las variantes del plano y su mapeo al catálogo de la oficina.

Bajo ``/projects`` a propósito: el middleware de acceso cuida cada proyecto.
La memoria del mapeo es del taller (el catálogo del espacio de trabajo al que
pertenece el proyecto); una decisión aquí vale para el siguiente proyecto.
"""

from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Header, HTTPException
from klave_engine.common.config import Settings
from klave_engine.costing.etiquetas import append_labels, mapping_label
from klave_engine.costing.mapeo import mapear
from klave_engine.costing.models import CostReport
from pydantic import BaseModel

from apps.api.dependencies import ProjectStore, get_settings, get_store, project_recompute_lock
from apps.api.events import clean_actor
from apps.api.routes.catalog import _recompute_project
from apps.api.tenancy import store_for_project

router = APIRouter(prefix="/projects")


class MapearBody(BaseModel):
    rematch: bool = False


class MapeoBody(BaseModel):
    status: Literal["confirmada", "sin_equivalente"]
    target_kind: Literal["concept", "reference"] | None = None
    target_code: str | None = None
    ref_id: int | None = None


def _report(store: ProjectStore, project_id: str) -> CostReport:
    try:
        return CostReport.model_validate(store.read_artifact(project_id, "cost_report.json"))
    except HTTPException as exc:
        raise HTTPException(
            status_code=409,
            detail={"error_type": "not_processed",
                    "message": "Procesa el proyecto antes de mapear sus conceptos."},
        ) from exc


@router.get("/{project_id}/variantes")
def list_variants(project_id: str, store: ProjectStore = Depends(get_store)) -> dict:
    """Cada renglón con sus variantes y a qué de tu catálogo apunta cada una."""
    report = _report(store, project_id)
    counts = {"automatica": 0, "propuesta": 0, "confirmada": 0, "sin_equivalente": 0,
              "sin_mapear": 0}
    lines = []
    for line in report.boq.lines:
        for v in line.variants:
            counts[v.mapping or "sin_mapear"] = counts.get(v.mapping or "sin_mapear", 0) + 1
        lines.append({
            "concept_code": line.concept_code, "description": line.description,
            "unit": line.unit, "phase": line.phase, "quantity": line.quantity,
            "unpriced": line.unpriced,
            "variants": [v.model_dump() for v in line.variants],
        })
    return {"lines": lines, "counts": counts}


@router.post("/{project_id}/variantes/mapear")
def map_variants(
    project_id: str,
    body: MapearBody | None = None,
    x_actor: Annotated[str | None, Header()] = None,
    store: ProjectStore = Depends(get_store),
    settings: Settings = Depends(get_settings),
) -> dict:
    """Propone un concepto de tu catálogo para cada variante sin decisión."""
    actor = clean_actor(x_actor) or ""
    report = _report(store, project_id)
    catalog = store_for_project(settings, project_id)
    with project_recompute_lock(project_id):
        result = mapear(report.boq, catalog, actor="motor", rematch=bool(body and body.rematch))
        _recompute_project(store, settings, project_id, actor, action="mapeo")
    return result


@router.put("/{project_id}/variantes/{variant_key}")
def set_variant_mapping(
    project_id: str,
    variant_key: str,
    body: MapeoBody,
    x_actor: Annotated[str | None, Header()] = None,
    store: ProjectStore = Depends(get_store),
    settings: Settings = Depends(get_settings),
) -> dict:
    """La decisión de una persona: este concepto de mi catálogo, o ninguno."""
    actor = clean_actor(x_actor) or ""
    report = _report(store, project_id)
    variant = next(
        (v for line in report.boq.lines for v in line.variants if v.key == variant_key), None
    )
    if variant is None:
        raise HTTPException(status_code=404, detail={"error_type": "variant_not_found"})
    catalog = store_for_project(settings, project_id)
    previous = catalog.load_variant_mappings().get(variant_key)
    fields: dict = {"status": body.status, "actor": actor, "reason": f"decidido por {actor}"}
    if body.status == "confirmada":
        if body.target_kind == "reference" and body.ref_id is not None:
            ref = catalog.get_reference(body.ref_id)
            if ref is None:
                raise HTTPException(status_code=404, detail={"error_type": "reference_not_found"})
            fields.update(target_kind="reference", target_code=ref["clave"], ref_id=body.ref_id,
                          clave=ref["clave"], description=ref["description"], unit=ref["unit"])
        elif body.target_kind == "concept" and body.target_code:
            concept = next(
                (c for c in catalog.load_concepts() if c["code"] == body.target_code), None
            )
            if concept is None:
                raise HTTPException(status_code=404, detail={"error_type": "concept_not_found"})
            fields.update(target_kind="concept", target_code=concept["code"],
                          clave=concept["code"], description=concept["description"],
                          unit=concept["unit"])
        else:
            raise HTTPException(
                status_code=422,
                detail={"error_type": "target_required",
                        "message": "Confirmar necesita el concepto o el renglón de tu catálogo."},
            )
    control_dir = store.get_root(project_id) / settings.processed_dir_name
    with project_recompute_lock(project_id):
        saved = catalog.set_variant_mapping(variant_key, **fields)
        append_labels(control_dir, [
            mapping_label(variant_key, previous, saved, actor, variant.description)
        ])
        _recompute_project(store, settings, project_id, actor, action="mapeo")
    return saved


@router.delete("/{project_id}/variantes/{variant_key}")
def forget_variant_mapping(
    project_id: str,
    variant_key: str,
    x_actor: Annotated[str | None, Header()] = None,
    store: ProjectStore = Depends(get_store),
    settings: Settings = Depends(get_settings),
) -> dict:
    actor = clean_actor(x_actor) or ""
    catalog = store_for_project(settings, project_id)
    with project_recompute_lock(project_id):
        removed = catalog.delete_variant_mapping(variant_key)
        _recompute_project(store, settings, project_id, actor, action="mapeo")
    return {"removed": removed}
