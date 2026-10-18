"""Acero de refuerzo (kg) derived from what the BoQ already counted.

The sheet states armados per mark and family (``4#3 E#2@20``); the BoQ knows
how many castillos, how many metres of wall and trabe, and which zapatas.
This stage multiplies the two into kilograms with every assumption written
down: bar weights per número (NMX-B-506), anchorage, hooks, cover, waste,
and a default armado only where the sheet says nothing — and says so.

With the structural model (``estructura``: its rules and elements) castillos,
columnas, trabes and contratrabes are weighed element by element from their
structured armado (``estructura.acero``: every bar group, every stirrup set by
shape, hooks, cover by family and sheet, stirrups laid out by zone). Whatever
cannot be weighed is listed mark by mark with its reason («acero por leer»,
R148a): a concept never vanishes silently.

``estructura.acero`` weighs with ``BAR_KG_PER_M`` from here, so this module
imports it only inside the functions that use it (R17: no import cycle).
"""

import math
import re
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from pydantic import BaseModel, Field

from klave_engine.costing.models import BillOfQuantities, BoqLine, QuantityKind
from klave_engine.detection.results import Detection
from klave_engine.detection.views import SheetSegmentation
from klave_engine.estructura.armado import Armado, Zona, parsear_armado, texto_estribos

if TYPE_CHECKING:
    from klave_engine.estructura.elementos import Elemento
    from klave_engine.estructura.reglas import Reglas

# kg/m por número de varilla (diámetro en octavos de pulgada).
BAR_KG_PER_M: dict[str, float] = {
    "2": 0.248, "2.5": 0.388, "3": 0.560, "4": 0.994, "5": 1.552, "6": 2.235,
    "7": 3.042, "8": 3.973, "10": 6.404, "12": 9.021,
}

_REBAR_RE = re.compile(r"^(\d{1,2})#(\d(?:\.5)?)$")
_SPACING_RE = re.compile(r"^#(\d(?:\.5)?)@(\d{1,3})$")

CODE_CASTILLOS = "ACE-001"
CODE_DALAS = "ACE-002"
CODE_ZAPATAS = "ACE-003"
CODE_TRABES = "ACE-004"
CODE_MALLA = "ACE-005"
CODE_LOSAS = "ACE-006"
_SLAB_LAYER_RE = re.compile(
    r"(?P<layer>L\.?\s*[SI]\.?|LECHO\s+(?:SUP|INF)\w*)?\s*#\s*(?P<bar>\d(?:\.5)?)\s*@\s*(?P<sp>\d{1,3})"
    r"\s*(?P<both>A\s*/\s*S|A\.?S\.?|AMBOS\s+SENTIDOS)?",
    re.I,
)


class SteelAssumptions(BaseModel):
    cover_m: float = 0.025
    hook_m: float = 0.075  # per stirrup, total for both hooks
    anchorage_m: float = 0.40  # longitudinal bars beyond the element
    waste_pct: float = 5.0
    default_castillo: tuple[str, str, tuple[int, int]] = ("4#3", "#2@20", (15, 20))
    default_dala: tuple[str, str, tuple[int, int]] = ("4#3", "#2@20", (15, 20))
    default_zapata_mesh: str = "#4@20"
    malla_overlap_factor: float = 1.10
    wall_height_m: float = 2.7


class SteelLine(BaseModel):
    concept_code: str
    quantity: float
    unit: str
    source_detections: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


class SteelReport(BaseModel):
    lines: list[SteelLine] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


def parse_rebar(text: str | None) -> tuple[int, str] | None:
    if not text:
        return None
    m = _REBAR_RE.match(text.replace(" ", ""))
    return (int(m.group(1)), m.group(2)) if m and m.group(2) in BAR_KG_PER_M else None


def parse_spacing(text: str | None) -> tuple[str, float] | None:
    """'#2@20' → (número, spacing in metres)."""
    if not text:
        return None
    m = _SPACING_RE.match(text.replace(" ", "").upper().replace("E", ""))
    if not m or m.group(1) not in BAR_KG_PER_M:
        return None
    return m.group(1), int(m.group(2)) / 100.0


def _spec_for(specs: dict | None, mark: str, family: str) -> tuple[dict | None, str]:
    """The sheet's spec for a mark, its family, or nothing — and which."""
    if not specs:
        return None, "none"
    by_mark = specs.get("by_mark") or {}
    by_family = specs.get("by_family") or {}
    if mark.upper() in by_mark:
        return by_mark[mark.upper()], "mark"
    if family in by_family:
        return by_family[family], "family"
    return None, "none"


def slab_rebar_kg_per_m2(label: str | None) -> tuple[float, str] | None:
    """Rebar per m² from a slab label: 'LS #4@20 A/S LI #4@20 A/S' is two
    layers, each both ways; '#4@20 A/S' on a 'DOBLEMENTE ARMADA' slab is two
    layers too. Returns (kg/m², how it was read) or None when the label
    carries no armado."""
    if not label:
        return None
    text = " ".join(label.split()).upper()
    matches = list(_SLAB_LAYER_RE.finditer(text))
    if not matches:
        return None
    total = 0.0
    parts: list[str] = []
    explicit_layers = any(m.group("layer") for m in matches)
    for m in matches:
        bar = m.group("bar")
        if bar not in BAR_KG_PER_M:
            continue
        spacing_m = int(m.group("sp")) / 100.0
        if spacing_m <= 0:
            continue
        directions = 2 if m.group("both") else 1
        kg = BAR_KG_PER_M[bar] * (1.0 / spacing_m) * directions
        total += kg
        parts.append(f"#{bar}@{m.group('sp')}{' a/s' if directions == 2 else ''}")
    if total <= 0:
        return None
    if not explicit_layers and "DOBLEMENTE" in text:
        total *= 2
        parts.append("×2 lechos (doblemente armada)")
    return round(total, 3), ", ".join(parts)


