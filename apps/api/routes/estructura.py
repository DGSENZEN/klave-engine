"""La lectura estructural de un proyecto por API: el modelo que vale para la corrida activa (sus
tarjetas por familia, sus hallazgos con ids que no se mueven, sus reglas, sus avisos y lo que el
presupuesto midió del modelo), sus elementos por familia con sus definiciones, y la decisión de
una persona sobre un campo de una marca, que se guarda, queda como etiqueta y recalcula; o se
quita, y el presupuesto queda como si nunca hubiera estado.

**Qué modelo.** Siempre ``leer_estructura_vigente``: el escenario del recálculo si es de la
corrida activa y está al día con las decisiones guardadas; si no, el de la corrida (que dice si
quedó atrás). Una corrida anterior al modelo, una que no se puede leer o un proyecto sin procesar
contestan ``{"disponible": false}`` con su aviso, nunca un error.

**Decidir.** Lo que el modelo no aplicaría (la altura de un castillo, una longitud para vigas de
claros distintos, una variante que la marca no tiene, un valor que no se lee, una marca que la
lectura no tiene) se contesta 422 con el aviso del modelo, sin guardar nada: nunca un 200 callado.
Cambiar lo que dice el plano necesita una nota. Guardar, etiquetar y recalcular van bajo el
candado del proyecto, así que dos decisiones a la vez se guardan las dos y sus recálculos van uno
tras otro; si el recálculo se rompe, la decisión no queda a medias.

**Acceso.** Bajo ``/projects``: el middleware de acceso pide «viewer» para leer y «editor» para
decidir o quitar, y cada ruta lo vuelve a pedir con ``require_project_role`` (la misma regla), así
que el router no queda abierto aunque se monte de otro modo."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated, Any

from fastapi import APIRouter, Body, Depends, Header, HTTPException, Query, Request
from klave_engine.common.config import Settings
from klave_engine.common.io import write_text
from klave_engine.costing.etiquetas import LABELS_FILENAME, append_labels
from klave_engine.costing.recompute import COST_REPORT_OVERRIDE_FILENAME
from klave_engine.detection.text_patterns import TextPatternConfig
from klave_engine.estructura.dato import Dato
from klave_engine.estructura.definiciones import normalizar_marca
from klave_engine.estructura.elementos import FAMILIAS_ESTRUCTURALES
from klave_engine.estructura.modelo import (
    CAMPOS_DECIDIBLES,
    DECISIONES_FILENAME,
    ESTRUCTURA_DERIVADA_FILENAME,
    NOMBRE_DEL_CAMPO,
    Decision,
    Estructura,
    decisiones_vigentes,
    guardar_decision,
    leer_decisiones,
    leer_estructura_con_motivo,
    leer_estructura_vigente,
    quitar_decision,
    revisar_decision,
)
from pydantic import BaseModel, Field, ValidationError

from apps.api.auth.access import require_project_role
from apps.api.dependencies import ProjectStore, get_settings, get_store, project_recompute_lock
from apps.api.events import clean_actor, clean_client_id
from apps.api.routes.reviews import _recompute_after_review

router = APIRouter(prefix="/projects", tags=["estructura"])

ANTERIOR = "Esta lectura es anterior a la lectura estructural. Reprocesa el proyecto para verla."
SIN_PROCESAR = "El proyecto no se ha procesado: procésalo para ver su lectura estructural."
_MURO_MAXIMO_CM = 200.0


class DecisionInput(BaseModel):
    """Lo que una persona decide: el ``valor`` de un ``campo`` de una ``marca`` (la sección
    ``[b, h]`` en cm o ``{"area_cm2": …}``, la longitud en m, el armado como texto o como sus
    piezas), con su ``nota``; ``para_muro_cm`` nombra la variante de una marca con variantes por
    muro."""

    marca: str = Field(min_length=1, max_length=60)
    campo: str = Field(min_length=1, max_length=40)
    valor: Any = None
    nota: str = Field(default="", max_length=300)
    para_muro_cm: Any = None


@dataclass
class _Lectura:
    estructura: Estructura | None
    motivo: str  # "" (disponible), "anterior", "ilegible", "sin_procesar"
    aviso: str
    control: Path


def _lectura(store: ProjectStore, settings: Settings, project_id: str) -> _Lectura:
    """El modelo que vale para la corrida activa, o por qué no lo hay (404: no hay proyecto)."""
    control = store.get_root(project_id) / settings.processed_dir_name
    corrida = store.artifact_root(project_id)
    e = leer_estructura_vigente(control, corrida)
    if e is not None:
        return _Lectura(e, "", "", control)
    _, motivo = leer_estructura_con_motivo(corrida)
    if motivo:
        return _Lectura(
            None,
            "ilegible",
            f"La lectura estructural de esta corrida no se pudo leer: {motivo}. Reprocesa el "
            "proyecto para rehacerla.",
            control,
        )
    if not (corrida / "detections.json").exists():
        return _Lectura(None, "sin_procesar", SIN_PROCESAR, control)
    return _Lectura(None, "anterior", ANTERIOR, control)


def _payload(lectura: _Lectura) -> dict[str, Any]:
    """Lo que ``Estructura`` tiene, como lo lee Revisión. ``al_dia``: si el modelo tiene aplicadas
    exactamente las decisiones guardadas; ``decisiones_guardadas``: las guardadas (una por marca,
    campo y variante: la más reciente)."""
    guardadas, avisos_de_decisiones = leer_decisiones(lectura.control)
    e = lectura.estructura
    base: dict[str, Any] = {
        "campos_decidibles": [
            {"campo": c, "nombre": NOMBRE_DEL_CAMPO[c]} for c in CAMPOS_DECIDIBLES
        ],
    }
    if e is None:
        return {
            "disponible": False,
            "motivo": lectura.motivo,
            "al_dia": False,
            "avisos": [lectura.aviso, *avisos_de_decisiones],
            "resumen": [],
            "verificaciones": [],
            "reglas": None,
            "familias": [],
            "decisiones": [],
            "decisiones_guardadas": [
                d.model_dump(mode="json")
                for d in decisiones_vigentes(guardadas, TextPatternConfig())
            ],
            "escrituras": [],
            **base,
        }
    vigentes = decisiones_vigentes(guardadas, e.patrones)
    familias: dict[str, int] = {}
    for x in e.elementos:
        familias[x.familia] = familias.get(x.familia, 0) + 1
    return {
        "disponible": True,
        "motivo": "",
        "al_dia": vigentes == e.decisiones,
        "avisos": list(dict.fromkeys([*e.avisos, *avisos_de_decisiones])),
        "resumen": [r.model_dump(mode="json") for r in e.resumen],
        "verificaciones": [v.model_dump(mode="json") for v in e.verificaciones],
        "reglas": e.reglas.model_dump(mode="json"),
        "familias": [{"familia": f, "colocaciones": n} for f, n in sorted(familias.items())],
        "decisiones": [d.model_dump(mode="json") for d in e.decisiones],
        "decisiones_guardadas": [d.model_dump(mode="json") for d in vigentes],
        "escrituras": [w.model_dump(mode="json") for w in e.escrituras],
        **base,
    }


@router.get("/{project_id}/estructura")
def get_estructura(
    project_id: str,
    request: Request,
    store: ProjectStore = Depends(get_store),
    settings: Settings = Depends(get_settings),
) -> dict:
    """El modelo estructural de la corrida activa: sus tarjetas, sus hallazgos, sus reglas, sus
    avisos, sus decisiones y lo que el presupuesto midió del modelo (``escrituras``: las
    detecciones guardan lo que leyó el detector)."""
    require_project_role(request, project_id, "viewer")
    return _payload(_lectura(store, settings, project_id))


@router.get("/{project_id}/estructura/elementos")
def get_elementos(
    project_id: str,
    request: Request,
    familia: Annotated[str | None, Query(max_length=40)] = None,
    marca: Annotated[str | None, Query(max_length=60)] = None,
    store: ProjectStore = Depends(get_store),
    settings: Settings = Depends(get_settings),
) -> dict:
    """Los elementos de una familia (o de una marca, o todos), cada campo con su fuente, y las
    definiciones de sus marcas (más las de la familia que el plano define sin colocar)."""
    require_project_role(request, project_id, "viewer")
    lectura = _lectura(store, settings, project_id)
    e = lectura.estructura
    if e is None:
        return {
            "disponible": False,
            "motivo": lectura.motivo,
            "avisos": [lectura.aviso],
            "familia": familia,
            "elementos": [],
            "definiciones": {},
            "de_familia": None,
            "escrituras": [],
        }
    familia = familia.strip().lower() if familia else None
    conocidas = (
        set(FAMILIAS_ESTRUCTURALES)
        | {x.familia for x in e.elementos}
        | {d.familia for d in e.definiciones}
    )
    if familia and familia not in conocidas:
        raise HTTPException(
            status_code=422,
            detail={
                "error_type": "familia_desconocida",
                "message": f"«{familia}» no es una familia de la lectura estructural: "
                + ", ".join(sorted(conocidas))
                + ".",
            },
        )
    buscada = normalizar_marca(marca, e.patrones) if marca and marca.strip() else None
    elementos = [
        x
        for x in e.elementos
        if (familia is None or x.familia == familia) and (buscada is None or x.marca == buscada)
    ]
    marcas = {x.marca for x in elementos}
    definiciones = {
        d.marca: d.model_dump(mode="json")
        for d in e.definiciones
        if d.marca in marcas
        or (buscada is not None and d.marca == buscada)
        or (buscada is None and (familia is None or d.familia == familia))
    }
    de_familia = next((d for d in e.por_familia if familia and d.familia == familia), None)
    ids = {x.detection_id for x in elementos}
    return {
        "disponible": True,
        "motivo": "",
        "avisos": [],
        "familia": familia,
        "elementos": [x.model_dump(mode="json") for x in elementos],
        "definiciones": definiciones,
        "de_familia": de_familia.model_dump(mode="json") if de_familia is not None else None,
        "escrituras": [w.model_dump(mode="json") for w in e.escrituras if w.detection_id in ids],
    }


def _invalida(error_type: str, message: str, status: int = 422) -> HTTPException:
    return HTTPException(status_code=status, detail={"error_type": error_type, "message": message})


def _campo(campo: str) -> str:
    campo = campo.strip()
    if campo not in CAMPOS_DECIDIBLES:
        nombres = ", ".join(f"{NOMBRE_DEL_CAMPO[c]} ({c})" for c in CAMPOS_DECIDIBLES)
        raise _invalida(
            "campo_desconocido", f"«{campo[:40]}» no es un campo que se decida: {nombres}."
        )
    return campo


def _muro(valor: Any) -> float | None:
    """El espesor de muro de la variante (cm): un número finito, positivo y de muro; o 422."""
    if valor is None or valor == "":
        return None
    numero: float | None
    if isinstance(valor, bool):
        numero = None
    elif isinstance(valor, int | float):
        numero = float(valor)
    elif isinstance(valor, str):
        try:
            numero = float(valor.strip().replace(",", "."))
        except ValueError:
            numero = None
    else:
        numero = None
    # NaN e infinito tampoco están entre 0 y el máximo.
    if numero is None or not 0 < numero <= _MURO_MAXIMO_CM:
        raise _invalida(
            "muro_invalido",
            "La variante se nombra por el espesor de su muro en cm (un número entre 0 y "
            f"{_MURO_MAXIMO_CM:g}).",
        )
    return numero


def _dato(d: Dato | None) -> dict[str, Any] | None:
    if d is None:
        return None
    return {"valor": d.valor, "fuente": d.fuente, "texto": d.texto, "hoja": d.hoja}


_TOCADOS = (DECISIONES_FILENAME, ESTRUCTURA_DERIVADA_FILENAME, COST_REPORT_OVERRIDE_FILENAME)


@dataclass
class _Foto:
    """Lo que una decisión toca, como estaba antes de guardarla: las decisiones, el escenario del
    modelo, el costo derivado y hasta dónde llegaba el diario de etiquetas."""

    control: Path
    archivos: dict[str, str | None]
    etiquetas: int | None

    @classmethod
    def de(cls, control: Path) -> _Foto:
        diario = control / LABELS_FILENAME
        return cls(
            control,
            {
                n: (control / n).read_text(encoding="utf-8") if (control / n).exists() else None
                for n in _TOCADOS
            },
            diario.stat().st_size if diario.exists() else None,
        )

    def restaurar(self) -> None:
        for nombre, contenido in self.archivos.items():
            ruta = self.control / nombre
            if contenido is None:
                ruta.unlink(missing_ok=True)
            else:
                write_text(ruta, contenido)
        diario = self.control / LABELS_FILENAME
        if self.etiquetas is None:
            diario.unlink(missing_ok=True)
        elif diario.exists():
            with diario.open("r+b") as f:
                f.truncate(self.etiquetas)


def _recalcular(
    store: ProjectStore,
    settings: Settings,
    project_id: str,
    actor: str,
    client_id: str | None,
    detalle: str,
    foto: _Foto,
) -> None:
    """El recálculo de siempre (``_recompute_after_review``: el costo, el modelo derivado y los
    eventos). Si se rompe, lo que la decisión tocó vuelve a como estaba antes de guardarla
    (``foto``) y el error sigue: nada a medias."""
    try:
        _recompute_after_review(
            store, settings, project_id, actor, client_id, "estructura_decision", detalle
        )
    except Exception:
        foto.restaurar()
        raise


@router.post("/{project_id}/estructura/decisiones")
def decidir(
    project_id: str,
    request: Request,
    cuerpo: Annotated[Any, Body()] = None,
    x_actor: Annotated[str | None, Header()] = None,
    x_client_id: Annotated[str | None, Header()] = None,
    store: ProjectStore = Depends(get_store),
    settings: Settings = Depends(get_settings),
) -> dict:
    """Guarda la decisión, la deja como etiqueta (``decide_value``, con lo que había) y recalcula;
    contesta el modelo nuevo (lo que da ``GET /estructura``)."""
    require_project_role(request, project_id, "editor")
    try:
        body = DecisionInput.model_validate(cuerpo)
    except ValidationError as error:
        # Sin repetir lo recibido: un NaN en el eco volvería el 422 un 500.
        campos = sorted({str(x["loc"][0]) for x in error.errors() if x.get("loc")})
        raise _invalida(
            "decision_invalida",
            "La decisión necesita marca, campo, valor y nota (texto de hasta 300); no se leyó: "
            + (", ".join(campos) or "el cuerpo"),
        ) from None
    campo = _campo(body.campo)
    para_muro_cm = _muro(body.para_muro_cm)
    marca = body.marca.strip()
    if not marca:
        raise _invalida("decision_invalida", "La decisión necesita la marca.")
    nota = " ".join(body.nota.split())
    actor = clean_actor(x_actor) or ""
    with project_recompute_lock(project_id):
        lectura = _lectura(store, settings, project_id)
        e = lectura.estructura
        if e is None:
            raise _invalida("estructura_no_disponible", lectura.aviso, status=409)
        d = Decision(
            marca=marca,
            campo=campo,  # type: ignore[arg-type]  # validado contra CAMPOS_DECIDIBLES
            valor=body.valor,
            nota=nota,
            actor=actor,
            fecha=datetime.now(UTC),
            para_muro_cm=para_muro_cm,
        )
        revision = revisar_decision(e, d)
        if revision.rechazo is not None:
            raise _invalida("decision_rechazada", revision.rechazo)
        if not nota and revision.del_plano:
            raise _invalida("nota_requerida", revision.nota_requerida or "")
        foto = _Foto.de(lectura.control)
        guardar_decision(lectura.control, d)
        append_labels(
            lectura.control,
            [
                {
                    "kind": "estructura",
                    "action": "decide_value",
                    "marca": revision.marca,
                    "campo": campo,
                    "para_muro_cm": para_muro_cm,
                    "valor": body.valor,
                    "valor_modelo": revision.valor,
                    "antes": _dato(revision.antes),
                    "del_plano": [_dato(x) for x in revision.del_plano],
                    "nota": nota,
                    "actor": actor,
                }
            ],
        )
        _recalcular(
            store, settings, project_id, actor, clean_client_id(x_client_id),
            f"{revision.marca} · {NOMBRE_DEL_CAMPO[campo]}", foto,
        )  # fmt: skip
        return _payload(_lectura(store, settings, project_id))


@router.delete("/{project_id}/estructura/decisiones")
def quitar(
    project_id: str,
    request: Request,
    marca: Annotated[str, Query(min_length=1, max_length=60)],
    campo: Annotated[str, Query(min_length=1, max_length=40)],
    para_muro_cm: Annotated[str | None, Query(max_length=20)] = None,
    x_actor: Annotated[str | None, Header()] = None,
    x_client_id: Annotated[str | None, Header()] = None,
    store: ProjectStore = Depends(get_store),
    settings: Settings = Depends(get_settings),
) -> dict:
    """Quita la decisión de esa marca, campo (y variante) y recalcula: el modelo y el presupuesto
    quedan como si nunca hubiera estado (R235). 404 si no hay tal decisión."""
    require_project_role(request, project_id, "editor")
    campo = _campo(campo)
    muro = _muro(para_muro_cm)
    actor = clean_actor(x_actor) or ""
    with project_recompute_lock(project_id):
        lectura = _lectura(store, settings, project_id)
        config = lectura.estructura.patrones if lectura.estructura is not None else None
        foto = _Foto.de(lectura.control)
        quitadas = quitar_decision(lectura.control, marca.strip(), campo, muro, config=config)
        if not quitadas:
            raise _invalida(
                "decision_no_encontrada",
                f"No hay una decisión guardada sobre {marca.strip()} ({NOMBRE_DEL_CAMPO[campo]})"
                + (f" para muros de {muro:g} cm" if muro is not None else "")
                + ".",
                status=404,
            )
        ultima = max(quitadas, key=lambda x: x.fecha)
        append_labels(
            lectura.control,
            [
                {
                    "kind": "estructura",
                    "action": "undo_decision",
                    "marca": ultima.marca,
                    "campo": campo,
                    "para_muro_cm": muro,
                    "valor": None,
                    "antes": {"valor": ultima.valor, "fuente": "humano", "actor": ultima.actor,
                              "nota": ultima.nota},
                    "actor": actor,
                }
            ],
        )  # fmt: skip
        _recalcular(
            store, settings, project_id, actor, clean_client_id(x_client_id),
            f"{marca.strip()} · {NOMBRE_DEL_CAMPO[campo]} (quitada)", foto,
        )  # fmt: skip
        return _payload(_lectura(store, settings, project_id))
