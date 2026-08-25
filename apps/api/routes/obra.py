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

from fastapi import APIRouter, Depends, Header, HTTPException, Response, UploadFile
from klave_engine.common.config import Settings
from klave_engine.common.ids import slugify
from klave_engine.common.io import write_json
from klave_engine.costing.catalog import build_catalog_from_store
from klave_engine.costing.convenios import (
    Convenio,
    catalogo_vigente,
    desde_estimacion,
)
from klave_engine.costing.convenios import (
    estado as estado_contrato,
)
from klave_engine.costing.convocante import atar_catalogo, avisos_de_cantidad
from klave_engine.costing.estimaciones import (
    Estimacion,
    RenglonEstimado,
    calcular,
    siguiente,
)
from klave_engine.costing.exports import build_estimacion_workbook
from klave_engine.costing.finiquito import Finiquito
from klave_engine.costing.finiquito import calcular as calcular_finiquito
from klave_engine.costing.generadores import DIMENSIONES
from klave_engine.costing.models import BillOfQuantities, CostingAssumptions
from klave_engine.costing.sources.custom import CustomCatalogError
from klave_engine.costing.sources.presupuesto import parse_presupuesto_file
from pydantic import BaseModel

from apps.api.dependencies import ProjectStore, get_settings, get_store
from apps.api.events import BUS, clean_actor
from apps.api.tenancy import store_for_project

router = APIRouter(prefix="/projects", tags=["obra"])
# Fuera de /projects a propósito: no es de un proyecto, y ahí
# GET /projects/{project_id} se la tragaría como si fuera un id.
medidas = APIRouter(prefix="/medidas", tags=["obra"])

MAX_IMPORT_BYTES = 8 * 1024 * 1024
CATALOGO = "catalogo_convocante.json"
ESTIMACIONES = "estimaciones.json"
CONVENIOS = "convenios.json"
FINIQUITO = "finiquito.json"


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

    # Un convenio firmado cambió lo contratado. Sin esto la estimación seguiría
    # marcando como excedido algo que ya se convino, y el aviso que sí importa
    # se perdería entre los que ya no.
    convs = _convenios(store, settings, project_id)
    if convs:
        vigente = catalogo_vigente(
            {r.clave: r.quantity_contract for r in nueva.renglones}, convs
        )
        claves = {r.clave for r in nueva.renglones}
        renglones = [
            r.model_copy(update={"quantity_contract": vigente[r.clave]})
            for r in nueva.renglones
        ]
        # Un convenio puede traer conceptos que no estaban en el catálogo.
        for conv in sorted(convs, key=lambda c: c.numero):
            for extra in conv.renglones:
                if extra.clave in claves:
                    continue
                claves.add(extra.clave)
                renglones.append(
                    RenglonEstimado(
                        clave=extra.clave, description=extra.description, unit=extra.unit,
                        unit_price=extra.unit_price, quantity_contract=extra.quantity,
                        quantity_period=0.0, quantity_previous=0.0,
                    )
                )
        # El catálogo de la convocante es el contrato, pero no todos los
        # proyectos lo cargaron. Sin ese respaldo manda lo que se capturó a
        # mano: tomar cero de un catálogo ausente dejaría el monto del contrato
        # por los suelos y la amortización del anticipo saldría mal, callada.
        monto = _monto_contrato(store, settings, project_id) or nueva.monto_contrato
        nueva = nueva.model_copy(
            update={
                "renglones": renglones,
                "monto_contrato": estado_contrato(convs, monto, 0).monto_vigente,
            }
        )
    return {"estimacion": nueva.model_dump(mode="json"), "resumen": vars(calcular(nueva))}


# --- Convenios modificatorios ------------------------------------------------
#
# Un convenio cambia el contrato, así que a partir de aquí «lo contratado» deja
# de ser lo que se firmó al principio. Las estimaciones tienen que leer el
# catálogo vigente o van a seguir marcando como excedido algo que ya se convino.


class ConvenioInput(BaseModel):
    convenio: Convenio


def _convenios(store: ProjectStore, settings: Settings, project_id: str) -> list[Convenio]:
    datos = _leer(store, settings, project_id, CONVENIOS) or []
    return [Convenio.model_validate(d) for d in datos]


def _monto_contrato(store: ProjectStore, settings: Settings, project_id: str) -> float:
    """El monto original del contrato, del catálogo de la convocante."""
    datos = _leer(store, settings, project_id, CATALOGO)
    if not datos:
        return 0.0
    return round(
        sum(
            float(r.get("quantity") or 0) * float(r.get("unit_price") or 0)
            for r in datos.get("renglones", [])
        ),
        2,
    )