@dataclass
class _Estribo:
    """El juego de estribos que el camino sin estructura cuenta: número, cuántas piezas por juego
    y su separación uniforme, o sus zonas (un texto canónico «2E#3 EXT@10 CENTRO@20»)."""

    numero: str
    separacion_m: float | None
    piezas: int = 1
    zonas: list[Zona] = field(default_factory=list)
    texto: str = ""


@dataclass
class _Leido:
    """Lo que el camino sin estructura lee de una especificación: los grupos de varillas y el
    primer juego de estribos; ``otros_juegos``, los que ese camino no cuenta (dicho en la nota)."""

    grupos: list[tuple[int, str]] = field(default_factory=list)
    estribo: _Estribo | None = None
    otros_juegos: list[str] = field(default_factory=list)


def _texto_varillas(grupos: list[tuple[int, str]]) -> str:
    return "+".join(f"{c}#{n}" for c, n in grupos)


def _texto_estribo(estribo: _Estribo | None) -> str:
    if estribo is None:
        return ""
    if estribo.texto:
        return f" {estribo.texto}"
    cuenta = str(estribo.piezas) if estribo.piezas > 1 else ""
    return f" {cuenta}E#{estribo.numero}@{(estribo.separacion_m or 0) * 100:.0f}"


def _leer_spec(spec: dict | None, familia: str) -> _Leido:
    """Las varillas y el primer juego de estribos de una especificación (``rebar``, ``stirrups``).

    Los textos de siempre («4#3», «#2@20», «E#3@15») se leen como siempre; uno que
    ``parse_rebar``/``parse_spacing`` no entienden (los canónicos «4#5+2#4», «2E#3@15»,
    «EYG#3@15», «4#3,E#2@20») se lee con ``parsear_armado`` —un «#n@s» suelto lleva antes su
    «E», como lo guardaban las corridas viejas—: todos los grupos de varillas y el primer juego
    de estribos. Nunca se pierde callado un armado que antes se leía (Tarea 7, R62)."""
    leido = _Leido()
    if not spec:
        return leido
    rebar = (spec.get("rebar") or "").strip()
    stirrups = (spec.get("stirrups") or "").strip()
    simple = parse_rebar(rebar) if rebar else None
    if simple is not None:
        leido.grupos = [simple]
    estribo_simple = parse_spacing(stirrups) if stirrups else None
    if estribo_simple is not None:
        leido.estribo = _Estribo(numero=estribo_simple[0], separacion_m=estribo_simple[1])
    textos = []
    if rebar and simple is None:
        textos.append(rebar)
    if stirrups and estribo_simple is None:
        textos.append("E" + stirrups if stirrups.startswith("#") else stirrups)
    if not textos:
        return leido
    armado = parsear_armado(textos, familia)
    if not leido.grupos:
        leido.grupos = [
            (g.cantidad, g.numero) for g in armado.longitudinales if g.numero in BAR_KG_PER_M
        ]
    juegos = [j for j in armado.estribos if j.numero in BAR_KG_PER_M]
    if leido.estribo is None and juegos:
        primero = juegos[0]
        zonas = list(primero.zonas)
        if [z.tramo for z in zonas] == ["todo"] and zonas[0].separacion_m:
            leido.estribo = _Estribo(
                numero=primero.numero, separacion_m=zonas[0].separacion_m,
                piezas=primero.cantidad,
            )
        elif zonas and all(z.separacion_m for z in zonas):
            leido.estribo = _Estribo(
                numero=primero.numero, separacion_m=None, piezas=primero.cantidad, zonas=zonas,
                texto=texto_estribos(Armado(estribos=[primero])),
            )
        leido.otros_juegos = [
            texto_estribos(Armado(estribos=[j])) for j in juegos[1 if leido.estribo else 0 :]
        ]
    return leido


def _leer_malla(spec: dict | None) -> tuple[str, float] | None:
    """La parrilla de una zapata: «#4@20» como siempre; un texto canónico («#4@20 A/S») con
    ``parsear_armado``, la primera malla."""
    mesh = ((spec or {}).get("mesh") or "").strip()
    if not mesh:
        return None
    simple = parse_spacing(mesh)
    if simple is not None:
        return simple
    parrillas = parsear_armado([mesh], "zapata").parrillas
    if parrillas and parrillas[0].numero in BAR_KG_PER_M:
        return parrillas[0].numero, parrillas[0].separacion_m
    return None


