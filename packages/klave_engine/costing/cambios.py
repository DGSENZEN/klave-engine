"""Qué cambió entre dos revisiones del plano: por elemento y por concepto.

Llega la revisión C con «cambios menores» y alguien vuelve a cuantificar todo
a mano —o no lo hace y se come la diferencia. Aquí cada elemento de la
lectura anterior se busca en la nueva: misma identidad (hoja, tipo, marca,
posición a 5 cm), o la misma marca a menos de 2 m (se movió). Lo que no
encuentra pareja es agregado o eliminado; nunca se adivina. Por concepto, la
cantidad antes y después, su diferencia y lo que vale a precio de hoy.

El mismo cálculo sirve cuando no cambió el plano sino la lectura (una versión
nueva de Klave): quien lo muestra tiene que decirlo, y ``mismo_plano`` es el
dato para decirlo.
"""

from __future__ import annotations

from collections import defaultdict
from pathlib import PurePath

from pydantic import BaseModel, Field

from klave_engine.costing.models import CostReport
from klave_engine.costing.referencias import element_id
from klave_engine.detection.results import Detection, DetectionType

# Lo que el motor lee para ubicar, no para cobrar: la malla se renumera sola.
_CONTEXTO = {DetectionType.grid_line, DetectionType.grid_intersection}
MOVIDO_M = 0.05
RADIO_M = 2.0
# Las propiedades que cambian una cantidad o un precio.
_CAMPOS = {
    "section_cm": "Sección", "spec_rebar": "Armado", "estimated_length": "Longitud",
    "length_m": "Longitud", "estimated_area": "Área", "estimated_thickness": "Espesor",
    "thickness_cm": "Espesor", "diameter": "Diámetro", "diametro": "Diámetro",
    "estimated_span_length": "Claro", "wall_kind": "Tipo de muro", "family": "Sistema",
    "footing_kind": "Tipo de zapata", "material": "Material",
}


class CampoCambiado(BaseModel):
    campo: str
    antes: str
    despues: str


class CambioElemento(BaseModel):
    tipo: str  # agregado | eliminado | movido | modificado
    detection_type: str
    familia: str
    marca: str
    hoja: str
    antes_id: str | None = None
    despues_id: str | None = None
    bbox_antes: list[float] | None = None
    bbox_despues: list[float] | None = None
    movido_m: float = 0.0
    campos: list[CampoCambiado] = Field(default_factory=list)


class CambioConcepto(BaseModel):
    concept_code: str
    descripcion: str
    unidad: str
    fase: str
    cantidad_antes: float
    cantidad_despues: float
    diferencia: float
    precio_unitario: float | None = None  # P.U. de hoy (la lectura nueva)
    importe_diferencia: float | None = None
    elementos: dict[str, int] = Field(default_factory=dict)  # tipo → cuántos


class Cambios(BaseModel):
    antes: str
    despues: str
    mismo_plano: bool | None = None  # None: la lectura anterior no guardó sus planos
    misma_version: bool | None = None
    conceptos: list[CambioConcepto] = Field(default_factory=list)
    elementos: list[CambioElemento] = Field(default_factory=list)
    resumen: dict[str, int] = Field(default_factory=dict)
    importe_diferencia: float = 0.0
    importe_sin_precio: int = 0  # conceptos que cambiaron sin precio


def _hoja(d: Detection) -> str:
    return PurePath(d.evidence.source or "").name


def _centro_m(d: Detection, factor: float) -> tuple[float, float]:
    x0, y0, x1, y1 = d.bbox
    return (x0 + x1) / 2.0 * factor, (y0 + y1) / 2.0 * factor


def _texto(value: object) -> str:
    if isinstance(value, float):
        return f"{value:g}"
    return str(value)


def _distancia_bbox(a: Detection, b: Detection, fa: float, fd: float) -> float:
    return sum(abs(x * fa - y * fd) for x, y in zip(a.bbox, b.bbox, strict=True))


def _campos(a: Detection, b: Detection) -> list[CampoCambiado]:
    out: list[CampoCambiado] = []
    vistos: set[str] = set()
    pa, pb = a.properties or {}, b.properties or {}
    for key, nombre in _CAMPOS.items():
        if nombre in vistos or (key not in pa and key not in pb):
            continue
        va, vb = pa.get(key), pb.get(key)
        if isinstance(va, (int, float)) and isinstance(vb, (int, float)):
            base = max(abs(float(va)), abs(float(vb)), 1e-9)
            if abs(float(va) - float(vb)) / base <= 0.01:
                continue
        elif _texto(va) == _texto(vb):
            continue
        vistos.add(nombre)
        out.append(CampoCambiado(
            campo=nombre, antes="—" if va is None else _texto(va),
            despues="—" if vb is None else _texto(vb),
        ))
    return out


