"""El copiloto: preguntas sobre la normativa, sobre la aplicación, y sobre el
proyecto que el usuario tiene abierto.

El contexto del proyecto se arma en cada petición desde el diagnóstico vivo,
nunca desde lo que el modelo recuerde de una conversación anterior: si el
ingeniero acaba de darle precio a un concepto, la siguiente respuesta ya lo
sabe. Y como todo lo demás en Klave, si no hay con qué respaldar la respuesta,
la respuesta es decirlo.
"""

from __future__ import annotations

from pathlib import Path
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from klave_engine.common.config import Settings
from klave_engine.copilot.acciones import Accion, proponer
from klave_engine.copilot.service import responder
from klave_engine.costing.catalog_store import CatalogStore
from klave_engine.costing.hallazgos import diagnose
from klave_engine.costing.models import CostingOverrides, CostReport
from klave_engine.costing.presentation import resolve_money_state
from klave_engine.costing.recompute import load_overrides, recompute_and_persist
from klave_engine.costing.reviews import load_reviews
from klave_engine.llm.reader import (
    active_model,
    configured_asker,
    credentials_available,
    is_transient,
)
from pydantic import BaseModel, Field

from apps.api.auth.common import rate_limit
from apps.api.dependencies import ProjectStore, get_settings, get_store
from apps.api.events import BUS, clean_actor
from apps.api.gasto import registrar_uso, revisar_presupuesto, workspace_de
from apps.api.routes.catalog import get_catalog
from apps.api.tenancy import store_for_project

router = APIRouter(prefix="/copilot", tags=["copilot"])

# The repo's own docs are half the knowledge base: they explain the app.
DOCS_DIR = Path(__file__).resolve().parents[3] / "docs"


class Pregunta(BaseModel):
    pregunta: str = Field(min_length=2, max_length=500)
    # When set, the answer may use this project's live findings as its own.
    project_id: str | None = Field(default=None, max_length=120)


def _contexto(
    store: ProjectStore, settings: Settings, project_id: str
) -> dict[str, Any] | None:
    """Los hechos actuales del proyecto: su diagnóstico y su plazo."""
    try:
        report = CostReport.model_validate(store.read_artifact(project_id, "cost_report.json"))
        manifest = store.get_manifest(project_id)
    except HTTPException:
        return None
    control_dir = store.get_root(project_id) / settings.processed_dir_name
    diagnostico = diagnose(report, reviews=load_reviews(control_dir))
    return {
        "project_id": project_id,
        "nombre": manifest.project_name,
        "resumen": diagnostico.resumen,
        "hallazgos": [h.model_dump() for h in diagnostico.hallazgos],
        "plazo_habil": report.schedule.total_duration_days,
        "plazo_natural": report.schedule.calendar_days,
    }


class Aplicar(BaseModel):
    project_id: str = Field(max_length=120)
    tipo: str = Field(max_length=60)
    hallazgo_id: str = Field(default="", max_length=80)


@router.get("/acciones/{project_id}")
def acciones_del_proyecto(
    project_id: str,
    store: ProjectStore = Depends(get_store),
    settings: Settings = Depends(get_settings),
    catalog: CatalogStore = Depends(get_catalog),
) -> dict:
    """Lo que el copiloto puede hacer por este presupuesto, con su vista previa.

    Derivado del diagnóstico, no redactado por un modelo: reproducible, gratis
    y auditable."""
    contexto = _acciones(store, settings, catalog, project_id)
    return {"acciones": [_serializar(a) for a in contexto]}


def _serializar(accion: Accion) -> dict:
    return {
        "tipo": accion.tipo,
        "titulo": accion.titulo,
        "descripcion": accion.descripcion,
        "endpoint": accion.endpoint,
        "vista_previa": [c.__dict__ for c in accion.vista_previa],
        "requiere": accion.requiere,
        "reversible": accion.reversible,
        "hallazgo_id": accion.hallazgo_id,
        "aplicable": bool(accion.peticiones) and not accion.requiere,
    }


