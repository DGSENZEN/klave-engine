"""Gold set: real drawings with known-good detections, and the runner that
keeps the engine honest against them.

An entry is captured from a processed project: its current detections are
the labels, and every human review on it is folded in — excluded detections
leave the labels, confirmed ones are pinned. The entry's ``status`` says how
much to trust it: ``baseline`` (no reviews: a regression guard, not truth),
``partial`` (some reviews), ``verified`` (the engineer signed off the
detections step). Drawings are identified by content hash, never committed.

    python -m klave_engine.evals.gold capture data/uploads/<root> --id prueba-1
    python -m klave_engine.evals.gold run            # all entries
"""

import argparse
import hashlib
import shutil
import sys
import tempfile
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from klave_engine.common.config import Settings, get_settings
from klave_engine.common.io import read_json, write_json, write_text
from klave_engine.costing.models import BoqLine, CostingConfig, CostReport
from klave_engine.costing.report import generate_cost_report
from klave_engine.costing.reviews import load_reviews
from klave_engine.detection.dimensions import DimensionInventory
from klave_engine.detection.results import Detection
from klave_engine.detection.views import SheetSegmentation
from klave_engine.dxf.units import DrawingUnits
from klave_engine.pipeline import run_full_pipeline

GOLD_DIR = Path("evals/gold")
DRAWING_SUFFIXES = (".dxf", ".dwg")


class TypeScore(BaseModel):
    detection_type: str
    expected: int
    predicted: int
    precision: float
    recall: float
    f1: float
    baseline_f1: float
    passed: bool


class QuantityExpectation(BaseModel):
    """What one concept should measure on this drawing. ``engine`` rows are
    the current engine's own figure (a regression fence); ``human`` rows are
    a takeoff someone did by hand (the truth), with its own tolerance;
    ``crudo`` rows were counted or measured on the raw drawing by a script
    independent of the engine (the truth too). A capture never overwrites a
    ``human`` or ``crudo`` row."""

    quantity: float
    unit: str
    tolerance_pct: float = 10.0
    source: Literal["engine", "human", "crudo"] = "engine"
    note: str = ""
    # R171: the quantity of each variant of a concept priced by variant (its key → quantity),
    # so a shift between variants — the same metres re-priced as another diameter or section —
    # cannot pass the gate while the concept's total stays put.
    variants: dict[str, float] | None = None


class MoneyExpectation(BaseModel):
    """Quantities and the direct cost at the engine's reference prices, so a
    change in a rule, a matrix or a seed price shows up as money."""

    model_config = ConfigDict(extra="forbid")

    concepts: dict[str, QuantityExpectation] = Field(default_factory=dict)
    direct_cost: float | None = None
    direct_cost_tolerance_pct: float = 5.0
    unpriced: list[str] = Field(default_factory=list)
    # Lo que el motor produce y el gold, a sabiendas, no cerca —un renglón cuya cantidad nadie ha
    # verificado contra el plano, o ``"costo_directo"``—, cada uno con su razón: no es «concepto
    # nuevo» y ``gold money`` no lo vuelve a capturar. Todo lo demás que el motor produzca y el gold
    # no tenga sigue fallando.
    sin_cerca: dict[str, str] | None = None


class MoneyScore(BaseModel):
    concept_code: str
    unit: str
    expected: float
    actual: float | None
    deviation_pct: float | None
    tolerance_pct: float
    source: str
    passed: bool


CAMPOS_DE_FAMILIA = ("colocaciones", "con_definicion", "criticos_total", "criticos_del_plano")
SEVERIDADES = ("bloquea", "duda", "aviso")
NUMEROS_DE_VERIFICACION = range(1, 12)
_PREFIJOS_SIN_CERCA = ("por_familia.", "verificaciones.")
# La identidad de un hallazgo en la cerca: sus marcas, ordenadas y unidas con «+»; ésta si no
# toca ninguna (un aviso de toda una familia, una regla de la hoja).
SIN_MARCA = "(sin marca)"


class EstructuraExpectation(BaseModel):
    """La cerca de la lectura estructural (``estructura.json``), exacta.

    ``por_familia``: por familia, sus cuentas de la tarjeta (``CAMPOS_DE_FAMILIA``).
    ``por_hoja``: por familia cuyas colocaciones se cercan, cuántas hay en cada hoja (una
    colocación que se cambia de planta mueve su altura y su dinero aunque el total no cambie).
    ``verificaciones``: cuántos hallazgos da cada verificación (1–11), por su número (``"7"``:
    todas sus severidades juntas) o por número y severidad (``"1/bloquea"``), nunca las dos para un
    mismo número. ``hallazgos``: por cada clave cercada con hallazgos, quiénes son —la identidad de
    cada uno (sus marcas, ``SIN_MARCA`` si no toca ninguna), ordenadas—, así que cambiar un hallazgo
    por otro no pasa. ``sin_cerca``: lo que el gold, a sabiendas, no cerca, cada cosa con su razón:
    ``"por_familia.zapata"`` (toda la familia), ``"por_familia.castillo.criticos_del_plano"``,
    ``"verificaciones.7"`` o ``"verificaciones.1/aviso"``; nada puede estar cercado y excusado a la
    vez. Todo lo demás debe ser cero: una familia, una hoja o una verificación que el gold no cerca
    ni excusa y que el motor empieza a dar, falla. ``transcripcion``: la ruta de una transcripción
    hecha a mano (formato de la Tarea 16); si la hay, las lecturas del motor por (marca, hoja) deben
    ser exactamente las suyas."""

    model_config = ConfigDict(extra="forbid")

    por_familia: dict[str, dict[str, int]] = Field(default_factory=dict)
    por_hoja: dict[str, dict[str, int]] = Field(default_factory=dict)
    verificaciones: dict[str, int] = Field(default_factory=dict)
    hallazgos: dict[str, list[str]] = Field(default_factory=dict)
    transcripcion: str | None = None
    sin_cerca: dict[str, str] | None = None

    @field_validator("por_familia")
    @classmethod
    def _campos_conocidos(cls, v: dict[str, dict[str, int]]) -> dict[str, dict[str, int]]:
        for familia, campos in v.items():
            extra = set(campos) - set(CAMPOS_DE_FAMILIA)
            if extra:
                raise ValueError(f"{familia}: campos que la tarjeta no tiene: {sorted(extra)}")
        return v

    @field_validator("verificaciones")
    @classmethod
    def _claves_de_verificacion(cls, v: dict[str, int]) -> dict[str, int]:
        for clave in v:
            _clave_de_verificacion(clave)
        totales = {c for c in v if "/" not in c}
        mezcladas = sorted(c for c in v if "/" in c and c.partition("/")[0] in totales)
        if mezcladas:
            raise ValueError(
                f"{mezcladas}: un número se cerca por su total o por severidad, no ambos"
            )
        return v

    @field_validator("sin_cerca")
    @classmethod
    def _claves_sin_cerca(cls, v: dict[str, str] | None) -> dict[str, str] | None:
        for clave, razon in (v or {}).items():
            if not clave.startswith(_PREFIJOS_SIN_CERCA):
                raise ValueError(f"«{clave}»: sin_cerca empieza con {_PREFIJOS_SIN_CERCA}")
            if clave.startswith("verificaciones."):
                _clave_de_verificacion(clave.removeprefix("verificaciones."))
            else:
                partes = clave.removeprefix("por_familia.").split(".")
                if len(partes) > 2 or (len(partes) == 2 and partes[1] not in CAMPOS_DE_FAMILIA):
                    raise ValueError(f"«{clave}»: no es una familia ni un campo de su tarjeta")
            if not razon.strip():
                raise ValueError(f"«{clave}»: lo que no se cerca lleva su razón")
        return v

    @model_validator(mode="after")
    def _coherente(self) -> "EstructuraExpectation":
        sin = self.sin_cerca or {}
        for familia, campos in self.por_familia.items():
            for campo in campos:
                if f"por_familia.{familia}" in sin or f"por_familia.{familia}.{campo}" in sin:
                    raise ValueError(f"{familia}.{campo}: está cercado y excusado a la vez")
        for clave in self.verificaciones:
            numero = clave.partition("/")[0]
            excusas = {f"verificaciones.{numero}", f"verificaciones.{clave}"}
            if "/" not in clave:
                excusas |= {f"verificaciones.{numero}/{s}" for s in SEVERIDADES}
            if excusas & set(sin):
                raise ValueError(f"verificación {clave}: está cercada y excusada a la vez")
        for clave, ids in self.hallazgos.items():
            if clave not in self.verificaciones:
                raise ValueError(f"hallazgos {clave}: la verificación no está cercada")
            if len(ids) != self.verificaciones[clave] or ids != sorted(ids):
                raise ValueError(f"hallazgos {clave}: {len(ids)} ordenados, la cuenta dice "
                                 f"{self.verificaciones[clave]}")  # fmt: skip
        for clave, n in self.verificaciones.items():
            if n and clave not in self.hallazgos:
                raise ValueError(f"verificación {clave}: se cerca su cuenta sin sus hallazgos")
        for familia, hojas in self.por_hoja.items():
            total = self.por_familia.get(familia, {}).get("colocaciones")
            if total is None:
                raise ValueError(f"por_hoja {familia}: sus colocaciones no están cercadas")
            if sum(hojas.values()) != total:
                raise ValueError(f"por_hoja {familia}: suma {sum(hojas.values())}, son {total}")
        for familia, campos in self.por_familia.items():
            if campos.get("colocaciones") and familia not in self.por_hoja:
                raise ValueError(f"{familia}: se cercan sus colocaciones sin sus hojas")
        return self


