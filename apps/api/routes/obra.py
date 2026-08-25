"""Obra pública: el catálogo que manda y las estimaciones que se cobran.

Dos piezas que van juntas y que la aplicación no tenía. El catálogo de la
convocante convierte un anteproyecto en una propuesta —mismas claves, mismo
orden, sus cantidades— y las estimaciones son lo que se cobra cada mes una vez
que la obra arrancó. Entre las dos cubren la vida del contrato: ganarlo y
cobrarlo.

Los dos artefactos viven junto al proyecto y no dentro del reporte de costos,
porque no salen del plano: los pone una contratante y los mide un residente.
Un reprocesamiento del dibujo no debe borrarlos.
"""

import json
from pathlib import Path
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Header, HTTPException, UploadFile
from klave_engine.common.config import Settings
from klave_engine.common.io import write_json
from klave_engine.costing.catalog import build_catalog_from_store
from klave_engine.costing.convocante import atar_catalogo, avisos_de_cantidad
from klave_engine.costing.estimaciones import Estimacion, calcular, siguiente
from klave_engine.costing.models import BillOfQuantities, CostingAssumptions
from klave_engine.costing.sources.custom import CustomCatalogError
from klave_engine.costing.sources.presupuesto import parse_presupuesto_file
from pydantic import BaseModel

from apps.api.dependencies import ProjectStore, get_settings, get_store
from apps.api.events import BUS, clean_actor
from apps.api.tenancy import store_for_project

router = APIRouter(prefix="/projects", tags=["obra"])

MAX_IMPORT_BYTES = 8 * 1024 * 1024
CATALOGO = "catalogo_convocante.json"
ESTIMACIONES = "estimaciones.json"


def _control_dir(store: ProjectStore, settings: Settings, project_id: str) -> Path:
    return store.get_root(project_id) / settings.processed_dir_name


def _leer(store: ProjectStore, settings: Settings, project_id: str, nombre: str) -> Any:
    ruta = _control_dir(store, settings, project_id) / nombre
    if not ruta.exists():
        return None
    return json.loads(ruta.read_text())


def _guardar(
    store: ProjectStore, settings: Settings, project_id: str, nombre: str, datos: Any
) -> None:
    write_json(_control_dir(store, settings, project_id) / nombre, datos)


def _boq(store: ProjectStore, project_id: str) -> BillOfQuantities | None:
    try:
        report = store.read_artifact(project_id, "cost_report.json")
    except HTTPException:
        return None
    try:
        return BillOfQuantities.model_validate(report.get("boq") or {})
    except Exception:  # noqa: BLE001 — un reporte viejo no debe tumbar la carga
        return None


def _renglon_payload(renglon: object) -> dict:
    r = renglon
    return {
        "clave": r.clave, "description": r.description, "unit": r.unit,  # type: ignore[attr-defined]
        "quantity": r.quantity, "orden": r.orden, "group": r.group,  # type: ignore[attr-defined]
        "concept_code": r.concept_code, "match_score": r.match_score,  # type: ignore[attr-defined]
        "match_reasons": r.match_reasons,  # type: ignore[attr-defined]
        "quantity_engine": r.quantity_engine,  # type: ignore[attr-defined]
        "diferencia_pct": r.diferencia_pct,  # type: ignore[attr-defined]
        "unit_price": r.unit_price, "amount": r.amount,  # type: ignore[attr-defined]
    }


# ------------------------------------------- catálogo de la convocante -----