def _linear_element_kg(
    length_m: float, rebar: list[tuple[int, str]], stirrups: _Estribo | None,
    section_cm: tuple[float, float], a: SteelAssumptions, *, anchorage: bool,
) -> tuple[float, float]:
    """(longitudinal kg, stirrup kg) for one prismatic element: every bar group, and the first
    stirrup set as perimeters (one per piece). Zoned stirrups are laid out by zone
    (``estructura.acero.posiciones``, ends supuesto by NTC) — strings the old reader never read."""
    bar_length = length_m + (a.anchorage_m if anchorage else 0.0)
    longitudinal = sum(count * bar_length * BAR_KG_PER_M[number] for count, number in rebar)
    stirrup_kg = 0.0
    if stirrups is not None:
        w, h = section_cm[0] / 100.0, section_cm[1] / 100.0
        perimeter = 2 * ((w - 2 * a.cover_m) + (h - 2 * a.cover_m)) + a.hook_m
        if stirrups.zonas:
            from klave_engine.estructura.acero import extremos_supuesto_m, posiciones

            n_stirrups = posiciones(
                length_m, stirrups.zonas, None, extremos_supuesto_m(w, h, length_m)
            )
        else:
            spacing = stirrups.separacion_m or 0.0
            n_stirrups = math.floor(length_m / spacing) + 1 if spacing > 0 else 0
        stirrup_kg = stirrups.piezas * n_stirrups * perimeter * BAR_KG_PER_M[stirrups.numero]
    return longitudinal, stirrup_kg


def _pzas(n: int) -> str:
    return f"{n} pza" if n == 1 else f"{n} pzas"


class _Modelo:
    """El modelo estructural que lee la etapa de acero (R6: sólo ``estructura["reglas"]``, un
    volcado de ``Reglas``, y ``estructura["elementos"]``, volcados de ``Elemento``): los elementos
    por detección y las reglas de cada hoja, calculadas una vez."""

    def __init__(self, estructura: dict) -> None:
        from klave_engine.estructura.elementos import Elemento
        from klave_engine.estructura.reglas import Reglas

        self.reglas = Reglas.model_validate(estructura["reglas"])
        elementos = [Elemento.model_validate(e) for e in estructura["elementos"]]
        self.elementos = elementos
        self.por_deteccion = {e.detection_id: e for e in elementos}
        self._por_hoja: dict[str, Reglas] = {}

    def reglas_de(self, hoja: str) -> "Reglas":
        """Las reglas como las resuelve ``hoja`` (``Reglas.para``), una vez por hoja."""
        if hoja not in self._por_hoja:
            self._por_hoja[hoja] = self.reglas.para(hoja)
        return self._por_hoja[hoja]

    def fy(self, numero: str) -> float | None:
        dato = self.reglas.fy_kg_cm2.get(numero)
        valor = dato.valor if dato is not None else None
        return float(valor) if isinstance(valor, int | float) else None


@dataclass
class _Cuenta:
    """Lo que la etapa junta de los elementos de una línea de acero."""

    kg_por_numero: dict[str, float] = field(default_factory=dict)
    total: float = 0.0
    grupos: dict[tuple, list] = field(default_factory=dict)  # nota por marca → [pzas, kg]
    supuestos: dict[str, set[str]] = field(default_factory=dict)  # supuesto → marcas
    por_confirmar: dict[tuple[str, str], list[str]] = field(default_factory=dict)
    por_leer: dict[tuple[str, tuple[str, ...], bool], list[str]] = field(default_factory=dict)
    calculados: int = 0
    elementos: int = 0
    sin_fila: dict[str, set[str]] = field(default_factory=dict)  # aviso de tabla → marcas

    def sumar(self, kg: dict[str, float]) -> None:
        for numero, valor in kg.items():
            self.kg_por_numero[numero] = self.kg_por_numero.get(numero, 0.0) + valor
            self.total += valor


def _del_modelo(cuenta: _Cuenta, e: "Elemento", modelo: _Modelo, a: SteelAssumptions) -> bool:
    """El acero de un elemento con su armado estructurado, en ``cuenta``. Falso si el elemento no
    tiene acero (``sin_acero``): el llamador decide qué hace con él."""
    from klave_engine.estructura.acero import acero_elemento, texto_del_armado

    cuenta.elementos += 1
    marca = e.marca or "sin marca"
    acero = acero_elemento(e, modelo.reglas_de(e.hoja), a.anchorage_m)
    if acero is None:
        return False
    cuenta.calculados += 1
    cuenta.sumar(acero.kg_por_numero)
    seccion = e.seccion_cm
    valor = seccion.valor if seccion is not None else None
    if isinstance(valor, list | tuple):
        lados = "x".join(f"{float(v):g}" for v in valor) + " cm"
    elif isinstance(valor, dict) and "area_cm2" in valor:
        lados = f"no rectangular de {float(valor['area_cm2']):g} cm²"
    else:
        lados = repr(valor)
    fuente = seccion.fuente if seccion is not None else "?"
    clave = (marca, texto_del_armado(e), lados, fuente)
    pzas_kg = cuenta.grupos.setdefault(clave, [0, 0.0])
    pzas_kg[0] += 1
    pzas_kg[1] += acero.total_kg()
    for supuesto in acero.supuestos:
        if supuesto.startswith("tabla de varillas: "):
            cuenta.sin_fila.setdefault(supuesto.removeprefix("tabla de varillas: "), set()).add(
                marca
            )
        else:
            cuenta.supuestos.setdefault(supuesto, set()).add(marca)
    for duda in acero.por_confirmar:
        cuenta.por_confirmar.setdefault((marca, duda), []).append(e.hoja)
    if acero.por_leer:
        cuenta.por_leer.setdefault((marca, tuple(acero.por_leer), True), []).append(e.hoja)
    return True