def _clave_de_verificacion(clave: str) -> tuple[int, str | None]:
    numero, barra, severidad = clave.partition("/")
    if not numero.isdigit() or (barra and severidad not in SEVERIDADES):
        raise ValueError(f"«{clave}»: la clave es «N» o «N/severidad» ({', '.join(SEVERIDADES)})")
    if int(numero) not in NUMEROS_DE_VERIFICACION:
        raise ValueError(f"«{clave}»: las verificaciones van de 1 a 11")
    return int(numero), (severidad if barra else None)


def identidad_de_hallazgo(v: dict) -> str:
    """Quién es un hallazgo en la cerca: sus marcas, ordenadas y unidas con «+»."""
    marcas = sorted({str(m) for m in v.get("marcas", [])})
    return "+".join(marcas) if marcas else SIN_MARCA


def _comparar_hallazgos(clave: str, esperados: list[str], reales: list[str]) -> list[str]:
    if sorted(esperados) == sorted(reales):
        return []
    faltan = sorted((Counter(esperados) - Counter(reales)).elements())
    sobran = sorted((Counter(reales) - Counter(esperados)).elements())
    return [f"verificación {clave}, hallazgos: faltan {faltan}, sobran {sobran}"]


def score_estructura(
    want: EstructuraExpectation, estructura_json: dict | None
) -> tuple[bool, list[str]]:
    """La cerca, exacta, contra el ``estructura.json`` de una corrida: cada cuenta cercada igual
    (y sus hallazgos y sus hojas, los mismos), lo excusado en ``sin_cerca`` sin medir y todo lo
    demás en cero. Las diferencias, en español, empiezan por lo que cambió
    («castillo.con_definicion: …», «castillo en ES-400: …», «verificación 7/duda: …»)."""
    if estructura_json is None:
        return False, ["la corrida no escribió estructura.json y el gold cerca su lectura"]
    sin_cerca = want.sin_cerca or {}
    diffs: list[str] = []
    tarjetas = {t["familia"]: t for t in estructura_json.get("resumen", [])}
    hojas_reales: dict[str, Counter[str]] = {}
    for x in estructura_json.get("elementos", []):
        hojas_reales.setdefault(str(x["familia"]), Counter())[str(x.get("hoja", ""))] += 1
    for familia in sorted(set(tarjetas) | set(want.por_familia)):
        if f"por_familia.{familia}" in sin_cerca:
            continue
        cercados = want.por_familia.get(familia, {})
        tarjeta = tarjetas.get(familia, {})
        for campo in CAMPOS_DE_FAMILIA:
            if campo not in cercados and f"por_familia.{familia}.{campo}" in sin_cerca:
                continue
            esperado = cercados.get(campo, 0)
            real = int(tarjeta.get(campo, 0))
            if real != esperado:
                origen = "" if campo in cercados else " (no está en el gold: debe ser 0)"
                diffs.append(f"{familia}.{campo}: esperado {esperado}, motor {real}{origen}")
        if familia in want.por_hoja:
            esperadas = want.por_hoja[familia]
            reales = hojas_reales.get(familia, Counter())
            for hoja in sorted(set(esperadas) | set(reales)):
                if esperadas.get(hoja, 0) != reales.get(hoja, 0):
                    diffs.append(f"{familia} en {hoja}: esperado {esperadas.get(hoja, 0)}, "
                                 f"motor {reales.get(hoja, 0)}")  # fmt: skip
    cuenta: Counter[tuple[int, str]] = Counter()
    ids: dict[str, list[str]] = {}
    for v in estructura_json.get("verificaciones", []):
        numero, severidad = int(v["numero"]), str(v["severidad"])
        cuenta[(numero, severidad)] += 1
        for clave in (str(numero), f"{numero}/{severidad}"):
            ids.setdefault(clave, []).append(identidad_de_hallazgo(v))
    numeros = {n for n, _ in cuenta} | {_clave_de_verificacion(c)[0] for c in want.verificaciones}
    for numero in sorted(numeros):
        if f"verificaciones.{numero}" in sin_cerca:
            continue
        total = sum(q for (n, _s), q in cuenta.items() if n == numero)
        if str(numero) in want.verificaciones:
            if total != want.verificaciones[str(numero)]:
                diffs.append(
                    f"verificación {numero}: esperado {want.verificaciones[str(numero)]}, "
                    f"motor {total}"
                )
            elif str(numero) in want.hallazgos:
                diffs += _comparar_hallazgos(
                    str(numero), want.hallazgos[str(numero)], ids.get(str(numero), [])
                )
            continue
        for severidad in SEVERIDADES:
            clave = f"{numero}/{severidad}"
            if clave not in want.verificaciones and f"verificaciones.{clave}" in sin_cerca:
                continue
            esperado = want.verificaciones.get(clave, 0)
            real = cuenta.get((numero, severidad), 0)
            if real != esperado:
                origen = "" if clave in want.verificaciones else " (no está en el gold: debe ser 0)"
                diffs.append(f"verificación {clave}: esperado {esperado}, motor {real}{origen}")
            elif clave in want.hallazgos:
                diffs += _comparar_hallazgos(clave, want.hallazgos[clave], ids.get(clave, []))
    return not diffs, diffs