@router.post("/{project_id}/catalogo-convocante", status_code=201)
async def cargar_catalogo(
    project_id: str,
    file: UploadFile,
    x_actor: Annotated[str | None, Header()] = None,
    nombre: str = "",
    store: ProjectStore = Depends(get_store),
    settings: Settings = Depends(get_settings),
) -> dict:
    """El catálogo de conceptos que manda la convocante.

    A partir de aquí ese documento es la autoridad sobre qué se cotiza y en qué
    orden; el motor sólo le pone al lado la cantidad que sostiene el plano."""
    raw = await file.read(MAX_IMPORT_BYTES + 1)
    if len(raw) > MAX_IMPORT_BYTES:
        raise HTTPException(
            status_code=413,
            detail={"error_type": "import_too_large", "max_bytes": MAX_IMPORT_BYTES},
        )
    try:
        filas = parse_presupuesto_file(raw, file.filename or "")
    except CustomCatalogError as exc:
        raise HTTPException(
            status_code=422, detail={"error_type": "headers_not_found", "message": str(exc)}
        ) from exc
    if not filas:
        raise HTTPException(
            status_code=422,
            detail={
                "error_type": "catalogo_vacio",
                "message": "No se encontró ningún renglón con clave, descripción, unidad "
                           "y cantidad.",
            },
        )
    catalogo_taller = store_for_project(settings, project_id)
    conceptos = build_catalog_from_store(
        catalogo_taller.load_concepts(), CostingAssumptions()
    )
    precios = {
        code: float(row["price"])
        for code, row in catalogo_taller.load_concept_prices().items()
    }
    atado = atar_catalogo(
        filas, conceptos, _boq(store, project_id),
        nombre=nombre.strip() or Path(file.filename or "catálogo").stem[:80],
        precios=precios,
    )
    payload = {
        "nombre": atado.nombre,
        "renglones": [_renglon_payload(r) for r in atado.renglones],
        "notas": atado.notas,
        "avisos": avisos_de_cantidad(atado),
        "total": atado.total,
        "sin_precio": [r.clave for r in atado.sin_precio],
        "sin_atar": [r.clave for r in atado.sin_atar],
    }
    _guardar(store, settings, project_id, CATALOGO, payload)
    BUS.publish("catalogo_convocante", project_id, clean_actor(x_actor))
    return payload


@router.get("/{project_id}/catalogo-convocante")
def leer_catalogo(
    project_id: str,
    store: ProjectStore = Depends(get_store),
    settings: Settings = Depends(get_settings),
) -> dict:
    datos = _leer(store, settings, project_id, CATALOGO)
    if datos is None:
        return {"nombre": "", "renglones": [], "notas": [], "avisos": [], "total": 0.0}
    return datos


# ---------------------------------------------------------- estimaciones ---


class EstimacionInput(BaseModel):
    estimacion: Estimacion


@router.get("/{project_id}/estimaciones")
def listar_estimaciones(
    project_id: str,
    store: ProjectStore = Depends(get_store),
    settings: Settings = Depends(get_settings),
) -> dict:
    """Las estimaciones del contrato, cada una con su carátula calculada."""
    datos = _leer(store, settings, project_id, ESTIMACIONES) or []
    salida = []
    for cruda in datos:
        est = Estimacion.model_validate(cruda)
        resumen = calcular(est)
        salida.append({"estimacion": est.model_dump(mode="json"), "resumen": vars(resumen)})
    return {"estimaciones": salida}


@router.put("/{project_id}/estimaciones/{numero}")
def guardar_estimacion(
    project_id: str,
    numero: int,
    body: EstimacionInput,
    x_actor: Annotated[str | None, Header()] = None,
    store: ProjectStore = Depends(get_store),
    settings: Settings = Depends(get_settings),
) -> dict:
    """Guardar una estimación con lo medido en el periodo."""
    est = body.estimacion.model_copy(update={"numero": numero})
    datos = _leer(store, settings, project_id, ESTIMACIONES) or []
    datos = [d for d in datos if int(d.get("numero", 0)) != numero]
    datos.append(est.model_dump(mode="json"))
    datos.sort(key=lambda d: int(d.get("numero", 0)))
    _guardar(store, settings, project_id, ESTIMACIONES, datos)
    BUS.publish("estimacion_guardada", project_id, clean_actor(x_actor))
    return {"estimacion": est.model_dump(mode="json"), "resumen": vars(calcular(est))}


@router.post("/{project_id}/estimaciones/siguiente")
def crear_siguiente(
    project_id: str,
    inicio: str,
    fin: str,
    store: ProjectStore = Depends(get_store),
    settings: Settings = Depends(get_settings),
) -> dict:
    """La estimación que sigue, con lo acumulado y lo amortizado ya cargados.

    Encadenar a mano es como se cobra dos veces el mismo metro."""
    datos = _leer(store, settings, project_id, ESTIMACIONES) or []
    if not datos:
        raise HTTPException(
            status_code=409,
            detail={
                "error_type": "sin_estimacion_previa",
                "message": "No hay una estimación anterior de la cual continuar; "
                           "captura la primera con el catálogo contratado.",
            },
        )
    ultima = Estimacion.model_validate(datos[-1])
    nueva = siguiente(ultima, ultima.numero + 1, inicio, fin)
    return {"estimacion": nueva.model_dump(mode="json"), "resumen": vars(calcular(nueva))}
