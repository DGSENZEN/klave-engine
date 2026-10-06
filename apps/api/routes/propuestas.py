"""Las propuestas del lector en Revisión: verlas, decir qué son o que no son
elemento. Confirmar entra por el camino del elemento omitido — la cantidad
se mueve por decisión de una persona, con la medida del recuadro dicha en la
nota —; las dos decisiones quedan como etiqueta y la propuesta no vuelve."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException
from klave_engine.common.config import Settings
from klave_engine.common.ids import short_uuid
from klave_engine.costing.etiquetas import read_labels
from klave_engine.costing.perfil import etiquetar_y_aprender
from klave_engine.costing.reviews import OmittedElement, load_reviews, save_reviews
from klave_engine.lector.propuestas import PROPUESTAS_FILENAME, claves_resueltas
from pydantic import BaseModel, Field

from apps.api.dependencies import ProjectStore, get_settings, get_store, project_recompute_lock
from apps.api.events import clean_actor, clean_client_id
from apps.api.routes.reviews import _perfil_store, _recompute_after_review, _reviews_payload

router = APIRouter(prefix="/projects", tags=["propuestas"])

# Lo que una propuesta puede ser: se cuenta por pieza, o su área es la de su
# recuadro. Lo lineal no — un recuadro no da una longitud honesta.
FAMILIAS = ("castillo", "columna", "pilote", "zapata")


class ConfirmarInput(BaseModel):
    family: str
    note: str = Field(default="", max_length=300)


def _pendientes(store: ProjectStore, settings: Settings, project_id: str) -> list[dict]:
    control_dir = store.get_root(project_id) / settings.processed_dir_name
    try:
        propuestas = store.read_artifact(project_id, PROPUESTAS_FILENAME)
    except HTTPException:
        return []
    resueltas = claves_resueltas(read_labels(control_dir))
    return [p for p in propuestas if p["key"] not in resueltas]


def _buscar(store: ProjectStore, settings: Settings, project_id: str, key: str) -> dict:
    hit = next((p for p in _pendientes(store, settings, project_id) if p["key"] == key), None)
    if hit is None:
        raise HTTPException(status_code=404, detail={
            "error_type": "propuesta_not_found",
            "message": "Esa propuesta ya no está: alguien la resolvió o el plano cambió.",
        })
    return hit


@router.get("/{project_id}/propuestas")
def list_propuestas(
    project_id: str,
    store: ProjectStore = Depends(get_store),
    settings: Settings = Depends(get_settings),
) -> dict:
    pendientes = _pendientes(store, settings, project_id)
    return {
        "familias": list(FAMILIAS),
        "propuestas": [{k: v for k, v in p.items() if k != "features"} for p in pendientes],
    }


def _etiqueta(p: dict, action: str, verdict: str, actor: str, note: str) -> dict:
    return {"kind": "propuesta", "key": p["key"], "action": action, "verdict": verdict,
            "actor": actor, "note": note[:300], "bloque": p.get("bloque", ""),
            "features": p.get("features") or {}, "features_version": p.get("features_version"),
            "proposals": {"model": "elemento", "model_version": p.get("modelo")}}


@router.post("/{project_id}/propuestas/{key}/confirmar")
def confirm_propuesta(
    project_id: str,
    key: str,
    body: ConfirmarInput,
    x_actor: Annotated[str | None, Header()] = None,
    x_client_id: Annotated[str | None, Header()] = None,
    store: ProjectStore = Depends(get_store),
    settings: Settings = Depends(get_settings),
) -> dict:
    family = body.family.strip().lower()
    if family not in FAMILIAS:
        raise HTTPException(status_code=422, detail={
            "error_type": "unknown_family",
            "message": "Una propuesta puede ser " + ", ".join(FAMILIAS)
            + ". Si es otra cosa, agrégala en «Lo que Klave no vio» con su medida.",
        })
    actor = clean_actor(x_actor) or ""
    control_dir = store.get_root(project_id) / settings.processed_dir_name
    with project_recompute_lock(project_id):
        p = _buscar(store, settings, project_id, key)
        ancho, alto = float(p["ancho_m"]), float(p["alto_m"])
        seccion = (
            f"{round(min(ancho, alto) * 100)}x{round(max(ancho, alto) * 100)}"
            if family in ("castillo", "columna") else ""
        )
        reviews = load_reviews(control_dir)
        reviews.omitted.append(OmittedElement(
            element_id=short_uuid("om"), family=family, count=1,
            area_m2=round(ancho * alto, 4) if family == "zapata" else None,
            section_cm=seccion, sheet=Path(p["hoja"]).stem, bbox=list(p["bbox"]),
            note=("propuesta del lector confirmada; medida del recuadro "
                  f"{ancho:.2f} × {alto:.2f} m") + (f" — {body.note.strip()}"
                                                     if body.note.strip() else ""),
            actor=actor,
        ))
        save_reviews(control_dir, reviews)
        etiquetar_y_aprender(control_dir, [_etiqueta(p, "confirm_proposal", family, actor,
                                                      body.note)],
                             _perfil_store(settings, project_id))
        _recompute_after_review(
            store, settings, project_id, actor, clean_client_id(x_client_id),
            "proposal_confirmed", family,
        )
    return _reviews_payload(reviews)


@router.post("/{project_id}/propuestas/{key}/descartar")
def reject_propuesta(
    project_id: str,
    key: str,
    x_actor: Annotated[str | None, Header()] = None,
    store: ProjectStore = Depends(get_store),
    settings: Settings = Depends(get_settings),
) -> dict:
    actor = clean_actor(x_actor) or ""
    control_dir = store.get_root(project_id) / settings.processed_dir_name
    with project_recompute_lock(project_id):
        p = _buscar(store, settings, project_id, key)
        etiquetar_y_aprender(control_dir, [_etiqueta(p, "reject_proposal", "no_es_elemento",
                                                      actor, "")],
                             _perfil_store(settings, project_id))
    return {"ok": True, "key": key}