def estructura_from_json(
    estructura_json: dict, sin_cerca: dict[str, str] | None = None
) -> EstructuraExpectation:
    """La cerca que una corrida da, sin lo que ``sin_cerca`` excusa (que se conserva con su
    razón): las tarjetas con algo distinto de cero, sus colocaciones por hoja, y cada
    verificación por número y severidad con sus hallazgos. Sólo se captura de una corrida cuyas
    cuentas se verificaron contra el plano crudo."""
    sin_cerca = dict(sin_cerca or {})
    por_familia: dict[str, dict[str, int]] = {}
    for t in estructura_json.get("resumen", []):
        familia = t["familia"]
        if f"por_familia.{familia}" in sin_cerca:
            continue
        campos = {
            c: int(t.get(c, 0)) for c in CAMPOS_DE_FAMILIA
            if f"por_familia.{familia}.{c}" not in sin_cerca
        }
        if any(campos.values()):
            por_familia[familia] = campos
    hojas: dict[str, Counter[str]] = {}
    for x in estructura_json.get("elementos", []):
        familia = str(x["familia"])
        if por_familia.get(familia, {}).get("colocaciones"):
            hojas.setdefault(familia, Counter())[str(x.get("hoja", ""))] += 1
    ids: dict[str, list[str]] = {}
    for v in estructura_json.get("verificaciones", []):
        ids.setdefault(f"{int(v['numero'])}/{v['severidad']}", []).append(identidad_de_hallazgo(v))
    verificaciones = {
        clave: len(lista) for clave, lista in sorted(ids.items(), key=lambda kv: _orden(kv[0]))
        if f"verificaciones.{clave}" not in sin_cerca
        and f"verificaciones.{clave.partition('/')[0]}" not in sin_cerca
    }
    return EstructuraExpectation(
        por_familia=por_familia,
        por_hoja={f: dict(sorted(c.items())) for f, c in sorted(hojas.items())},
        verificaciones=verificaciones,
        hallazgos={clave: sorted(ids[clave]) for clave in verificaciones},
        sin_cerca=sin_cerca or None,
    )


def _orden(clave: str) -> tuple[int, int]:
    numero, severidad = _clave_de_verificacion(clave)
    return numero, SEVERIDADES.index(severidad) if severidad else -1


_LEIDAS_DEL_PLANO = frozenset({"cuadro", "detalle", "nota"})


def _texto_canonico(valor: Any) -> str | None:
    if valor is None:
        return None
    texto = "".join(str(valor).upper().split())
    return texto or None


def _seccion_canonica(valor: Any) -> tuple[float, ...] | None:
    if not valor:
        return None
    return tuple(sorted(float(v) for v in valor))


def _muro(valor: Any) -> float | None:
    return None if valor is None else float(valor)


def score_transcripcion(path: Path, schedules_json: dict | None) -> tuple[bool, list[str]]:
    """R7: una transcripción hecha a mano (formato de la Tarea 16: ``lecturas`` con ``marca``,
    ``hoja``, ``longitudinal``, ``estribos``, ``seccion_cm`` y, si hacen falta, ``hoja_llave``
    —el marco, cuando dos marcos llevan el mismo código— y ``para_muro_cm`` —la variante de una
    marca por el espesor de su muro, como CI—; ``dudas`` con ``marca`` y ``hoja``) contra las
    lecturas del plano del motor (``schedules.json``: fuentes cuadro, detalle o nota, nunca la IA),
    por (marca, marco, variante), en los dos sentidos: lo que la transcripción lee y el motor no
    —o lee distinto— y lo que el motor lee y la transcripción no tiene. Una lectura repetida en la
    transcripción es un error; lo que deja en ``dudas`` no se compara. Los textos se comparan sin
    espacios y en mayúsculas; la sección sin el orden de sus lados."""
    from klave_engine.estructura.definiciones import normalizar_marca

    if schedules_json is None:
        return False, ["la corrida no escribió schedules.json y el gold tiene una transcripción"]
    try:
        hecha = read_json(Path(path))
    except (OSError, ValueError) as exc:
        return False, [f"la transcripción {path} no se puede leer: {exc}"]
    diffs: list[str] = []
    llaves_de_hoja: dict[str, set[str]] = {}
    motor: dict[tuple[str, str, float | None], dict[str, set[Any]]] = {}
    hoja_de_llave: dict[str, str] = {}
    for spec in schedules_json.get("specs", []):
        if spec.get("source") not in _LEIDAS_DEL_PLANO or not spec.get("mark"):
            continue
        hoja = str(spec.get("hoja") or "")
        llave_hoja = str(spec.get("hoja_llave") or hoja)
        llaves_de_hoja.setdefault(hoja, set()).add(llave_hoja)
        hoja_de_llave[llave_hoja] = hoja
        llave = (normalizar_marca(str(spec["mark"])), llave_hoja, _muro(spec.get("para_muro_cm")))
        lecturas = motor.setdefault(
            llave, {"longitudinal": set(), "estribos": set(), "seccion_cm": set()}
        )
        if (t := _texto_canonico(spec.get("rebar"))) is not None:
            lecturas["longitudinal"].add(t)
        if (t := _texto_canonico(spec.get("stirrups"))) is not None:
            lecturas["estribos"].add(t)
        if (s := _seccion_canonica(spec.get("section_cm"))) is not None:
            lecturas["seccion_cm"].add(s)

    def llave_de_hoja(d: dict) -> str:
        if d.get("hoja_llave"):
            return str(d["hoja_llave"])
        hoja = str(d["hoja"])
        marcos = llaves_de_hoja.get(hoja, set())
        if len(marcos) > 1:
            diffs.append(f"{d['marca']} en {hoja}: esa hoja la llevan {len(marcos)} marcos; la "
                         "transcripción debe decir su hoja_llave")  # fmt: skip
        return next(iter(marcos)) if len(marcos) == 1 else hoja

    dudas = {(normalizar_marca(str(d["marca"])), llave_de_hoja(d)) for d in hecha.get("dudas", [])}
    esperado: dict[tuple[str, str, float | None], dict[str, Any]] = {}
    for lectura in hecha.get("lecturas", []):
        llave = (normalizar_marca(str(lectura["marca"])), llave_de_hoja(lectura),
                 _muro(lectura.get("para_muro_cm")))  # fmt: skip
        if llave in esperado:
            diffs.append(f"{lectura['marca']} en {lectura['hoja']}: la transcripción la lee dos "
                         "veces")  # fmt: skip
            continue
        esperado[llave] = {
            "longitudinal": {t} if (t := _texto_canonico(lectura.get("longitudinal"))) else set(),
            "estribos": {t} if (t := _texto_canonico(lectura.get("estribos"))) else set(),
            "seccion_cm": {s} if (s := _seccion_canonica(lectura.get("seccion_cm"))) else set(),
        }
    for llave in sorted(set(esperado) | set(motor), key=lambda k: (k[0], k[1], k[2] or 0.0)):
        marca, marco, muro = llave
        if (marca, marco) in dudas:
            continue
        nombre = f"{marca} en {hoja_de_llave.get(marco, marco)}" + (
            f" (muros de {muro:g} cm)" if muro is not None else ""
        )
        if llave not in esperado:
            diffs.append(f"{nombre}: el motor la lee y la transcripción no la tiene")
            continue
        if llave not in motor:
            diffs.append(f"{nombre}: la transcripción la lee y el motor no")
            continue
        for campo in ("longitudinal", "estribos", "seccion_cm"):
            if esperado[llave][campo] != motor[llave][campo]:
                diffs.append(
                    f"{nombre}, {campo}: transcripción {sorted(esperado[llave][campo])}, "
                    f"motor {sorted(motor[llave][campo])}"
                )
    return not diffs, diffs


class GoldEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    drawing_id: str
    source: str
    files: dict[str, str]
    status: Literal["baseline", "partial", "verified"]
    captured_at: datetime
    labels: dict[str, list[str]] = Field(default_factory=dict)
    confirmed: list[str] = Field(default_factory=list)
    excluded: list[str] = Field(default_factory=list)
    baseline_f1: dict[str, float] = Field(default_factory=dict)
    money: MoneyExpectation | None = None
    estructura: EstructuraExpectation | None = None
    notes: str = ""


class EntryResult(BaseModel):
    drawing_id: str
    status: str
    available: bool
    fingerprint_matches: bool | None = None
    scores: list[TypeScore] = Field(default_factory=list)
    confirmed_missing: list[str] = Field(default_factory=list)
    excluded_present: list[str] = Field(default_factory=list)
    money_scores: list[MoneyScore] = Field(default_factory=list)
    direct_cost_expected: float | None = None
    direct_cost_actual: float | None = None
    direct_cost_passed: bool | None = None
    concepts_unexpected: list[str] = Field(default_factory=list)
    # Renglones cuyas variantes no suman su cantidad (debe estar vacío).
    variants_unbalanced: list[str] = Field(default_factory=list)
    # La cerca estructural: None si el gold no la tiene; sus diferencias, si las hay.
    estructura_passed: bool | None = None
    estructura_diffs: list[str] = Field(default_factory=list)
    transcripcion_passed: bool | None = None
    transcripcion_diffs: list[str] = Field(default_factory=list)
    passed: bool
    message: str = ""


# ------------------------------------------------------------------ helpers

def _key(detection: Detection) -> str:
    return detection.display_label or detection.label


def fingerprint(project_root: Path) -> dict[str, str]:
    drawings = project_root / "drawings"
    files: dict[str, str] = {}
    for path in sorted(drawings.glob("*")):
        if path.suffix.lower() in DRAWING_SUFFIXES and path.is_file():
            files[path.name] = hashlib.sha256(path.read_bytes()).hexdigest()
    return files


def _active_detections(project_root: Path, settings: Settings) -> list[Detection]:
    control_dir = project_root / settings.processed_dir_name
    pointer = control_dir / "active_run.json"
    artifact_dir = control_dir
    if pointer.exists():
        try:
            candidate = (control_dir / str(read_json(pointer)["artifact_dir"])).resolve()
            if candidate.is_dir():
                artifact_dir = candidate
        except (KeyError, TypeError, OSError, ValueError):
            pass
    path = artifact_dir / "detections.json"
    if not path.exists():
        raise FileNotFoundError(f"No hay detections.json en {artifact_dir}; procesa el proyecto.")
    return [Detection.model_validate(d) for d in read_json(path)]


def _score(
    predicted: list[Detection], labels: dict[str, list[str]], baseline: dict[str, float]
) -> list[TypeScore]:
    by_type: dict[str, Counter[str]] = {}
    for detection in predicted:
        by_type.setdefault(detection.detection_type.value, Counter())[_key(detection)] += 1
    scores = []
    for detection_type in sorted(set(labels) | set(by_type)):
        expected = Counter(labels.get(detection_type, []))
        got = by_type.get(detection_type, Counter())
        tp = sum((expected & got).values())
        fp = sum((got - expected).values())
        fn = sum((expected - got).values())
        precision = tp / (tp + fp) if tp + fp else (1.0 if not expected else 0.0)
        recall = tp / (tp + fn) if tp + fn else 1.0
        f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
        base = baseline.get(detection_type, 0.0)
        scores.append(
            TypeScore(
                detection_type=detection_type,
                expected=sum(expected.values()),
                predicted=sum(got.values()),
                precision=round(precision, 4),
                recall=round(recall, 4),
                f1=round(f1, 4),
                baseline_f1=round(base, 4),
                passed=f1 + 1e-9 >= base,
            )
        )
    return scores


# ------------------------------------------------------------------ capture

def _engine_money(scratch: Path, settings: Settings, detections: list[Detection]) -> CostReport:
    """The presupuesto the pure engine produces for a run: default catalog,
    reference prices, default assumptions — no taller catálogo, no reviews —
    so two runs of the same engine on the same drawing agree to the cent."""
    processed = scratch / settings.processed_dir_name

    def optional(name: str) -> dict | None:
        path = processed / name
        return read_json(path) if path.exists() else None

    units_raw = optional("drawing_units.json") or {}
    units = DrawingUnits.model_validate(units_raw) if units_raw else DrawingUnits(
        unit="drawing_units", source="unknown", confidence=0.0
    )
    views = optional("views.json")
    dims = optional("dimensions.json")
    return generate_cost_report(
        scratch.name,
        detections,
        units,
        CostingConfig(),
        SheetSegmentation.model_validate(views) if views else None,
        DimensionInventory.model_validate(dims) if dims else None,
        schedule_specs=optional("schedules.json"),
        estructura=optional("estructura.json"),
    )


def _leer_procesado(scratch: Path, settings: Settings, name: str) -> dict | None:
    """Un artefacto de la corrida de prueba, leído antes de que se borre."""
    path = scratch / settings.processed_dir_name / name
    return read_json(path) if path.exists() else None