def _acciones(
    store: ProjectStore, settings: Settings, catalog: CatalogStore, project_id: str
) -> list[Accion]:
    try:
        report = CostReport.model_validate(store.read_artifact(project_id, "cost_report.json"))
    except HTTPException:
        return []
    control_dir = store.get_root(project_id) / settings.processed_dir_name
    diagnostico = diagnose(report, reviews=load_reviews(control_dir))
    return proponer(report, diagnostico, catalog, project_id)


@router.post("/aplicar")
def aplicar(
    body: Aplicar,
    request: Request,
    x_actor: Annotated[str | None, Header()] = None,
    store: ProjectStore = Depends(get_store),
    settings: Settings = Depends(get_settings),
    catalog: CatalogStore = Depends(get_catalog),
) -> dict:
    """Ejecuta una acción propuesta, por la misma puerta que la interfaz.

    Se vuelve a derivar la acción antes de aplicarla: lo que se ejecuta es lo
    que el presupuesto pide **ahora**, no lo que pedía cuando se dibujó el
    botón. Si el hallazgo ya se resolvió, no hay nada que hacer y se dice."""
    rate_limit(request, "copilot_apply", max_attempts=60, window_seconds=3600.0)
    actor = clean_actor(x_actor) or ""
    disponibles = _acciones(store, settings, catalog, body.project_id)
    accion = next(
        (
            a
            for a in disponibles
            if a.tipo == body.tipo
            and (not body.hallazgo_id or a.hallazgo_id == body.hallazgo_id)
        ),
        None,
    )
    if accion is None:
        raise HTTPException(
            status_code=409,
            detail={
                "error_type": "accion_no_disponible",
                "message": "Ese hallazgo ya no está: el presupuesto cambió desde que "
                "se propuso la acción. Vuelve a revisarlo.",
            },
        )
    if accion.requiere or not accion.peticiones:
        raise HTTPException(
            status_code=422,
            detail={
                "error_type": "accion_incompleta",
                "message": accion.requiere
                or "Esa acción necesita un dato que el motor no puede suponer.",
            },
        )

    # Todo o nada: se comprueba cada petición antes de tocar el catálogo, para
    # no dejar el presupuesto a medio arreglar si la quinta falla.
    if accion.tipo == "adoptar_precio_publicado":
        for peticion in accion.peticiones:
            problema = catalog.check_concept_reference(
                peticion["concepto"], int(peticion["body"]["ref_id"])
            )
            if problema:
                raise HTTPException(
                    status_code=422,
                    detail={
                        "error_type": "accion_no_valida",
                        "message": f"{peticion['concepto']}: {problema} No apliqué nada.",
                    },
                )

    aplicadas: list[str] = []
    for peticion in accion.peticiones:
        if accion.tipo == "adoptar_precio_publicado":
            catalog.adopt_concept_reference(
                peticion["concepto"], int(peticion["body"]["ref_id"])
            )
            # La descripción viaja al presupuesto y al Excel que firma el
            # cliente: cobrar f'c=300 y seguir diciendo 250 sería el mismo
            # desacuerdo con el plano, al revés.
            if peticion.get("descripcion"):
                catalog.update_concept(
                    peticion["concepto"], description=peticion["descripcion"]
                )
            aplicadas.append(peticion["concepto"])

    # El presupuesto se recalcula con el catálogo nuevo, como en cualquier
    # cambio de precios hecho a mano.
    root = store.get_root(body.project_id)
    control_dir = root / settings.processed_dir_name
    # Loaded once and reused for both totals below: sign-off does not change
    # mid-request, so re-deriving it per read would just be the bug again.
    reviews = load_reviews(control_dir)
    antes = None
    try:
        reporte_antes = CostReport.model_validate(
            store.read_artifact(body.project_id, "cost_report.json")
        )
        estado_antes = resolve_money_state(reporte_antes.money_basis, reviews.verification)
        antes = None if estado_antes == "blocked" else reporte_antes.integration.grand_total
    except HTTPException:
        pass
    overrides = load_overrides(control_dir) or CostingOverrides()
    report = recompute_and_persist(
        store.artifact_root(body.project_id),
        control_dir,
        root / "reports",
        body.project_id,
        overrides,
        catalog_store=store_for_project(settings, body.project_id),
    )
    state = resolve_money_state(report.money_basis, reviews.verification)
    total = None if state == "blocked" else report.integration.grand_total
    BUS.publish(
        "costing_updated",
        project_id=body.project_id,
        actor=actor,
        data={
            "version": overrides.version,
            "direct_cost": report.boq.direct_cost_total,
            "grand_total": total,
            "prev_grand_total": antes,
            "review_action": f"copilot:{accion.tipo}",
        },
    )
    return {
        "aplicadas": aplicadas,
        "total_antes": antes,
        "total_despues": total,
        "accion": accion.titulo,
    }