def comparar_elementos(
    antes: list[Detection], despues: list[Detection],
    factor_antes: float | None, factor_despues: float | None,
) -> list[CambioElemento]:
    fa, fd = factor_antes or 1.0, factor_despues or 1.0
    grupos_a: dict[tuple, list[Detection]] = defaultdict(list)
    grupos_d: dict[tuple, list[Detection]] = defaultdict(list)
    for d in antes:
        if d.detection_type not in _CONTEXTO:
            grupos_a[(_hoja(d), d.detection_type.value)].append(d)
    for d in despues:
        if d.detection_type not in _CONTEXTO:
            grupos_d[(_hoja(d), d.detection_type.value)].append(d)
    out: list[CambioElemento] = []

    def cambio(tipo: str, a: Detection | None, b: Detection | None, movido: float = 0.0,
               campos: list[CampoCambiado] | None = None) -> CambioElemento:
        ref = b or a
        assert ref is not None
        return CambioElemento(
            tipo=tipo, detection_type=ref.detection_type.value,
            familia=ref.family_label or ref.detection_type.value, marca=ref.mark or "",
            hoja=PurePath(_hoja(ref)).stem,
            antes_id=a.detection_id if a else None, despues_id=b.detection_id if b else None,
            bbox_antes=list(a.bbox) if a else None, bbox_despues=list(b.bbox) if b else None,
            movido_m=round(movido, 3), campos=campos or [],
        )

    for key in sorted(set(grupos_a) | set(grupos_d)):
        libres_a = list(grupos_a.get(key, []))
        libres_d = list(grupos_d.get(key, []))
        pares: list[tuple[Detection, Detection, float]] = []
        # 1 · Misma identidad: misma marca y misma posición (5 cm).
        por_id: dict[str, list[Detection]] = defaultdict(list)
        for b in libres_d:
            por_id[element_id(b, fd)].append(b)
        quedan_a = []
        for a in libres_a:
            candidatos = por_id.get(element_id(a, fa))
            if candidatos:
                # Varias piezas pueden compartir identidad (corridas partidas
                # por diámetro, tableros con el mismo centro): se toma la que
                # coincide en propiedades y contorno, no la primera.
                def parecido(b: Detection, a: Detection = a) -> tuple[int, float]:
                    return len(_campos(a, b)), _distancia_bbox(a, b, fa, fd)

                mejor = min(candidatos, key=parecido)
                candidatos.remove(mejor)
                pares.append((a, mejor, 0.0))
            else:
                quedan_a.append(a)
        usados = {id(b) for _a, b, _m in pares}
        quedan_d = [b for b in libres_d if id(b) not in usados]
        # 2 · Misma marca, la más cercana a menos de 2 m: se movió.
        candidatos2: list[tuple[float, int, int]] = []
        for i, a in enumerate(quedan_a):
            ca = _centro_m(a, fa)
            for j, b in enumerate(quedan_d):
                if (a.mark or "") != (b.mark or ""):
                    continue
                cb = _centro_m(b, fd)
                dist = ((ca[0] - cb[0]) ** 2 + (ca[1] - cb[1]) ** 2) ** 0.5
                if dist <= RADIO_M:
                    candidatos2.append((dist, i, j))
        candidatos2.sort()
        toma_a: set[int] = set()
        toma_d: set[int] = set()
        for dist, i, j in candidatos2:
            if i in toma_a or j in toma_d:
                continue
            toma_a.add(i)
            toma_d.add(j)
            pares.append((quedan_a[i], quedan_d[j], dist))
        for a, b, dist in pares:
            campos = _campos(a, b)
            if campos:
                out.append(cambio("modificado", a, b, dist, campos))
            elif dist > MOVIDO_M:
                out.append(cambio("movido", a, b, dist))
        for i, a in enumerate(quedan_a):
            if i not in toma_a:
                out.append(cambio("eliminado", a, None))
        for j, b in enumerate(quedan_d):
            if j not in toma_d:
                out.append(cambio("agregado", None, b))
    return out


def comparar(
    antes_run: str,
    despues_run: str,
    antes_dets: list[Detection],
    despues_dets: list[Detection],
    antes_report: CostReport,
    despues_report: CostReport,
    *,
    mismo_plano: bool | None = None,
    misma_version: bool | None = None,
) -> Cambios:
    elementos = comparar_elementos(
        antes_dets, despues_dets,
        antes_report.drawing_units.to_meters(), despues_report.drawing_units.to_meters(),
    )
    por_antes = {e.antes_id: e for e in elementos if e.antes_id}
    por_despues = {e.despues_id: e for e in elementos if e.despues_id}
    lineas_a = {line.concept_code: line for line in antes_report.boq.lines}
    lineas_d = {line.concept_code: line for line in despues_report.boq.lines}
    conceptos: list[CambioConcepto] = []
    total = 0.0
    sin_precio = 0
    for code in [*lineas_d, *(c for c in lineas_a if c not in lineas_d)]:
        a, d = lineas_a.get(code), lineas_d.get(code)
        qa = a.quantity if a else 0.0
        qd = d.quantity if d else 0.0
        diferencia = round(qd - qa, 6)
        conteo: dict[str, int] = defaultdict(int)
        for det_id in (d.source_detections if d else []):
            if det_id in por_despues:
                conteo[por_despues[det_id].tipo] += 1
        for det_id in (a.source_detections if a else []):
            e = por_antes.get(det_id)
            if e is not None and e.tipo == "eliminado":
                conteo["eliminado"] += 1
        if abs(diferencia) <= 1e-6 and not conteo:
            continue
        ref = d or a
        assert ref is not None
        pu = None if (d is None or d.unpriced) else d.unit_price
        importe = round(diferencia * pu, 2) if pu is not None else None
        if importe is None and abs(diferencia) > 1e-6:
            sin_precio += 1
        total += importe or 0.0
        conceptos.append(CambioConcepto(
            concept_code=code, descripcion=ref.description, unidad=ref.unit, fase=ref.phase,
            cantidad_antes=round(qa, 4), cantidad_despues=round(qd, 4), diferencia=diferencia,
            precio_unitario=pu, importe_diferencia=importe, elementos=dict(conteo),
        ))
    resumen: dict[str, int] = defaultdict(int)
    for e in elementos:
        resumen[e.tipo] += 1
    return Cambios(
        antes=antes_run, despues=despues_run, mismo_plano=mismo_plano,
        misma_version=misma_version, conceptos=conceptos, elementos=elementos,
        resumen=dict(resumen), importe_diferencia=round(total, 2), importe_sin_precio=sin_precio,
    )