@router.get("/{project_id}/convenios")
def listar_convenios(
    project_id: str,
    plazo_dias: int = 0,
    store: ProjectStore = Depends(get_store),
    settings: Settings = Depends(get_settings),
) -> dict:
    """Los convenios firmados y qué tan cerca están del techo del art. 59."""
    convs = _convenios(store, settings, project_id)
    monto = _monto_contrato(store, settings, project_id)
    crudas = _leer(store, settings, project_id, ESTIMACIONES) or []
    capturado = float(crudas[-1].get("monto_contrato") or 0) if crudas else None
    st = estado_contrato(convs, monto, plazo_dias, capturado or None)
    return {
        "convenios": [c.model_dump(mode="json") for c in convs],
        "estado": {
            "monto_original": st.monto_original,
            "monto_convenido": st.monto_convenido,
            "monto_vigente": st.monto_vigente,
            "monto_pct": st.monto_pct,
            "plazo_original_dias": st.plazo_original_dias,
            "dias_convenidos": st.dias_convenidos,
            "plazo_vigente_dias": st.plazo_vigente_dias,
            "plazo_pct": st.plazo_pct,
            "rebasa_techo": st.rebasa_techo,
            "techo_pct": 25.0,
            "avisos": st.avisos,
        },
    }


@router.put("/{project_id}/convenios/{numero}")
def guardar_convenio(
    project_id: str,
    numero: int,
    body: ConvenioInput,
    x_actor: Annotated[str | None, Header()] = None,
    store: ProjectStore = Depends(get_store),
    settings: Settings = Depends(get_settings),
) -> dict:
    conv = body.convenio.model_copy(update={"numero": numero})
    datos = _leer(store, settings, project_id, CONVENIOS) or []
    datos = [d for d in datos if int(d.get("numero", 0)) != numero]
    datos.append(conv.model_dump(mode="json"))
    datos.sort(key=lambda d: int(d.get("numero", 0)))
    _guardar(store, settings, project_id, CONVENIOS, datos)
    BUS.publish("convenio_guardado", project_id, clean_actor(x_actor))
    return {"convenio": conv.model_dump(mode="json")}


@router.delete("/{project_id}/convenios/{numero}", status_code=204)
def borrar_convenio(
    project_id: str,
    numero: int,
    x_actor: Annotated[str | None, Header()] = None,
    store: ProjectStore = Depends(get_store),
    settings: Settings = Depends(get_settings),
) -> None:
    datos = _leer(store, settings, project_id, CONVENIOS) or []
    quedan = [d for d in datos if int(d.get("numero", 0)) != numero]
    if len(quedan) == len(datos):
        raise HTTPException(status_code=404, detail="No existe ese convenio.")
    _guardar(store, settings, project_id, CONVENIOS, quedan)
    BUS.publish("convenio_guardado", project_id, clean_actor(x_actor))


@router.post("/{project_id}/convenios/desde-estimacion/{numero}")
def borrador_de_convenio(
    project_id: str,
    numero: int,
    fecha: str,
    store: ProjectStore = Depends(get_store),
    settings: Settings = Depends(get_settings),
) -> dict:
    """El borrador que resuelve lo que una estimación no pudo cobrar.

    No se guarda: sale a la pantalla para que alguien le escriba el motivo. La
    ley pide causa justificada y el motor sabe que se excedió, no por qué."""
    datos = _leer(store, settings, project_id, ESTIMACIONES) or []
    cruda = next((d for d in datos if int(d.get("numero", 0)) == numero), None)
    if cruda is None:
        raise HTTPException(status_code=404, detail="No existe esa estimación.")
    est = Estimacion.model_validate(cruda)
    convs = _convenios(store, settings, project_id)
    borrador = desde_estimacion(est, numero=max((c.numero for c in convs), default=0) + 1,
                               fecha=fecha)
    if not borrador.renglones:
        raise HTTPException(
            status_code=409,
            detail={
                "error_type": "sin_excedentes",
                "message": "Esa estimación no rebasa ninguna cantidad del catálogo, "
                           "así que no necesita convenio.",
            },
        )
    return {"convenio": borrador.model_dump(mode="json")}


# --- Finiquito ---------------------------------------------------------------


class FiniquitoInput(BaseModel):
    finiquito: Finiquito