@router.get("/status")
def copilot_status(settings: Settings = Depends(get_settings)) -> dict:
    return {
        "available": credentials_available(settings.ai_provider),
        "model": active_model(settings.ai_provider, settings.ai_model) or "",
    }


@router.post("/ask")
def ask(
    body: Pregunta,
    request: Request,
    store: ProjectStore = Depends(get_store),
    settings: Settings = Depends(get_settings),
) -> dict:
    rate_limit(request, "copilot", max_attempts=60, window_seconds=3600.0)
    workspace = workspace_de(request, settings)
    revisar_presupuesto(settings, workspace)
    if not credentials_available(settings.ai_provider):
        raise HTTPException(
            status_code=409,
            detail={
                "error_type": "ai_not_configured",
                "message": "El copiloto necesita credenciales de IA; pide a tu "
                "administrador que las configure.",
            },
        )
    contexto = (
        _contexto(store, settings, body.project_id) if body.project_id else None
    )
    modelo = active_model(settings.ai_provider, settings.ai_model) or ""
    medido: dict[str, int] = {"entrada": 0, "salida": 0}

    def preguntar_midiendo(system: str, prompt: str) -> str:
        # Sin cuenta de tokens del proveedor, se estima por caracteres: una
        # estimación rotulada vale más que un renglón en blanco en la bitácora.
        texto = configured_asker(settings.ai_provider, settings.ai_model)(system, prompt)
        medido["entrada"] += len(system) + len(prompt)
        medido["salida"] += len(texto)
        return texto

    try:
        respuesta = responder(
            body.pregunta,
            DOCS_DIR,
            preguntar_midiendo,
            contexto=contexto,
        )
    except Exception as exc:  # noqa: BLE001 — a busy provider is news, not a crash
        detalle = str(exc)
        transitorio = is_transient(exc)
        raise HTTPException(
            status_code=503 if transitorio else 502,
            detail={
                "error_type": "ai_provider_error",
                "message": (
                    "El proveedor de IA está saturado o agotó su cuota; inténtalo en "
                    "un momento."
                    if transitorio
                    else "El proveedor de IA rechazó la consulta."
                )
                + f" ({detalle[:160]})",
            },
        ) from exc
    if medido["entrada"]:
        # ~4 caracteres por token es la regla de dedo habitual; la bitácora
        # guarda de dónde salió el número para que nadie lo lea como exacto.
        registrar_uso(
            settings,
            workspace,
            project_id=body.project_id or "",
            modelo=modelo,
            proveedor=settings.ai_provider,
            tipo="copiloto",
            tokens_entrada=medido["entrada"] // 4,
            tokens_salida=medido["salida"] // 4,
        )
    return {
        "texto": respuesta.texto,
        "citas": [c.__dict__ for c in respuesta.citas],
        "fundamentada": respuesta.fundamentada,
        "aviso": respuesta.aviso,
        "con_contexto": contexto is not None,
    }