def _fresh_run(
    project_root: Path, settings: Settings
) -> tuple[list[Detection], CostReport, dict | None]:
    """Run the current engine on a scratch copy of the drawings: the
    detections, the pure-engine presupuesto and the run's ``estructura.json``
    (read before the scratch is deleted)."""
    scratch = Path(tempfile.mkdtemp(prefix="klave_gold_")) / project_root.name
    try:
        shutil.copytree(project_root / "drawings", scratch / "drawings")
        detections = run_full_pipeline(
            scratch, settings, record_history=False, perfil_del_taller=False
        ).detections
        report = _engine_money(scratch, settings, detections)
        return detections, report, _leer_procesado(scratch, settings, "estructura.json")
    finally:
        shutil.rmtree(scratch.parent, ignore_errors=True)


def money_from_report(
    report: CostReport, sin_cerca: dict[str, str] | None = None
) -> MoneyExpectation:
    """Capture every line's quantity and the direct cost as the fence, except
    what ``sin_cerca`` excuses (kept with its reason)."""
    sin_cerca = dict(sin_cerca or {})
    concepts = {
        line.concept_code: QuantityExpectation(
            quantity=round(line.quantity, 3), unit=line.unit, source="engine",
            variants={v.key: round(v.quantity, 3) for v in line.variants} or None,
        )
        for line in report.boq.lines
        if line.concept_code not in sin_cerca
    }
    return MoneyExpectation(
        concepts=concepts,
        direct_cost=(
            None if "costo_directo" in sin_cerca else round(report.boq.direct_cost_total, 2)
        ),
        unpriced=sorted(line.concept_code for line in report.boq.lines if line.unpriced),
        sin_cerca=sin_cerca or None,
    )


def _score_variants(code: str, want: QuantityExpectation, line: BoqLine) -> list[MoneyScore]:
    """R171: each recorded variant against the line's variant of that key, with the concept's
    tolerance; a variant the gold never saw, or one it saw that is gone, fails."""
    actual = {v.key: v.quantity for v in line.variants}
    expected = want.variants or {}
    scores: list[MoneyScore] = []
    for key in sorted(set(expected) | set(actual)):
        esperado, real = expected.get(key), actual.get(key)
        if esperado is None or real is None:
            deviation = None
            passed = False
        else:
            deviation = (
                (0.0 if real == 0 else 100.0)
                if esperado == 0
                else abs(real - esperado) / abs(esperado) * 100.0
            )
            passed = deviation <= want.tolerance_pct
        scores.append(MoneyScore(
            concept_code=key, unit=want.unit, expected=esperado if esperado is not None else 0.0,
            actual=round(real, 3) if real is not None else None,
            deviation_pct=round(deviation, 2) if deviation is not None else None,
            tolerance_pct=want.tolerance_pct, source=want.source, passed=passed,
        ))  # fmt: skip
    return scores


def score_money(
    expected: MoneyExpectation, report: CostReport
) -> tuple[list[MoneyScore], bool | None, list[str]]:
    """Per-concept deviation against tolerance, the direct-cost verdict, and
    the concepts the engine now produces that the gold never saw."""
    actual = {line.concept_code: line for line in report.boq.lines}
    scores: list[MoneyScore] = []
    for code, want in sorted(expected.concepts.items()):
        line = actual.get(code)
        if line is None:
            scores.append(MoneyScore(
                concept_code=code, unit=want.unit, expected=want.quantity, actual=None,
                deviation_pct=None, tolerance_pct=want.tolerance_pct, source=want.source,
                passed=False,
            ))
            continue
        if want.quantity == 0:
            deviation = 0.0 if line.quantity == 0 else 100.0
        else:
            deviation = abs(line.quantity - want.quantity) / abs(want.quantity) * 100.0
        scores.append(MoneyScore(
            concept_code=code, unit=want.unit, expected=want.quantity,
            actual=round(line.quantity, 3), deviation_pct=round(deviation, 2),
            tolerance_pct=want.tolerance_pct, source=want.source,
            passed=deviation <= want.tolerance_pct and line.unit.upper() == want.unit.upper(),
        ))
        if want.variants is not None:
            scores.extend(_score_variants(code, want, line))
    cost_passed: bool | None = None
    if expected.direct_cost is not None:
        if expected.direct_cost == 0:
            cost_passed = report.boq.direct_cost_total == 0
        else:
            drift = abs(report.boq.direct_cost_total - expected.direct_cost)
            cost_passed = drift / expected.direct_cost * 100.0 <= expected.direct_cost_tolerance_pct
    excusados = expected.sin_cerca or {}
    unexpected = sorted(
        code for code in actual if code not in expected.concepts and code not in excusados
    )
    return scores, cost_passed, unexpected


def capture(
    project_root: Path,
    drawing_id: str,
    settings: Settings | None = None,
    *,
    fresh: bool = False,
    anterior: GoldEntry | None = None,
) -> GoldEntry:
    """Fold a processed project's detections and reviews into a gold entry.
    With ``fresh`` the labels come from a current-engine run instead of the
    project's stored artifact, so a baseline never lags behind the parser.
    The structural fence is never copied from the engine here (it is captured
    on its own, from raw-verified counts, with ``capture_estructura``). An
    ``anterior`` entry (the same id, recaptured) keeps its notes, its
    ``estructura`` and, in the money, its verified rows, its exclusions and
    its tolerances."""
    settings = settings or get_settings()
    project_root = Path(project_root)
    money: MoneyExpectation | None = None
    if fresh:
        detections, report, _estructura_json = _fresh_run(project_root, settings)
        money = fusionar_dinero(anterior.money if anterior else None, report)
    else:
        detections = _active_detections(project_root, settings)
    reviews = load_reviews(project_root / settings.processed_dir_name)
    excluded = sorted(k for k, r in reviews.detections.items() if r.status == "excluded")
    confirmed = sorted(k for k, r in reviews.detections.items() if r.status == "confirmed")
    excluded_set = set(excluded)

    labels: dict[str, list[str]] = {}
    for detection in detections:
        if _key(detection) in excluded_set:
            continue
        labels.setdefault(detection.detection_type.value, []).append(_key(detection))
    for values in labels.values():
        values.sort()

    if reviews.verification.detections_confirmed_at is not None:
        status: Literal["baseline", "partial", "verified"] = "verified"
    elif reviews.detections:
        status = "partial"
    else:
        status = "baseline"

    # The entry's own starting point: excluded detections the engine still
    # produces lower precision here, which is exactly the debt to pay down.
    baseline = {s.detection_type: s.f1 for s in _score(detections, labels, {})}
    return GoldEntry(
        drawing_id=drawing_id,
        source=str(project_root),
        files=fingerprint(project_root),
        status=status,
        captured_at=datetime.now(UTC),
        labels=labels,
        confirmed=confirmed,
        excluded=excluded,
        baseline_f1=baseline,
        money=money if money is not None else (anterior.money if anterior else None),
        estructura=anterior.estructura if anterior else None,
        notes=anterior.notes if anterior else "",
    )