@router.get("/{project_id}/finiquito")
def leer_finiquito(
    project_id: str,
    store: ProjectStore = Depends(get_store),
    settings: Settings = Depends(get_settings),
) -> dict:
    """El finiquito guardado, o uno precargado con lo que ya sabe la aplicación.

    Precargar no es inventar: lo ejecutado, lo pagado y lo retenido salen de las
    estimaciones que ya se capturaron. Lo que el motor no puede saber —los días
    de atraso, el porcentaje de pena que fija el contrato— nace en cero y a la
    vista."""
    guardado = _leer(store, settings, project_id, FINIQUITO)
    if guardado:
        fin = Finiquito.model_validate(guardado)
        return {
            "finiquito": fin.model_dump(mode="json"),
            "resumen": calcular_finiquito(fin).payload(),
            "guardado": True,
        }

    crudas = _leer(store, settings, project_id, ESTIMACIONES) or []
    estimaciones = [Estimacion.model_validate(d) for d in crudas]
    resumenes = [calcular(e) for e in estimaciones]
    convs = _convenios(store, settings, project_id)
    # La base del anticipo tiene que ser la misma que produjo las
    # amortizaciones, o el remanente sale de una resta entre dos contratos
    # distintos y el finiquito acusa de algo que no pasó.
    ultima_monto = estimaciones[-1].monto_contrato if estimaciones else 0.0
    monto = ultima_monto or _monto_contrato(store, settings, project_id)
    monto_vigente = estado_contrato(convs, monto, 0).monto_vigente

    ultima = estimaciones[-1] if estimaciones else None
    fin = Finiquito(
        fecha="",
        monto_contrato=monto_vigente,
        ejecutado=round(sum(r.importe for r in resumenes), 2),
        pagado=round(sum(r.liquido for r in resumenes), 2),
        anticipo_otorgado=round(
            monto_vigente * (ultima.anticipo_pct if ultima else 0.0) / 100.0, 2
        ),
        anticipo_amortizado=round(sum(r.amortizacion for r in resumenes), 2),
        retenciones_aplicadas=round(sum(r.retencion for r in resumenes), 2),
    )
    return {
        "finiquito": fin.model_dump(mode="json"),
        "resumen": calcular_finiquito(fin).payload(),
        "guardado": False,
    }


@router.put("/{project_id}/finiquito")
def guardar_finiquito(
    project_id: str,
    body: FiniquitoInput,
    x_actor: Annotated[str | None, Header()] = None,
    store: ProjectStore = Depends(get_store),
    settings: Settings = Depends(get_settings),
) -> dict:
    fin = body.finiquito
    _guardar(store, settings, project_id, FINIQUITO, fin.model_dump(mode="json"))
    BUS.publish("finiquito_guardado", project_id, clean_actor(x_actor))
    return {
        "finiquito": fin.model_dump(mode="json"),
        "resumen": calcular_finiquito(fin).payload(),
        "guardado": True,
    }


# --- Generadores -------------------------------------------------------------


@medidas.get("/unidades-generador")
def unidades_generador() -> dict:
    """Qué dimensiones multiplica cada unidad.

    La pantalla necesita esta tabla para calcular mientras alguien teclea, y
    tenerla escrita dos veces es tenerla distinta el día que cambie. La
    multiplicación puede vivir en cualquier lado; qué se multiplica, no."""
    return {"unidades": {u: list(dims) for u, dims in DIMENSIONES.items()}}


XLSX_MEDIA_TYPE = (
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
)


@router.get("/{project_id}/estimaciones/{numero}/export.xlsx")
def exportar_estimacion(
    project_id: str,
    numero: int,
    store: ProjectStore = Depends(get_store),
    settings: Settings = Depends(get_settings),
) -> Response:
    """La estimación como se entrega: carátula, conceptos y generadores juntos.

    En un solo archivo a propósito. Una estimación que llega sin su generador se
    regresa, y mandarlos por separado es la forma más fácil de que uno de los
    dos se quede en el escritorio."""
    datos = _leer(store, settings, project_id, ESTIMACIONES) or []
    cruda = next((d for d in datos if int(d.get("numero", 0)) == numero), None)
    if cruda is None:
        raise HTTPException(status_code=404, detail="No existe esa estimación.")
    est = Estimacion.model_validate(cruda)
    obra = store.get_manifest(project_id).project_name
    contenido = build_estimacion_workbook(est, calcular(est), obra)
    nombre = f"estimacion_{numero}_{slugify(obra)[:40]}.xlsx"
    return Response(
        content=contenido,
        media_type=XLSX_MEDIA_TYPE,
        headers={"Content-Disposition": f'attachment; filename="{nombre}"'},
    )