def _sin_acero_en(cuenta: _Cuenta, e: "Elemento", extra: tuple[str, ...] = ()) -> None:
    """El elemento sin acero desde su armado, en «acero por leer» con sus motivos."""
    from klave_engine.estructura.acero import motivos_por_leer

    marca = e.marca or "sin marca"
    cuenta.por_leer.setdefault((marca, (*motivos_por_leer(e), *extra), False), []).append(e.hoja)


def _lados_cm(e: "Elemento") -> tuple[float, float] | None:
    seccion = e.seccion_cm
    if seccion is None or not isinstance(seccion.valor, list | tuple) or len(seccion.valor) != 2:
        return None
    b, h = seccion.valor
    if not all(isinstance(v, int | float) and v > 0 for v in (b, h)):
        return None
    return float(b), float(h)


def _armado_supuesto(
    elementos: list["Elemento"], a: SteelAssumptions, height: float, cuenta: _Cuenta
) -> tuple[float, list[str], list[str]]:
    """Los castillos y columnas del modelo sin acero desde su armado: el camino de antes con el
    armado supuesto (nunca la especificación: la IA que el modelo bloqueó no vuelve por aquí), con
    la sección y la altura de cada elemento si las tiene, y cada uno en «acero por leer» con su
    motivo y el armado que se supuso (R148a). Devuelve (kg sin desperdicio, notas, marcas)."""
    d_rebar, d_stirrup, d_section = a.default_castillo
    default = _leer_spec({"rebar": d_rebar, "stirrups": d_stirrup}, "castillo")
    texto = _texto_varillas(default.grupos) + _texto_estribo(default.estribo)
    total = 0.0
    por_grupo: dict[tuple[str, tuple[float, float], str], list[float]] = {}
    for e in elementos:
        marca = e.marca or "sin marca"
        lados = _lados_cm(e)
        fuente = e.seccion_cm.fuente if lados is not None and e.seccion_cm is not None else ""
        seccion = lados or (float(d_section[0]), float(d_section[1]))
        largo = e.altura_m.valor if e.altura_m is not None else None
        alto = float(largo) if isinstance(largo, int | float) and largo > 0 else height
        long_kg, stir_kg = _linear_element_kg(
            alto, default.grupos, default.estribo, seccion, a, anchorage=True
        )
        total += long_kg + stir_kg
        grupo = por_grupo.setdefault((marca, seccion, fuente), [0, 0.0])
        grupo[0] += 1
        grupo[1] += long_kg + stir_kg
        usada = f"{seccion[0]:g}x{seccion[1]:g} cm" + ("" if lados else " supuesta")
        _sin_acero_en(cuenta, e, (f"se usó el armado supuesto {texto.strip()} ({usada})",))
    notas = [
        f"{marca}: {int(n)} pzas × {texto.strip()} sección {b:g}x{h:g} cm (supuesto: armado; "
        f"sección {fuente or 'supuesta'}) = {kg:,.2f} kg"
        for (marca, (b, h), fuente), (n, kg) in sorted(por_grupo.items())
    ]
    marcas = sorted({m for m, _, _ in por_grupo})
    return total, notas, marcas


def _notas_del_modelo(cuenta: _Cuenta, modelo: _Modelo, waste: float) -> list[str]:
    notas = [
        f"{marca}: {pzas} pzas × {texto} sección {lados} ({fuente}) = {kg:,.2f} kg"
        for (marca, texto, lados, fuente), (pzas, kg) in sorted(cuenta.grupos.items())
    ]
    if cuenta.kg_por_numero:
        partes = [
            f"#{n} {kg * waste:,.2f} kg"
            for n, kg in sorted(cuenta.kg_por_numero.items(), key=lambda x: float(x[0]))
            if n != "2"
        ]
        texto = "Kg por número (con desperdicio): " + ("; ".join(partes) or "—")
        if "2" in cuenta.kg_por_numero:
            fy = modelo.fy("2")
            texto += (
                f"; #2 aparte (alambrón, fy {fy:g} kg/cm²"
                if fy is not None
                else "; #2 aparte (alambrón, fy sin declarar"
            ) + f"): {cuenta.kg_por_numero['2'] * waste:,.2f} kg"
        notas.append(texto)
    for supuesto, marcas in cuenta.supuestos.items():
        notas.append(f"{supuesto} — {', '.join(sorted(marcas))}")
    for (marca, duda), hojas in sorted(cuenta.por_confirmar.items()):
        notas.append(f"{marca} ({_pzas(len(hojas))}): {duda}")
    return notas


def _hojas(hojas: list[str]) -> str:
    return ", ".join(sorted(set(h for h in hojas if h))) or "sin hoja"


def _avisos_del_modelo(cuenta: _Cuenta, nombre: str, consecuencia: str) -> list[str]:
    """«Acero por leer» (R148a): cada marca con su motivo, sin recortar; y lo que se calculó sobre
    datos que hay que confirmar."""
    avisos: list[str] = []
    if cuenta.por_leer:
        partes = []
        for (marca, motivos, parcial), hojas in sorted(cuenta.por_leer.items()):
            cuantas = _pzas(len(hojas)) + (", sólo varillas longitudinales" if parcial else "")
            partes.append(f"{marca} ({cuantas}) en {_hojas(hojas)}: " + "; ".join(motivos))
        avisos.append(
            f"Acero por leer — {nombre}: {cuenta.calculados} de {cuenta.elementos} elementos "
            f"con acero calculado; {consecuencia}: " + " | ".join(partes)
        )
    if cuenta.por_confirmar:
        por_duda: dict[str, list[str]] = {}
        for (marca, duda), hojas in sorted(cuenta.por_confirmar.items()):
            por_duda.setdefault(duda, []).append(f"{marca} ({_pzas(len(hojas))})")
        avisos.append(
            f"Acero de {nombre} calculado sobre datos supuestos o en conflicto (por confirmar): "
            + " | ".join(f"{', '.join(m)}: {d}" for d, m in por_duda.items())
        )
    return avisos