_VERIFICADAS = ("human", "crudo")


class CambioDeCerca(Exception):
    """Una captura cambiaría un valor que el gold ya cerca: no se escribe sin ``acepto``."""


class SinCaptura(Exception):
    """``--only`` nombra una entrada que no está en el gold, o cuyos planos no están aquí: no se
    capturó nada (un error de dedo no pasa por una captura hecha)."""


def _elegidas(gold_dir: Path, only: str | None) -> list[GoldEntry]:
    """Las entradas a capturar: todas, o la que ``only`` nombra; si no hay tal, ``SinCaptura``.
    Las que no tienen sus planos aquí se dicen y se saltan (con ``only``, ``SinCaptura``)."""
    entradas = [e for e in load_entries(gold_dir) if only is None or e.drawing_id == only]
    if only is not None and not entradas:
        raise SinCaptura(f"ninguna entrada del gold ({gold_dir}) se llama «{only}»")
    con_planos = []
    for entry in entradas:
        if (Path(entry.source) / "drawings").is_dir():
            con_planos.append(entry)
        elif only is not None:
            raise SinCaptura(f"{entry.drawing_id}: sus planos no están en {entry.source}")
        else:
            print(f"{entry.drawing_id}: sin planos en {entry.source}, no se capturó",
                  file=sys.stderr)
    return con_planos


def fusionar_dinero(anterior: MoneyExpectation | None, report: CostReport) -> MoneyExpectation:
    """The engine's money for a run, merged into an entry's money: verified rows (``human``,
    ``crudo``) are kept as they are, excused concepts stay out, and the engine's own rows
    keep their tolerance and note."""
    fresh = money_from_report(report, anterior.sin_cerca if anterior else None)
    if anterior is None:
        return fresh
    for code, want in anterior.concepts.items():
        if want.source in _VERIFICADAS:
            fresh.concepts[code] = want
        elif code in fresh.concepts:
            fresh.concepts[code].tolerance_pct = want.tolerance_pct
            fresh.concepts[code].note = want.note
    fresh.direct_cost_tolerance_pct = anterior.direct_cost_tolerance_pct
    return fresh


def _plano_de_dinero(m: MoneyExpectation | None) -> dict[str, Any]:
    if m is None:
        return {}
    plano: dict[str, Any] = {}
    for code, q in m.concepts.items():
        plano[f"{code}.cantidad"] = (q.quantity, q.unit.upper())
        plano[f"{code}.variantes"] = tuple(sorted((q.variants or {}).items()))
    if m.direct_cost is not None:
        plano["costo_directo"] = m.direct_cost
    return plano


def _plano_de_estructura(e: EstructuraExpectation | None) -> dict[str, Any]:
    if e is None:
        return {}
    plano: dict[str, Any] = {}
    for familia, campos in e.por_familia.items():
        for campo, n in campos.items():
            plano[f"por_familia.{familia}.{campo}"] = n
    for familia, hojas in e.por_hoja.items():
        for hoja, n in hojas.items():
            plano[f"por_hoja.{familia}.{hoja}"] = n
    for clave, n in e.verificaciones.items():
        plano[f"verificaciones.{clave}"] = n
    for clave, ids in e.hallazgos.items():
        plano[f"hallazgos.{clave}"] = tuple(ids)
    return plano


def _excusado_en_dinero(llave: str, sin_cerca: dict[str, str]) -> bool:
    return (llave == "costo_directo" and "costo_directo" in sin_cerca) or (
        llave.rsplit(".", 1)[0] in sin_cerca
    )


def _excusado_en_estructura(llave: str, sin_cerca: dict[str, str]) -> bool:
    tipo, _, resto = llave.partition(".")
    if tipo in ("por_familia", "por_hoja"):
        familia = resto.split(".", 1)[0]
        campo = "colocaciones" if tipo == "por_hoja" else resto.split(".", 1)[1]
        return (
            f"por_familia.{familia}" in sin_cerca or f"por_familia.{familia}.{campo}" in sin_cerca
        )
    numero = resto.partition("/")[0]
    return f"verificaciones.{numero}" in sin_cerca or f"verificaciones.{resto}" in sin_cerca


def cambios_de_cerca(
    antes: dict[str, Any], despues: dict[str, Any], habia_cerca: bool, excusado: Any
) -> tuple[list[str], list[str]]:
    """Todo lo que cambia entre dos cercas aplanadas, y cuáles de esos cambios tocan lo que la
    de antes cercaba: un valor que tenía, o uno nuevo donde antes se exigía cero (no excusado)."""
    cambios: list[str] = []
    cercados: list[str] = []
    for llave in sorted(set(antes) | set(despues)):
        a, d = antes.get(llave), despues.get(llave)
        if a == d:
            continue
        texto = f"{llave}: {a!r} → {d!r}"
        cambios.append(texto)
        if llave in antes or (habia_cerca and not excusado(llave)):
            cercados.append(texto)
    return cambios, cercados


def _aplicar(nombre: str, cambios: list[str], cercados: list[str], acepto: bool) -> None:
    for c in cambios:
        print(f"{nombre}: {c}")
    if cercados and not acepto:
        raise CambioDeCerca(
            f"{nombre}: la captura cambia {len(cercados)} valores cercados; revísalos contra el "
            "plano y vuelve a capturar con --acepto (y di por qué en la entrada)"
        )


def capture_money(
    gold_dir: Path = GOLD_DIR,
    only: str | None = None,
    settings: Settings | None = None,
    *,
    acepto: bool = False,
) -> list[Path]:
    """Fresh engine run per entry; its quantities and direct cost become the
    entry's money fence. Verified rows (``human``, ``crudo``) and exclusions
    are kept: only the engine's own rows are refreshed. Every change is
    printed; one that touches a fenced value is refused unless ``acepto``. An
    ``only`` that names no entry here (or one without its drawings) raises
    ``SinCaptura``."""
    settings = settings or get_settings()
    saved: list[Path] = []
    for entry in _elegidas(gold_dir, only):
        _detections, report, _estructura = _fresh_run(Path(entry.source), settings)
        fresh = fusionar_dinero(entry.money, report)
        sin = (entry.money.sin_cerca if entry.money else None) or {}
        cambios, cercados = cambios_de_cerca(
            _plano_de_dinero(entry.money), _plano_de_dinero(fresh), entry.money is not None,
            lambda llave, sin=sin: _excusado_en_dinero(llave, sin),
        )
        _aplicar(f"{entry.drawing_id} (dinero)", cambios, cercados, acepto)
        entry.money = fresh
        saved.append(save_entry(entry, gold_dir))
    return saved


def capture_estructura(
    gold_dir: Path, only: str, settings: Settings | None = None, *, acepto: bool = False
) -> list[Path]:
    """Fresh engine run for the entry named in ``only``; its counts (with their sheets and
    their findings) become the fence, without what the entry's ``sin_cerca`` excuses (kept
    with its reasons) and keeping its ``transcripcion``. Only for counts verified against the
    raw drawing: say which and how in the entry's notes. Every change is printed; one that
    touches a fenced value (the old fence would fail on this run) is refused unless
    ``acepto``. An entry with no ``estructura`` yet is refused too unless ``acepto`` (R251):
    seed it first with what it excuses (its ``sin_cerca``), or the whole engine reading
    becomes the fence."""
    settings = settings or get_settings()
    saved: list[Path] = []
    for entry in _elegidas(gold_dir, only):
        if entry.estructura is None and not acepto:
            raise CambioDeCerca(
                f"{entry.drawing_id} no tiene cerca estructural: siémbrala con lo que excusa "
                "(sin_cerca, cada cosa con su razón) o, si toda la lectura del motor se verificó "
                "contra el plano, captura con --acepto"
            )
        _detections, _report, estructura_json = _fresh_run(Path(entry.source), settings)
        if estructura_json is None:
            raise RuntimeError(f"{entry.drawing_id}: la corrida no escribió estructura.json")
        anterior = entry.estructura
        fresh = estructura_from_json(estructura_json, anterior.sin_cerca if anterior else None)
        fresh.transcripcion = anterior.transcripcion if anterior else None
        sin = (anterior.sin_cerca if anterior else None) or {}
        cambios, cercados = cambios_de_cerca(
            _plano_de_estructura(anterior), _plano_de_estructura(fresh), anterior is not None,
            lambda llave, sin=sin: _excusado_en_estructura(llave, sin),
        )
        _aplicar(f"{entry.drawing_id} (estructura)", cambios, cercados, acepto)
        entry.estructura = fresh
        saved.append(save_entry(entry, gold_dir))
    return saved


def save_entry(entry: GoldEntry, gold_dir: Path = GOLD_DIR) -> Path:
    gold_dir.mkdir(parents=True, exist_ok=True)
    path = gold_dir / f"{entry.drawing_id}.json"
    # A concept without variants carries none (R171): no ``null`` in the gold files.
    write_json(path, entry.model_dump(mode="json", exclude_none=True))
    return path


def load_entries(gold_dir: Path = GOLD_DIR) -> list[GoldEntry]:
    if not gold_dir.exists():
        return []
    return [GoldEntry.model_validate(read_json(p)) for p in sorted(gold_dir.glob("*.json"))]


# --------------------------------------------------------------------- run

def evaluate_entry(entry: GoldEntry, settings: Settings | None = None) -> EntryResult:
    """Re-run the pipeline on a scratch copy of the drawings and score it."""
    settings = settings or get_settings()
    source = Path(entry.source)
    if not (source / "drawings").is_dir():
        return EntryResult(
            drawing_id=entry.drawing_id, status=entry.status, available=False, passed=True,
            message=f"Plano no disponible localmente: {entry.source}",
        )
    matches = fingerprint(source) == entry.files
    scratch = Path(tempfile.mkdtemp(prefix="klave_gold_")) / entry.drawing_id
    estructura_json: dict | None = None
    schedules_json: dict | None = None
    try:
        shutil.copytree(source / "drawings", scratch / "drawings")
        result = run_full_pipeline(scratch, settings, record_history=False, perfil_del_taller=False)
        predicted = result.detections
        report = _engine_money(scratch, settings, predicted) if entry.money else None
        if entry.estructura is not None:
            estructura_json = _leer_procesado(scratch, settings, "estructura.json")
            if entry.estructura.transcripcion is not None:
                schedules_json = _leer_procesado(scratch, settings, "schedules.json")
    finally:
        shutil.rmtree(scratch.parent, ignore_errors=True)

    keys = {_key(d) for d in predicted}
    scores = _score(predicted, entry.labels, entry.baseline_f1)
    confirmed_missing = [c for c in entry.confirmed if c not in keys]
    excluded_present = [x for x in entry.excluded if x in keys]
    if entry.status == "verified":
        passed = all(s.f1 == 1.0 for s in scores) and not confirmed_missing
    else:
        passed = all(s.passed for s in scores) and not confirmed_missing
    money_scores: list[MoneyScore] = []
    cost_passed: bool | None = None
    unexpected: list[str] = []
    cost_actual: float | None = None
    variants_unbalanced: list[str] = []
    if report is not None:
        variants_unbalanced = unbalanced_variants(report)
        passed = passed and not variants_unbalanced
    if entry.money is not None and report is not None:
        money_scores, cost_passed, unexpected = score_money(entry.money, report)
        cost_actual = round(report.boq.direct_cost_total, 2)
        passed = (
            passed and all(m.passed for m in money_scores)
            and cost_passed is not False and not unexpected
        )
    estructura_passed: bool | None = None
    estructura_diffs: list[str] = []
    transcripcion_passed: bool | None = None
    transcripcion_diffs: list[str] = []
    if entry.estructura is not None:
        estructura_passed, estructura_diffs = score_estructura(entry.estructura, estructura_json)
        passed = passed and estructura_passed
        if entry.estructura.transcripcion is not None:
            transcripcion_passed, transcripcion_diffs = score_transcripcion(
                Path(entry.estructura.transcripcion), schedules_json
            )
            passed = passed and transcripcion_passed
    message = "" if matches else "El plano cambió desde la captura; recaptura el gold."
    return EntryResult(
        drawing_id=entry.drawing_id,
        status=entry.status,
        available=True,
        fingerprint_matches=matches,
        scores=scores,
        confirmed_missing=confirmed_missing,
        excluded_present=excluded_present,
        money_scores=money_scores,
        direct_cost_expected=entry.money.direct_cost if entry.money else None,
        direct_cost_actual=cost_actual,
        direct_cost_passed=cost_passed,
        concepts_unexpected=unexpected,
        variants_unbalanced=variants_unbalanced,
        estructura_passed=estructura_passed,
        estructura_diffs=estructura_diffs,
        transcripcion_passed=transcripcion_passed,
        transcripcion_diffs=transcripcion_diffs,
        passed=passed,
        message=message,
    )


def unbalanced_variants(report: CostReport) -> list[str]:
    """Renglones cuyas variantes no suman exactamente su cantidad: las
    variantes reparten el renglón, nunca lo cambian."""
    bad = []
    for line in report.boq.lines:
        if not line.variants:
            continue
        total = sum(v.quantity for v in line.variants)
        if abs(total - line.quantity) > 1e-6 * max(1.0, abs(line.quantity)):
            bad.append(f"{line.concept_code}: Σ variantes {total:.6f} ≠ {line.quantity:.6f}")
    return bad