_FAMILIAS_CON_ACERO = ("castillo", "columna", "trabe", "contratrabe")


def _fuera_del_presupuesto(
    modelo: _Modelo, en_lineas: set[str], a: SteelAssumptions, waste: float
) -> str | None:
    """Los castillos, columnas, trabes y contratrabes del modelo que no están en las líneas de
    concreto del presupuesto (la planta de cimentación, que el presupuesto toma como la base de
    las mismas columnas de arriba; una viga sin claro): su acero no se suma, y se dice cuánto
    pesaría o por qué no se puede pesar (R148a)."""
    from klave_engine.estructura.acero import acero_elemento, motivos_por_leer

    pesados: dict[str, list] = {}  # marca → [hojas, kg]
    sin: dict[tuple[str, tuple[str, ...]], list[str]] = {}
    for e in modelo.elementos:
        if e.familia not in _FAMILIAS_CON_ACERO or e.detection_id in en_lineas:
            continue
        marca = e.marca or f"{e.familia} sin marca"
        acero = acero_elemento(e, modelo.reglas_de(e.hoja), a.anchorage_m)
        if acero is None:
            sin.setdefault((marca, tuple(motivos_por_leer(e))), []).append(e.hoja)
            continue
        hojas_kg = pesados.setdefault(marca, [[], 0.0])
        hojas_kg[0].append(e.hoja)
        hojas_kg[1] += acero.total_kg() * waste
    if not pesados and not sin:
        return None
    partes = [
        f"{marca} ({_pzas(len(hojas))}) en {_hojas(hojas)}: {kg:,.1f} kg"
        for marca, (hojas, kg) in sorted(pesados.items())
    ] + [
        f"{marca} ({_pzas(len(hojas))}) en {_hojas(hojas)}, sin acero: " + "; ".join(motivos)
        for (marca, motivos), hojas in sorted(sin.items())
    ]
    total = sum(kg for _, kg in pesados.values())
    cuantos = sum(len(h) for h, _ in pesados.values()) + sum(len(h) for h in sin.values())
    return (
        f"Acero fuera del presupuesto — {cuantos} "
        "castillos, columnas, trabes y contratrabes del modelo estructural no están en las líneas "
        "de concreto (EST-001, EST-002, CIM-008), así que su acero no se suma (acero no "
        f"cuantificado; {total:,.1f} kg con desperdicio en los que se pueden pesar): "
        + " | ".join(partes)
    )


def compute_steel(
    boq: BillOfQuantities,
    detections: list[Detection],
    specs: dict | None,
    segmentation: SheetSegmentation | None,
    meters_factor: float | None,
    column_height_m: float,
    assumptions: SteelAssumptions | None = None,
    estructura: dict | None = None,
) -> SteelReport:
    """El acero de las líneas que el presupuesto ya contó. Con ``estructura`` (el modelo de
    ``estructura``: R6, ``{"reglas", "elementos"}``) castillos, columnas, trabes y contratrabes
    se pesan desde el armado estructurado de cada elemento (``estructura.acero``); sin ella, como
    antes, desde las especificaciones por marca (``specs``), que ahora también se leen en su
    forma canónica. Lo que no se puede pesar se dice, marca por marca («acero por leer», R148a)."""
    a = assumptions or SteelAssumptions()
    report = SteelReport()
    by_id = {d.detection_id: d for d in detections}
    lines = {line.concept_code: line for line in boq.lines}
    waste = 1.0 + a.waste_pct / 100.0
    modelo = _Modelo(estructura) if estructura is not None else None
    sin_fila: dict[str, set[str]] = {}
    # Each castillo is as tall as ITS planta (entrepiso), never the whole
    # building: with declared levels the story heights apply per assignment;
    # without them the assumed column height does. The total height divided
    # by the number of plantas is the fallback when levels exist but do not
    # pair up into stories.
    story_heights = segmentation.story_heights() if segmentation is not None else {}
    assignment = segmentation.assignment if segmentation is not None else {}
    height = column_height_m
    total_height = segmentation.total_height() if segmentation is not None else None
    if not story_heights and total_height and segmentation is not None:
        plantas = max(len(segmentation.superstructure_views()), 1)
        height = total_height / plantas

    # --- castillos / columnas -------------------------------------------
    columns = lines.get("EST-001")
    if columns is not None and columns.source_detections:
        total_long = total_stirrup = 0.0
        groups: dict[str, list[Detection]] = {}
        cuenta = _Cuenta()
        sin_su_acero: list[Elemento] = []
        for det_id in columns.source_detections:
            det = by_id.get(det_id)
            if det is None:
                continue
            elemento = modelo.por_deteccion.get(det_id) if modelo is not None else None
            if elemento is not None and modelo is not None:
                if not _del_modelo(cuenta, elemento, modelo, a):
                    sin_su_acero.append(elemento)
                continue
            groups.setdefault(det.label.strip().upper() or "?", []).append(det)
        notes: list[str] = []
        assumed_marks: list[str] = []
        faltan: dict[str, str] = {}  # marca → lo que el plano no dio (armado, sección)
        for mark, members in sorted(groups.items()):
            family = "castillo" if mark.startswith("K") else "columna"
            spec, origin = _spec_for(specs, mark, family)
            leido = _leer_spec(spec, family)
            rebar = leido.grupos or None
            stirrups = leido.estribo
            section = tuple(spec["section_cm"]) if spec and spec.get("section_cm") else None
            if rebar is None or section is None:
                faltan[mark] = " y ".join(
                    falta
                    for falta, sin in (("armado", rebar is None), ("sección", section is None))
                    if sin
                )
                d_rebar, d_stirrup, d_section = a.default_castillo
                default = _leer_spec({"rebar": d_rebar, "stirrups": d_stirrup}, family)
                rebar = rebar or default.grupos
                stirrups = stirrups or default.estribo
                section = section or d_section
                assumed_marks.append(mark)
            assert rebar is not None and section is not None
            for member in members:
                own_height = story_heights.get(assignment.get(member.detection_id, ""), height)
                long_kg, stir_kg = _linear_element_kg(
                    own_height, rebar, stirrups, (float(section[0]), float(section[1])), a,
                    anchorage=True,
                )
                total_long += long_kg
                total_stirrup += stir_kg
            notes.append(
                f"{mark}: {len(members)} pzas × {_texto_varillas(rebar)}"
                + _texto_estribo(stirrups)
                + f" sección {section[0]}x{section[1]} cm "
                + ("(plano)" if origin != "none" else "(supuesto)")
                + (" (sin elemento en el modelo estructural)" if modelo is not None else "")
            )
            if leido.otros_juegos:
                notes.append(
                    f"{mark}: sólo se cuenta el primer juego de estribos; no se cuentan "
                    + ", ".join(leido.otros_juegos)
                )
        if sin_su_acero:
            supuesto_kg, notas_supuestas, marcas = _armado_supuesto(
                sin_su_acero, a, height, cuenta
            )
            total_long += supuesto_kg
            notes += notas_supuestas
            assumed_marks += marcas
        quantity = (total_long + total_stirrup + cuenta.total) * waste
        if assumed_marks:
            notes.append(
                "Armado supuesto (el plano no lo declara): " + ", ".join(assumed_marks)
            )
            if modelo is None:
                # R148a: sin el modelo no se sabe si el plano lo escribe y no se leyó o si no lo
                # dice; cada marca se nombra.
                d_rebar, d_stirrup, _ = a.default_castillo
                report.warnings.append(
                    "Acero por leer — castillos y columnas sin armado o sin sección leídos del "
                    f"plano (acero no cuantificado desde el plano; se suplió con {d_rebar} "
                    f"E{d_stirrup}, {d_section[0]}x{d_section[1]} cm): "
                    + ", ".join(f"{m} (sin {faltan[m]})" for m in assumed_marks)
                )
        if modelo is not None:
            heights_note = (
                "altura de cada elemento del modelo estructural (niveles del plano, o supuesta y "
                "dicha)"
            )
            notes = _notas_del_modelo(cuenta, modelo, waste) + notes
            report.warnings.extend(
                _avisos_del_modelo(
                    cuenta, "castillos y columnas",
                    "acero no cuantificado desde su armado en estos (los que no tienen ninguno "
                    "llevan el armado supuesto, dicho)",
                )
            )
            for aviso, marcas_sin_fila in cuenta.sin_fila.items():
                sin_fila.setdefault(aviso, set()).update(marcas_sin_fila)
        else:
            heights_note = (
                "altura de entrepiso de cada planta (niveles NTC/NPT)" if story_heights
                else f"altura {height:.2f} m por elemento"
            )
        notes.insert(
            0,
            f"{heights_note[:1].upper()}{heights_note[1:]} + {a.anchorage_m:.2f} m de anclaje"
            + (" (supuesto)" if modelo is not None else "")
            + f"; desperdicio {a.waste_pct:g} %",
        )
        report.lines.append(
            SteelLine(
                concept_code=CODE_CASTILLOS, quantity=round(quantity, 2), unit="KG",
                source_detections=list(columns.source_detections), notes=notes,
            )
        )

    # --- dalas over walls ------------------------------------------------
    walls = lines.get("EST-004")
    if walls is not None and walls.raw_quantity > 0:
        length = walls.raw_quantity  # metres of wall (already in m)
        spec, origin = _spec_for(specs, "DALA", "dala")
        leido = _leer_spec(spec, "dala")
        rebar = leido.grupos or None
        stirrups = leido.estribo
        section = tuple(spec["section_cm"]) if spec and spec.get("section_cm") else None
        assumed = rebar is None or section is None
        if assumed:
            d_rebar, d_stirrup, d_section = a.default_dala
            default = _leer_spec({"rebar": d_rebar, "stirrups": d_stirrup}, "dala")
            rebar = rebar or default.grupos
            stirrups = stirrups or default.estribo
            section = section or d_section
        assert rebar is not None and section is not None
        long_kg, stir_kg = _linear_element_kg(
            length, rebar, stirrups, (float(section[0]), float(section[1])), a, anchorage=False
        )
        report.lines.append(
            SteelLine(
                concept_code=CODE_DALAS, quantity=round((long_kg + stir_kg) * waste, 2),
                unit="KG", source_detections=list(walls.source_detections),
                notes=[
                    f"Dala de cerramiento sobre {length:,.1f} m de muro: {_texto_varillas(rebar)}"
                    + _texto_estribo(stirrups)
                    + f" sección {section[0]}x{section[1]} cm "
                    + ("(supuesto)" if assumed else f"(plano: {origin})"),
                    f"Desperdicio {a.waste_pct:g} %",
                ],
            )
        )

    # --- zapatas: parrilla -------------------------------------------------
    footings = lines.get("CIM-002")
    if footings is not None and footings.source_detections and meters_factor:
        spec, origin = _spec_for(specs, "ZAPATA", "zapata")
        mesh = _leer_malla(spec)
        assumed = mesh is None
        mesh = mesh or parse_spacing(a.default_zapata_mesh)
        assert mesh is not None
        number, spacing = mesh
        total = 0.0
        sized = 0
        for det_id in footings.source_detections:
            det = by_id.get(det_id)
            if det is None:
                continue
            props = det.properties
            if props.get("dimensioned_width") and props.get("dimensioned_length"):
                w = float(props["dimensioned_width"]) * meters_factor
                length = float(props["dimensioned_length"]) * meters_factor
                sized += 1
            else:
                area = float(props.get("estimated_area") or 0.0) * meters_factor**2
                w = length = math.sqrt(area) if area > 0 else 0.0
            if w <= 0 or length <= 0:
                continue
            bars_along = math.floor((w - 2 * a.cover_m) / spacing) + 1
            bars_across = math.floor((length - 2 * a.cover_m) / spacing) + 1
            total += (bars_along * (length + a.hook_m) + bars_across * (w + a.hook_m)) * (
                BAR_KG_PER_M[number]
            )
        report.lines.append(
            SteelLine(
                concept_code=CODE_ZAPATAS, quantity=round(total * waste, 2), unit="KG",
                source_detections=list(footings.source_detections),
                notes=[
                    f"Parrilla #{number}@{spacing * 100:.0f} cm en ambos sentidos "
                    + ("(supuesta)" if assumed else f"(plano: {origin})")
                    + f" en {len(footings.source_detections)} zapatas, {sized} con cotas del plano",
                    f"Ganchos {a.hook_m:.3f} m, recubrimiento {a.cover_m:.3f} m, "
                    f"desperdicio {a.waste_pct:g} %",
                ],
            )
        )

    # --- trabes: only with a stated armado -----------------------------------
    beam_sources: list[tuple[str, str]] = []
    for line_code, family in (("EST-002", "trabe"), ("CIM-008", "contratrabe")):
        beam_line = lines.get(line_code)
        if beam_line is not None:
            beam_sources.extend((det_id, family) for det_id in beam_line.source_detections)
    if beam_sources:
        total = 0.0
        covered: list[str] = []
        missing: set[str] = set()
        cuenta = _Cuenta()
        for det_id, family in beam_sources:
            det = by_id.get(det_id)
            if det is None:
                continue
            elemento = modelo.por_deteccion.get(det_id) if modelo is not None else None
            if elemento is not None and modelo is not None:
                if _del_modelo(cuenta, elemento, modelo, a):
                    covered.append(det_id)
                else:
                    _sin_acero_en(cuenta, elemento)
                continue
            mark = det.label.strip().upper()
            spec, _origin = _spec_for(specs, mark, family)
            leido = _leer_spec(spec, family)
            section = tuple(spec["section_cm"]) if spec and spec.get("section_cm") else None
            span_du = float(det.properties.get("estimated_span_length") or 0.0)
            span = span_du * (meters_factor or 1.0)
            if not leido.grupos or section is None or span <= 0:
                missing.add(mark)
                continue
            long_kg, stir_kg = _linear_element_kg(
                span, leido.grupos, leido.estribo, (float(section[0]), float(section[1])), a,
                anchorage=True,
            )
            total += long_kg + stir_kg
            covered.append(det_id)
        if covered:
            notes = [f"{len(covered)} trabes con armado declarado en el plano"]
            if modelo is not None:
                notes += _notas_del_modelo(cuenta, modelo, waste)
            notes.append(f"Desperdicio {a.waste_pct:g} %")
            report.lines.append(
                SteelLine(
                    concept_code=CODE_TRABES, quantity=round((total + cuenta.total) * waste, 2),
                    unit="KG", source_detections=covered, notes=notes,
                )
            )
        if modelo is not None:
            report.warnings.extend(
                _avisos_del_modelo(
                    cuenta, "trabes y contratrabes",
                    "acero no cuantificado en estos (no hay armado supuesto de trabes)",
                )
            )
            for aviso, marcas_sin_fila in cuenta.sin_fila.items():
                sin_fila.setdefault(aviso, set()).update(marcas_sin_fila)
        if missing:
            # R148a: cada marca, sin recortar.
            report.warnings.append(
                "Acero por leer — trabes y contratrabes sin armado leído del plano (acero no "
                "cuantificado): " + ", ".join(sorted(missing))
            )

    # --- losa: malla electrosoldada en la capa de compresión ----------------
    malla_area = 0.0
    malla_sources: list[str] = []
    for code in ("EST-003", "EST-012"):
        line = lines.get(code)
        if line is not None and line.raw_quantity > 0:
            malla_area += line.raw_quantity
            malla_sources.extend(line.source_detections)
    if malla_area > 0:
        report.lines.append(
            SteelLine(
                concept_code=CODE_MALLA,
                quantity=round(malla_area * a.malla_overlap_factor, 2), unit="M2",
                source_detections=malla_sources,
                notes=[
                    f"Área de losa reticular/vigueta {malla_area:,.1f} m² × "
                    f"{a.malla_overlap_factor:.2f} de traslapes (capa de compresión)"
                ],
            )
        )
    # --- losas macizas y de cimentación: armado por su propia etiqueta ---------
    factor = (meters_factor or 1.0) ** 2
    slab_total = 0.0
    slab_sources: list[str] = []
    slab_notes: list[str] = []
    for code, label in (("EST-013", "losa maciza"), ("CIM-007", "losa de cimentación")):
        line = lines.get(code)
        if line is None or line.raw_quantity <= 0:
            continue
        read_m2 = 0.0
        unread_m2 = 0.0
        for det_id in line.source_detections:
            det = by_id.get(det_id)
            if det is None:
                continue
            area = float(det.properties.get("estimated_area") or 0.0) * factor
            parsed = slab_rebar_kg_per_m2(det.properties.get("label"))
            if parsed is None or area <= 0:
                unread_m2 += area
                continue
            kg_m2, how = parsed
            slab_total += area * kg_m2
            read_m2 += area
            slab_sources.append(det_id)
            if how not in slab_notes:
                slab_notes.append(how)
        if unread_m2 > 0:
            report.warnings.append(
                f"{label.capitalize()}: {unread_m2:,.1f} m² sin armado en su etiqueta; ese acero "
                "no se cuantificó (capturarlo del detalle)."
            )
        if read_m2 > 0:
            slab_notes.append(f"{label} {read_m2:,.1f} m² con armado leído de la etiqueta")
    if slab_total > 0:
        report.lines.append(
            SteelLine(
                concept_code=CODE_LOSAS, quantity=round(slab_total * waste, 2), unit="KG",
                source_detections=slab_sources,
                notes=["Parrillas por m² según etiqueta de cada tablero: " + "; ".join(slab_notes),
                       f"Desperdicio {a.waste_pct:g} %"],
            )
        )
    if modelo is not None:
        en_lineas = {
            det_id
            for code in ("EST-001", "EST-002", "CIM-008")
            if (line := lines.get(code)) is not None
            for det_id in line.source_detections
        }
        fuera = _fuera_del_presupuesto(modelo, en_lineas, a, waste)
        if fuera:
            report.warnings.append(fuera)
    for aviso, con_esa_varilla in sorted(sin_fila.items()):
        report.warnings.append(
            f"Tabla de varillas: {aviso} (en {', '.join(sorted(con_esa_varilla))})."
        )
    if modelo is not None:
        # R148a: las familias del modelo sin concepto de acero en esta etapa también se dicen.
        sin_concepto: dict[str, list[str]] = {}
        for e in modelo.elementos:
            if e.familia in ("pilote", "muro_concreto"):
                sin_concepto.setdefault(e.marca or f"{e.familia} sin marca", []).append(e.hoja)
        if sin_concepto:
            report.warnings.append(
                "Acero por leer — pilotes y muros de concreto: acero no cuantificado (no tienen "
                "concepto de acero en esta etapa): "
                + ", ".join(f"{m} ({_pzas(len(h))})" for m, h in sorted(sin_concepto.items()))
            )
    return report