def run(
    gold_dir: Path = GOLD_DIR,
    only: str | None = None,
    settings: Settings | None = None,
    reports_dir: Path | None = None,
) -> dict:
    settings = settings or get_settings()
    entries = [e for e in load_entries(gold_dir) if only is None or e.drawing_id == only]
    results = [evaluate_entry(entry, settings) for entry in entries]
    status = (
        "FAIL" if any(r.available and not r.passed for r in results)
        else "PENDING" if not results or any(not r.available for r in results)
        else "PASS"
    )
    summary = {
        "evaluated_at": datetime.now(UTC).isoformat(),
        "entries": [r.model_dump() for r in results],
        "all_passed": status == "PASS",
        "status": status,
        "unavailable": [r.drawing_id for r in results if not r.available],
    }
    out = reports_dir or settings.reports_dir
    write_json(out / "gold_eval.json", summary)
    write_text(out / "gold_eval.md", render_markdown(summary))
    return summary


def render_markdown(summary: dict) -> str:
    status = summary.get("status", "PASS" if summary["all_passed"] else "FAIL")
    lines = [
        "# Gold set",
        "",
        f"Overall: {status} — {summary['evaluated_at']}",
        "",
    ]
    for entry in summary["entries"]:
        lines.append(f"## {entry['drawing_id']} ({entry['status']})")
        lines.append("")
        if not entry["available"]:
            lines += [f"_{entry['message']}_", ""]
            continue
        if entry["message"]:
            lines += [f"**{entry['message']}**", ""]
        lines += ["| Tipo | Esperado | Predicho | P | R | F1 | F1 base | OK |",
                  "|---|---|---|---|---|---|---|---|"]
        for s in entry["scores"]:
            ok = "sí" if s["passed"] else "NO"
            lines.append(
                f"| {s['detection_type']} | {s['expected']} | {s['predicted']} | {s['precision']} "
                f"| {s['recall']} | {s['f1']} | {s['baseline_f1']} | {ok} |"
            )
        if entry["confirmed_missing"]:
            missing = ", ".join(entry["confirmed_missing"])
            lines += ["", f"Confirmadas que ya no aparecen: {missing}"]
        if entry["excluded_present"]:
            lines += ["", "Excluidas que el motor sigue produciendo: "
                      + ", ".join(entry["excluded_present"])]
        if entry.get("money_scores"):
            lines += ["", "### Cantidades y dinero", "",
                      "| Concepto | Unidad | Esperado | Motor | Desv. % | Tol. % | Fuente | OK |",
                      "|---|---|---|---|---|---|---|---|"]
            for m in entry["money_scores"]:
                actual = "—" if m["actual"] is None else f"{m['actual']:g}"
                dev = "—" if m["deviation_pct"] is None else f"{m['deviation_pct']:g}"
                ok = "sí" if m["passed"] else "NO"
                lines.append(
                    f"| {m['concept_code']} | {m['unit']} | {m['expected']:g} | {actual} | {dev} "
                    f"| {m['tolerance_pct']:g} | {m['source']} | {ok} |"
                )
            if entry.get("direct_cost_expected") is not None:
                verdict = "sí" if entry.get("direct_cost_passed") else "NO"
                lines += ["", f"Costo directo: esperado ${entry['direct_cost_expected']:,.2f}, "
                          f"motor ${entry.get('direct_cost_actual') or 0:,.2f} — OK: {verdict}"]
            if entry.get("concepts_unexpected"):
                lines += ["", "Conceptos nuevos que el gold no conoce: "
                          + ", ".join(entry["concepts_unexpected"])]
        if entry.get("variants_unbalanced"):
            lines += ["", "Variantes que no suman su renglón: "
                      + "; ".join(entry["variants_unbalanced"])]
        if entry.get("estructura_passed") is not None:
            verdict = "sí" if entry["estructura_passed"] else "NO"
            lines += ["", "### Lectura estructural", "", f"Cerca exacta — OK: {verdict}"]
            lines += [f"- {d}" for d in entry.get("estructura_diffs", [])]
        if entry.get("transcripcion_passed") is not None:
            verdict = "sí" if entry["transcripcion_passed"] else "NO"
            lines += ["", f"Transcripción a mano — OK: {verdict}"]
            lines += [f"- {d}" for d in entry.get("transcripcion_diffs", [])]
        lines.append("")
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="klave-gold")
    sub = parser.add_subparsers(dest="command", required=True)
    cap = sub.add_parser("capture", help="capture a processed project into the gold set")
    cap.add_argument("project_root")
    cap.add_argument("--id", required=True, dest="drawing_id")
    cap.add_argument("--gold", default=str(GOLD_DIR))
    cap.add_argument(
        "--fresh", action="store_true",
        help="label from a current-engine run instead of the stored artifact",
    )
    acepto = "write even if a fenced value changes (after checking it against the drawing)"
    cap.add_argument("--acepto", action="store_true", help="recapture an existing id: " + acepto)
    money = sub.add_parser(
        "money", help="capture the engine's quantities and direct cost into existing entries"
    )
    money.add_argument("--gold", default=str(GOLD_DIR))
    money.add_argument("--only")
    money.add_argument("--acepto", action="store_true", help=acepto)
    est = sub.add_parser(
        "estructura",
        help="capture the structural reading's counts into one entry (raw-verified only)",
    )
    est.add_argument("--gold", default=str(GOLD_DIR))
    est.add_argument("--only", required=True)
    est.add_argument("--acepto", action="store_true", help=acepto)
    runner = sub.add_parser("run", help="evaluate the engine against the gold set")
    runner.add_argument("--gold", default=str(GOLD_DIR))
    runner.add_argument("--only")
    args = parser.parse_args(argv)

    try:
        if args.command == "capture":
            destino = Path(args.gold) / f"{args.drawing_id}.json"
            anterior = GoldEntry.model_validate(read_json(destino)) if destino.exists() else None
            if anterior is not None and not args.acepto:
                raise CambioDeCerca(
                    f"{args.drawing_id} ya está en el gold: recapturarla reemplaza sus etiquetas y "
                    "su dinero (conserva sus notas, su estructura y lo verificado); usa --acepto"
                )
            entry = capture(
                Path(args.project_root), args.drawing_id, fresh=args.fresh, anterior=anterior
            )
            if anterior is not None:
                cambios, _ = cambios_de_cerca(
                    _plano_de_dinero(anterior.money), _plano_de_dinero(entry.money), True,
                    lambda _llave: False,
                )
                for c in cambios:
                    print(f"{entry.drawing_id} (dinero): {c}")
            path = save_entry(entry, Path(args.gold))
            counts = {k: len(v) for k, v in entry.labels.items()}
            print(f"{entry.drawing_id}: {entry.status} — {counts} → {path}")
            return 0
        if args.command == "money":
            for path in capture_money(Path(args.gold), only=args.only, acepto=args.acepto):
                print(f"money → {path}")
            return 0
        if args.command == "estructura":
            for path in capture_estructura(Path(args.gold), args.only, acepto=args.acepto):
                print(f"estructura → {path}")
            return 0
    except (CambioDeCerca, SinCaptura) as exc:
        print(f"NO SE ESCRIBIÓ: {exc}", file=sys.stderr)
        return 2
    summary = run(Path(args.gold), only=args.only)
    print(render_markdown(summary))
    if summary["status"] == "PENDING":
        return 2
    return 0 if summary["all_passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