def apply_steel(boq: BillOfQuantities, catalog: list, apus: dict, steel: SteelReport) -> int:
    """Append steel lines for the concepts the catalog has; report the rest."""
    concepts = {concept.code: concept for concept in catalog}
    existing = {line.concept_code for line in boq.lines}
    added = 0
    for steel_line in steel.lines:
        concept = concepts.get(steel_line.concept_code)
        apu = apus.get(steel_line.concept_code)
        if concept is None or apu is None:
            boq.warnings.append(
                f"Acero calculado ({steel_line.quantity:,.0f} {steel_line.unit}) pero el "
                f"catálogo no tiene el concepto {steel_line.concept_code} con matriz: "
                "agrégalo para costearlo."
            )
            continue
        if steel_line.concept_code in existing or steel_line.quantity <= 0:
            continue
        boq.lines.append(
            BoqLine(
                concept_code=concept.code,
                description=concept.description,
                unit=concept.unit,
                quantity=round(steel_line.quantity, 4),
                unit_price=apu.direct_unit_cost,
                amount=round(steel_line.quantity * apu.direct_unit_cost, 2),
                phase=concept.phase,
                raw_quantity=steel_line.quantity,
                raw_kind=QuantityKind.COUNT,
                source_detection_count=len(steel_line.source_detections),
                source_detections=list(steel_line.source_detections),
                confidence=0.7,
                assumptions=["Derivado de armados del plano y cantidades del presupuesto"]
                + steel_line.notes,
            )
        )
        added += 1
    boq.warnings.extend(steel.warnings)
    if added:
        boq.direct_cost_total = round(sum(line.amount for line in boq.lines), 2)
        totals: dict[str, float] = {}
        for line in boq.lines:
            totals[line.phase] = round(totals.get(line.phase, 0.0) + line.amount, 2)
        boq.totals_by_phase = totals
    return added
