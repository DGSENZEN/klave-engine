"""View segmentation: split a sheet into its plan views and detail/table regions.

A single structural sheet packs several plan views (planta de cimentación,
planta baja, planta alta, azotea…) plus details, schedules, and notes. The same
physical element is drawn once per plan view, so counting raw detections
inflates quantities by a sheet-dependent factor. This module attributes every
detection to a labeled view so the cost engine can deduplicate vertical
elements, restrict foundation work to the foundation plan, and sum level
elements correctly.

Detection is title-driven and deterministic: large text matching plan keywords
anchors a plan view; detail/table/note keywords anchor excluded regions. When
fewer than two plan views are found the sheet is treated as a single implicit
plan and behavior matches the flat (non-segmented) pipeline.
"""

import math
import re
import statistics
from collections import defaultdict
from enum import StrEnum

from pydantic import BaseModel, Field
from shapely.geometry import box
from shapely.strtree import STRtree

from klave_engine.detection.frames import SheetFrame
from klave_engine.detection.inventory import reads_as_structure
from klave_engine.detection.results import Detection, layer_matches
from klave_engine.dxf.entities import NormalizedEntity
from klave_engine.geometry.bbox import BBox, bbox_center, bbox_contains_point, bbox_union_all
from klave_engine.geometry.forma import Formas

# Plan-view titles we quantify, mapped to a canonical level key.
_PLAN_KEYWORDS: list[tuple[str, re.Pattern[str]]] = [
    ("cimentacion", re.compile(r"\bCIMENTACI", re.I)),
    ("planta_baja", re.compile(r"\bPLANTA\s+BAJA|\bP\.?B\.?\b", re.I)),
    ("planta_alta", re.compile(r"\bPLANTA\s+ALTA|\bP\.?A\.?\b", re.I)),
    ("azotea", re.compile(r"\bAZOTEA", re.I)),
    ("entrepiso", re.compile(r"\bENTREPISO", re.I)),
]
_NIVEL_RE = re.compile(r"\b(?:NIVEL|N)\s*[-]?\s*(\d+)", re.I)
_PLANTA_GENERIC = re.compile(r"\bPLANTA\b", re.I)
# Regions that must never contribute to quantities.
_EXCLUDE_RE = re.compile(
    r"DETALLE|TABLA|NOTAS?|CUADRO|ISOMETRIC|CORTE|FACHADA|SECCION|SECCIÓN|"
    r"ARMADO|ANCLAJE|SIMBOLOG|CROQUIS|LOCALIZAC",
    re.I,
)
_NPT_RE = re.compile(r"N\.?\s*P\.?\s*T\.?\s*\+?\s*(-?\d+\.\d+)", re.I)
# Any way a sheet writes a level: N.P.T. +3.20, NTC +4.35, NIVEL +7.95, N.I.P. +10.70
_LEVEL_RE = re.compile(
    r"\b(?:N\.?\s*P\.?\s*T\.?|N\.?\s*T\.?\s*C\.?|N\.?\s*I\.?\s*P\.?|NIVEL)\s*[:=]?\s*"
    r"([+-]?\s*\d+(?:[.,]\d+)?)",
    re.I,
)
# Tarea 15e: la leyenda de nivel de una planta («N.P.T. +3.45», «N.P.T. 0+00», «NIVEL ±0.00»):
# su prefijo y su valor, con signo, «±» (o «%%p» de AutoCAD) o el «0+00» del nivel cero.
_LEYENDA_RE = re.compile(
    r"\b(?:N\.?\s*P\.?\s*T\.?|N\.?\s*T\.?\s*C\.?|N\.?\s*I\.?\s*P\.?|NIVEL)\s*[:=]?\s*"
    r"(?:(?P<cero>[±]?\s*0\s*\+\s*0{2})(?![\d.,])|(?:±|%%[pP]|\+/-)?\s*(?P<valor>[+-]?\s*\d+[.,]\d+))",
    re.I,
)

_TITLE_HEIGHT_FACTOR = 2.5  # title text is at least this × median text height
_MIN_TITLE_HEIGHT = 0.25


class ViewKind(StrEnum):
    plan = "plan"
    excluded = "excluded"  # detail / table / note / section


class ViewRegion(BaseModel):
    view_id: str
    title: str
    kind: ViewKind
    level_key: str | None = None  # cimentacion | planta_baja | azotea | nivel_2 …
    npt_level: float | None = None
    # M-4: every level the planta's texts declare, with how many say it (the most said first):
    # ``npt_level`` is the first; the others are what it was weighed against.
    niveles_leidos: list[tuple[float, int]] = Field(default_factory=list)
    # Tarea 15e: la leyenda de nivel pegada a su título («N.P.T. +3.45» bajo «PLANTA BAJA»), dicha
    # para la procedencia del nivel (``nota``); y, si sus leyendas dicen niveles distintos, la duda
    # (``npt_level`` queda vacío: ni el mayor ni el primero).
    leyenda_de_nivel: str = ""
    nivel_en_duda: str = ""
    # False for plantas of non-structural sheets (cancelería, instalaciones…):
    # they are views for the levantamiento but never levels of the structure.
    structural: bool = True
    anchor: tuple[float, float]
    bbox: BBox | None = None
    detection_ids: list[str] = Field(default_factory=list)
    detection_counts: dict[str, int] = Field(default_factory=dict)


# Declared levels closer than this are the same level on different sheets.
SAME_LEVEL_M = 0.6


class AlturaDeEntrepiso(BaseModel):
    """The height of one planta and where it comes from (R73): the distance from its declared
    level to the next one above (``nivel_arriba_m``), or — the top planta, with nothing declared
    above it — the height of the planta below, repeated (``repetida``: an assumption, not what
    the drawing says)."""

    altura_m: float
    nivel_m: float
    nivel_arriba_m: float | None = None
    repetida: bool = False
    # Tarea 15e (R270, R273), lectura B: la planta más alta no dibuja losa; sus castillos y muros
    # van del nivel de la planta de abajo hasta el suyo (``nivel_arriba_m``), sin losa encima.
    sin_losa: bool = False
    texto: str


class LosaAcotada(BaseModel):
    """Tarea 15e (R271): el peralte de la losa que un detalle del plano acota (``detalle``): el
    título del detalle («LOSA DE VIGUETA Y BOVEDILLA 12-5») y su cadena de cotas verticales
    (15 + 5 = 20)."""

    espesor_m: float
    texto: str


# El Voronoi de títulos tiene tope: 1.5× la separación mediana entre anclas.
ANCHOR_ASSIGN_FACTOR = 1.5
# Tarea 15c: la región aparte (no es planta) de lo que está dentro de las rejillas de dos plantas
# sin dibujo que diga de cuál es: se cuenta una vez y no la cobra ninguna hasta que se decida.
VISTA_EN_DUDA = "vista_en_duda"


class SheetSegmentation(BaseModel):
    views: list[ViewRegion]
    assignment: dict[str, str]  # detection_id -> view_id
    is_segmented: bool  # True when ≥2 plan views were found
    npt_levels: list[float] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)
    # R165: detections whose two nearest titles are about as near and whose drawing does not
    # say which view they belong to: kept at the nearest title, with this aviso.
    vistas_dudosas: dict[str, str] = Field(default_factory=dict)
    # Tarea 15c: la rejilla de ejes de cada planta que la tiene (su caja, la vista): lo que está
    # dentro de la de una sola es de esa planta, aunque las cajas de las vistas se traslapen.
    rejillas: list[tuple[BBox, str]] = Field(default_factory=list)
    # Tarea 15e (R270): el aviso que dice por qué el nivel de cada planta es la losa que dibuja
    # (lectura B: sus castillos van del nivel de la planta de abajo al suyo); vacío cuando el
    # dibujo no lo muestra y no se escoge (las alturas de siempre; la verificación 8 dice las dos).
    lectura_de_niveles: str = ""
    # Tarea 15e (R271): los peraltes de losa que acotan los detalles del plano.
    losas_acotadas: list[LosaAcotada] = Field(default_factory=list)
    # R286 (I2): esta corrida buscó esos peraltes. Un views.json de antes no lo trae: no se leyeron,
    # y eso no quiere decir que el plano no los acote.
    losas_leidas: bool = False
    # Tarea 15e (R272), lectura B: cada castillo de la cimentación que sigue en la planta de arriba
    # (detección → (la de arriba, a cuánto, ya corrida la rejilla)); y los que no, con su aviso.
    continuaciones: dict[str, tuple[str, float]] = Field(default_factory=dict)
    sin_continuacion: dict[str, str] = Field(default_factory=dict)

    def losa_acotada(self) -> LosaAcotada | None:
        """Tarea 15e (R271): el peralte de losa del plano, si sus detalles acotan uno solo. Si
        acotan varios (losas de cimentación, de alberca, de entrepiso), el plano no dice cuál está
        sobre los muros de cada planta: ninguno."""
        distintos = {round(losa.espesor_m, 3) for losa in self.losas_acotadas}
        return self.losas_acotadas[0] if len(distintos) == 1 else None

    def sin_losa_acotada(self) -> str:
        """R286 (I2): por qué no se descuenta un peralte de losa (``losa_acotada`` es None), dicho
        como lo que hizo el motor —nunca «el plano no la acota»: un detalle puede acotarla con una
        sola cota, o en una cadena que no se leyó."""
        if not self.losas_leidas:
            return (
                "esta lectura no buscó el peralte de la losa en los detalles (reprocesa el plano)"
            )
        peraltes = sorted({round(losa.espesor_m * 100) for losa in self.losas_acotadas})
        if peraltes:
            return (
                f"los detalles acotan peraltes de losa distintos ({', '.join(map(str, peraltes))} "
                "cm) y no dicen cuál está sobre los muros de cada planta"
            )
        return (
            "no se leyó un peralte de losa acotado en un detalle (se lee una cadena de cotas "
            "que suma su total)"
        )

    def vista_por_rejilla(self, punto: tuple[float, float]) -> str | None:
        """Tarea 15c: la planta cuya rejilla, sola, contiene el punto; ninguna si son varias o
        ninguna."""
        dentro = {vid for caja, vid in self.rejillas if bbox_contains_point(caja, punto)}
        return dentro.pop() if len(dentro) == 1 else None

    def plan_views(self) -> list[ViewRegion]:
        return [v for v in self.views if v.kind == ViewKind.plan]

    def structural_plan_views(self) -> list[ViewRegion]:
        """The plantas that describe the structure's levels. When no sheet
        reads as structure (an instalaciones-only project) every planta counts."""
        structural = [v for v in self.plan_views() if v.structural]
        return structural or self.plan_views()

    def foundation_views(self) -> list[ViewRegion]:
        return [v for v in self.structural_plan_views() if v.level_key == "cimentacion"]

    def superstructure_views(self) -> list[ViewRegion]:
        return [v for v in self.structural_plan_views() if v.level_key != "cimentacion"]

    def story_heights(self) -> dict[str, float]:
        """Height of each planta (view_id → m): the distance to the next
        declared level above it; the top planta repeats the one below. Only
        when at least two plantas declare their level. Levels closer than
        ``SAME_LEVEL_M`` are one level drawn on several sheets (the arch
        planta baja and the structural one), never a story. Where each height
        comes from: ``alturas_de_entrepiso``."""
        return {vista: a.altura_m for vista, a in self.alturas_de_entrepiso().items()}

    def alturas_de_entrepiso(self) -> dict[str, AlturaDeEntrepiso]:
        """``story_heights`` with where each height comes from (R73): between two declared
        levels (named in ``texto``), or repeated from the planta below for the top one. Tarea 15e
        (R270): with ``lectura_de_niveles`` (the drawing shows each level is the slab its planta
        draws) each planta goes from the level below up to its own, the top one (no slab in its
        planta) too."""
        return self._entrepisos()[0]

    def dudas_de_nivel(self) -> list[str]:
        """Tarea 15e (R270): lo que los niveles declarados no dejan medir y se dice como duda (la
        verificación 8): una planta con leyendas de nivel que no coinciden, y un entrepiso que no
        es una altura de planta (fuera de 1.8–8 m; ni la cimentación ni la planta más alta sin
        losa)."""
        en_duda = [v.nivel_en_duda for v in self.structural_plan_views() if v.nivel_en_duda]
        return en_duda + self._entrepisos()[1]

    def _entrepisos(self) -> tuple[dict[str, AlturaDeEntrepiso], list[str]]:
        leveled = sorted(
            (v for v in self.structural_plan_views() if v.npt_level is not None),
            key=lambda v: v.npt_level or 0.0,
        )
        if len(leveled) < 2:
            return {}, []
        clusters: list[list[ViewRegion]] = []
        for view in leveled:
            level = view.npt_level or 0.0
            if clusters and level - (clusters[-1][0].npt_level or 0.0) < SAME_LEVEL_M:
                clusters[-1].append(view)
            else:
                clusters.append([view])
        # Tarea 15e: una planta dibujada sin nivel entre dos que lo tienen: nadie mide a través de
        # ella (su altura y la de su vecina por ese lado no se conocen).
        sin_nivel = [
            v for v in self.structural_plan_views() if v.npt_level is None and v.detection_ids
        ]

        def salta(abajo: list[ViewRegion], arriba: list[ViewRegion]) -> bool:
            ordenes = [orden_de_planta(v) for v in (*abajo, *arriba)]
            if any(o is None for o in ordenes):
                return False
            bajo = max(orden_de_planta(v) or 0 for v in abajo)
            alto = min(orden_de_planta(v) or 0 for v in arriba)
            return any(bajo < (orden_de_planta(u) or -1) < alto for u in sin_nivel)

        def nombre(cluster: list[ViewRegion]) -> str:
            """The cluster's level, its plantas and (M-4) how many texts say each level."""
            nivel = cluster[0].npt_level or 0.0
            partes = []
            for v in cluster:
                votos = ", ".join(f"{n:+g} ×{c}" for n, c in v.niveles_leidos[:4])
                partes.append(f"{v.title}: {votos}" if votos else v.title)
            return f"{nivel:+.2f} ({'; '.join(partes)})"

        def es_cimentacion(cluster: list[ViewRegion]) -> bool:
            return all(v.level_key == "cimentacion" for v in cluster)

        heights: dict[str, AlturaDeEntrepiso] = {}
        dudas: list[str] = []

        def fuera_de_rango(cluster: list[ViewRegion], delta: float, de: float, a: float) -> None:
            titulos = ", ".join(f"«{v.title}»" for v in cluster)
            dudas.append(
                f"el entrepiso de {titulos} mide {round(delta, 3):g} m (de {de:+.2f} a {a:+.2f}, "
                "los niveles que el plano declara): no es una altura de planta; sus castillos y "
                "muros no se miden con ella hasta que se decida"
            )

        if self.lectura_de_niveles:
            for index, cluster in enumerate(clusters):
                base = cluster[0].npt_level or 0.0
                if index == 0:
                    # La cimentación: los castillos suyos que siguen en la planta de arriba
                    # (``continuaciones``, R272) son su arranque (las cantidades no los cuentan
                    # dos veces): de su nivel al de arriba. Los que no siguen
                    # (``sin_continuacion``) no toman esta altura: es un supuesto, con su duda.
                    if len(clusters) < 2 or not es_cimentacion(cluster):
                        continue
                    if salta(cluster, clusters[1]):
                        continue
                    arriba = clusters[1][0].npt_level or 0.0
                    delta = arriba - base
                    if 1.8 <= delta <= 8.0:
                        altura = AlturaDeEntrepiso(
                            altura_m=round(delta, 3),
                            nivel_m=base,
                            nivel_arriba_m=arriba,
                            texto=(
                                f"el arranque de los castillos de {nombre(clusters[1])}, que "
                                f"van de {nombre(cluster)} a la losa de su planta: "
                                f"{round(delta, 3):g} m ({self.lectura_de_niveles})"
                            ),
                        )
                        for view in cluster:
                            heights[view.view_id] = altura
                    continue
                abajo = clusters[index - 1]
                if salta(abajo, cluster):
                    continue
                debajo = abajo[0].npt_level or 0.0
                delta = base - debajo
                tope = index + 1 == len(clusters)
                if tope:
                    valida = 0.0 < delta <= 8.0
                    texto = (
                        f"la planta más alta, {nombre(cluster)}, sin losa en su planta: sus "
                        f"castillos y muros van de {nombre(abajo)} hasta su nivel: "
                        f"{round(delta, 3):g} m ({self.lectura_de_niveles})"
                    )
                else:
                    valida = 1.8 <= delta <= 8.0
                    texto = (
                        f"bajo su losa: la planta dibuja la losa de su nivel {nombre(cluster)} y "
                        f"sus castillos van desde {nombre(abajo)}: {round(delta, 3):g} m "
                        f"({self.lectura_de_niveles})"
                    )
                if not valida:
                    if not tope:
                        fuera_de_rango(cluster, delta, debajo, base)
                    continue
                altura = AlturaDeEntrepiso(
                    altura_m=round(delta, 3),
                    nivel_m=debajo,
                    nivel_arriba_m=base,
                    sin_losa=tope,
                    texto=texto,
                )
                for view in cluster:
                    heights[view.view_id] = altura
            return heights, dudas

        previous: AlturaDeEntrepiso | None = None
        previous_titulos: list[str] = []
        for index, cluster in enumerate(clusters):
            base = cluster[0].npt_level or 0.0
            if index + 1 < len(clusters):
                if salta(cluster, clusters[index + 1]):
                    previous = None
                    continue
                arriba = clusters[index + 1][0].npt_level or 0.0
                delta = arriba - base
                altura = AlturaDeEntrepiso(
                    altura_m=round(delta, 3),
                    nivel_m=base,
                    nivel_arriba_m=arriba,
                    texto=(
                        f"entre los niveles declarados {nombre(cluster)} y "
                        f"{nombre(clusters[index + 1])}: {round(delta, 3):g} m"
                    ),
                )
            elif previous is not None:
                delta = previous.altura_m
                abajo_ = ", ".join(t for t in previous_titulos)
                altura = AlturaDeEntrepiso(
                    altura_m=delta,
                    nivel_m=base,
                    repetida=True,
                    texto=(
                        f"la planta más alta, {nombre(cluster)}, no tiene un nivel declarado "
                        f"encima: repite la altura de la planta de abajo, «{abajo_}» ({delta:g} m, "
                        f"de {previous.nivel_m:+.2f} a {previous.nivel_arriba_m or base:+.2f})"
                    ),
                )
            else:
                continue
            if 1.8 <= delta <= 8.0:
                if not altura.repetida:
                    previous, previous_titulos = altura, [v.title for v in cluster]
                for view in cluster:
                    heights[view.view_id] = altura
            else:
                # Tarea 15e: la planta de arriba no repite un entrepiso que no es una altura, y
                # éste (salvo el de la cimentación) es una duda.
                previous = None
                if not altura.repetida and not es_cimentacion(cluster):
                    fuera_de_rango(cluster, delta, base, altura.nivel_arriba_m or base)
        return heights, dudas

    def total_height(self) -> float | None:
        """Top finished level (max NPT) when at least two distinct levels exist."""
        levels = sorted(set(self.npt_levels))
        if len(levels) >= 2 and max(levels) > 0:
            return max(levels)
        return None


class _TitleAnchor(BaseModel):
    title: str
    kind: ViewKind
    level_key: str | None
    npt_level: float | None
    point: tuple[float, float]
    height: float


def punto_de_texto(e: NormalizedEntity) -> tuple[float, float]:
    """The point a title or a tag stands for when views are told apart by proximity: the centre
    of the box the normalizer used to give it (from its insert, 0.6 heights per character, one
    line). R165: the views' borders are a proximity rule calibrated on these points; the text's
    real extent (R146) must not move them — near-ties are decided by the drawing instead."""
    insert = e.properties.get("insert")
    alto = e.properties.get("height")
    if insert is None or not isinstance(alto, int | float) or alto <= 0:
        return bbox_center(e.bbox)
    ancho = max(float(alto) * 0.6 * max(len(e.text or ""), 1), float(alto))
    return (float(insert[0]) + ancho / 2, float(insert[1]) + float(alto) / 2)


class _Puntos:
    """Where each detection stands for the views: a detection that is a text (a tag) stands at
    its text's point (``punto_de_texto``); any other, at its box's centre."""

    def __init__(self, entities: list[NormalizedEntity]) -> None:
        self._textos = {e.entity_id: e for e in entities if e.is_textual}

    def de(self, detection: Detection) -> tuple[float, float]:
        primera = detection.source_entities[0] if detection.source_entities else ""
        texto = self._textos.get(primera)
        if texto is not None and tuple(texto.bbox) == tuple(detection.bbox):
            return punto_de_texto(texto)
        return bbox_center(detection.bbox)


def _classify_title(text: str) -> tuple[ViewKind, str | None] | None:
    """Return (kind, level_key) for a title, or None if it is not a title."""
    if _EXCLUDE_RE.search(text):
        return (ViewKind.excluded, None)
    for level_key, pattern in _PLAN_KEYWORDS:
        if pattern.search(text):
            return (ViewKind.plan, level_key)
    nivel = _NIVEL_RE.search(text)
    if nivel:
        return (ViewKind.plan, f"nivel_{nivel.group(1)}")
    if _PLANTA_GENERIC.search(text):
        return (ViewKind.plan, "planta")
    return None


def _collect_anchors(entities: list[NormalizedEntity]) -> list[_TitleAnchor]:
    heights = [
        float(e.properties["height"])
        for e in entities
        if e.is_textual and "height" in e.properties and float(e.properties["height"]) > 0
    ]
    if not heights:
        return []
    threshold = max(_MIN_TITLE_HEIGHT, statistics.median(heights) * _TITLE_HEIGHT_FACTOR)

    anchors: list[_TitleAnchor] = []
    for entity in entities:
        if not entity.is_textual or not entity.text:
            continue
        height = float(entity.properties.get("height", 0.0))
        if height < threshold:
            continue
        text = " ".join(entity.text.split())
        classified = _classify_title(text)
        if classified is None:
            continue
        kind, level_key = classified
        npt = _NPT_RE.search(text)
        anchors.append(
            _TitleAnchor(
                title=text,
                kind=kind,
                level_key=level_key,
                npt_level=float(npt.group(1)) if npt else None,
                point=punto_de_texto(entity),
                height=height,
            )
        )
    return anchors


def _merge_plan_anchors(anchors: list[_TitleAnchor]) -> list[_TitleAnchor]:
    """Collapse repeated plan titles for the same level (a big header plus a
    smaller NPT caption) into one anchor, keeping the tallest text's position
    and any parsed NPT level."""
    by_level: dict[str, list[_TitleAnchor]] = {}
    passthrough: list[_TitleAnchor] = []
    for anchor in anchors:
        if anchor.kind == ViewKind.plan and anchor.level_key and anchor.level_key != "planta":
            by_level.setdefault(anchor.level_key, []).append(anchor)
        else:
            passthrough.append(anchor)

    merged: list[_TitleAnchor] = []
    for level_key, group in by_level.items():
        tallest = max(group, key=lambda a: a.height)
        npt = next((a.npt_level for a in group if a.npt_level is not None), None)
        merged.append(
            _TitleAnchor(
                title=tallest.title,
                kind=ViewKind.plan,
                level_key=level_key,
                npt_level=npt,
                point=tallest.point,
                height=tallest.height,
            )
        )
    return merged + passthrough


def _level_values(texts: list[str]) -> list[float]:
    values: list[float] = []
    for text in texts:
        for m in _LEVEL_RE.finditer(text):
            try:
                values.append(float(m.group(1).replace(" ", "").replace(",", ".")))
            except ValueError:
                continue
    return values


def _frame_level(entities: list[NormalizedEntity], frame: SheetFrame) -> float | None:
    """The level a planta declares most often inside its frame (texts and
    cajetín/level-marker attributes)."""
    niveles = _frame_levels(entities, frame)
    return niveles[0][0] if niveles else None


def _frame_levels(entities: list[NormalizedEntity], frame: SheetFrame) -> list[tuple[float, int]]:
    """Every level a planta declares inside its frame, with how many texts say it: the most said
    first (ties: the lower level), as ``_frame_level`` picks it."""
    texts: list[str] = []
    for e in entities:
        if e.source_file != frame.source_file and frame.source_file:
            continue
        if not bbox_contains_point(frame.bbox, bbox_center(e.bbox)):
            continue
        if e.is_textual and e.text:
            texts.append(e.text)
        attributes = (e.properties or {}).get("attributes")
        if isinstance(attributes, dict):
            texts.extend(str(v) for v in attributes.values())
    values = _level_values(texts)
    counts: dict[float, int] = {}
    for v in values:
        counts[v] = counts.get(v, 0) + 1
    return sorted(counts.items(), key=lambda vc: (-vc[1], vc[0]))


def _npt_levels(entities: list[NormalizedEntity]) -> list[float]:
    return sorted(
        {
            float(m.group(1))
            for e in entities
            if e.is_textual and e.text
            for m in [_NPT_RE.search(e.text)]
            if m
        }
    )


def nivel_de_leyenda(texto: str) -> float | None:
    """Tarea 15e: el nivel que dice una leyenda («N.P.T. +3.45» → 3.45; «N.P.T. 0+00», «±0.00»,
    «%%p0.00», «0.00» → 0), o nada si el texto no declara un nivel."""
    m = _LEYENDA_RE.search(texto or "")
    if m is None:
        return None
    if m.group("cero"):
        return 0.0
    valor = float(m.group("valor").replace(" ", "").replace(",", "."))
    return 0.0 if valor == 0 else valor


# Tarea 15e: el orden de las plantas de abajo arriba por su nombre (lo que no se nombra así no tiene
# orden: no se decide nada que dependa de él).
_ORDEN_DE_PLANTA = {
    "cimentacion": 0,
    "planta_baja": 1,
    "entrepiso": 2,
    "planta_alta": 3,
    "roof_garden": 4,
    "azotea": 5,
}


def orden_de_planta(vista: ViewRegion) -> int | None:
    return _ORDEN_DE_PLANTA.get(vista.level_key or "")


# Tarea 15e: una leyenda está pegada al título de su planta: su centro a no más de tantas alturas
# del título por encima o por debajo, y de lado dentro de lo ancho de los dos textos; y ese título,
# el más cercano a ella, al menos a la mitad de la distancia del siguiente.
_LEYENDA_ALTOS = 3.0
_LEYENDA_DEL_TITULO = 2.0


def _ancho_de_texto(texto: str, alto: float) -> float:
    return max(alto * 0.6 * max(len(texto), 1), alto)


def _leyendas_de_nivel(
    entities: list[NormalizedEntity], anchors: list["_TitleAnchor"]
) -> dict[int, list[tuple[float, str]]]:
    """Tarea 15e: las leyendas de nivel pegadas al título de cada planta (índice del ancla →
    [(nivel, texto)]), por la geometría del dibujo: bajo o sobre su título, nunca por el orden."""
    salida: dict[int, list[tuple[float, str]]] = defaultdict(list)
    if not anchors:
        return salida
    for e in entities:
        if not e.is_textual or not e.text:
            continue
        nivel = nivel_de_leyenda(e.text)
        if nivel is None:
            continue
        texto = " ".join(e.text.split())
        alto = float(e.properties.get("height", 0.0) or 0.0)
        punto = punto_de_texto(e)
        cerca = sorted(
            (math.dist(punto, a.point), i) for i, a in enumerate(anchors)
        )  # fmt: skip
        d0, i0 = cerca[0]
        if len(cerca) > 1 and cerca[1][0] < _LEYENDA_DEL_TITULO * d0:
            continue
        ancla = anchors[i0]
        if ancla.kind != ViewKind.plan:
            continue
        dx = abs(punto[0] - ancla.point[0])
        dy = abs(punto[1] - ancla.point[1])
        holgura = (_ancho_de_texto(ancla.title, ancla.height) + _ancho_de_texto(texto, alto)) / 2
        if dy <= _LEYENDA_ALTOS * ancla.height and dx <= holgura:
            salida[i0].append((nivel, texto))
    return salida


def _nivel_de_sus_leyendas(
    region: ViewRegion, leyendas: list[tuple[float, str]]
) -> None:
    """Tarea 15e: el nivel de la planta por sus leyendas (``nota``): el que dicen, si todas dicen
    el mismo; si dicen distintos, ninguno y la duda (ni el mayor ni el primero)."""
    cuentas: dict[float, int] = {}
    for nivel, _t in leyendas:
        clave = round(nivel, 3)
        cuentas[clave] = cuentas.get(clave, 0) + 1
    region.niveles_leidos = sorted(cuentas.items(), key=lambda vc: (-vc[1], vc[0]))
    textos = ", ".join(f"«{t}»" for _n, t in leyendas)
    if len(cuentas) == 1:
        region.npt_level = next(iter(cuentas))
        region.leyenda_de_nivel = f"{textos} bajo su título «{region.title}»"
        return
    region.npt_level = None
    niveles = ", ".join(f"{n:+.2f}" for n in sorted(cuentas))
    region.nivel_en_duda = (
        f"«{region.title}» declara niveles distintos junto a su título ({textos}: {niveles}); "
        "no se toma ninguno hasta que se decida"
    )


def _lectura_bajo_su_losa(
    views: list[ViewRegion], assignment: dict[str, str], detections: list[Detection]
) -> str:
    """Tarea 15e (R270): el aviso de la lectura B cuando el dibujo la muestra, o nada. El nivel de
    cada planta es la losa que dibuja (sus castillos van del nivel de la de abajo al suyo) sólo si
    (i) la planta más alta dibuja castillos o muros y ninguna losa, y (ii) cada otra planta de
    superestructura con castillos dibuja tableros de losa. Si no, no se escoge."""
    plantas = [v for v in views if v.kind == ViewKind.plan and v.structural] or [
        v for v in views if v.kind == ViewKind.plan
    ]
    if sum(1 for v in plantas if v.npt_level is not None) < 2:
        return ""
    tipos: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for d in detections:
        vista = assignment.get(d.detection_id)
        if vista is not None:
            tipos[vista][d.detection_type.value] += 1

    def castillos(v: ViewRegion) -> int:
        return tipos[v.view_id]["column_tag"]

    def losas(v: ViewRegion) -> int:
        return tipos[v.view_id]["slab_region"]

    con_dibujo = [v for v in plantas if castillos(v) or tipos[v.view_id]["wall"]]
    if len(con_dibujo) < 2 or any(orden_de_planta(v) is None for v in con_dibujo):
        return ""
    alto = max(orden_de_planta(v) or 0 for v in con_dibujo)
    tope = [v for v in con_dibujo if orden_de_planta(v) == alto]
    if len(tope) != 1 or losas(tope[0]):
        return ""
    resto = [
        v
        for v in con_dibujo
        if v is not tope[0] and v.level_key != "cimentacion" and castillos(v)
    ]
    if not resto or any(not losas(v) for v in resto):
        return ""
    nombres = " y ".join(f"«{v.title}»" for v in resto)
    dibuja = "dibuja" if len(resto) == 1 else "dibujan"
    return (
        f"el nivel es la losa que dibuja la planta: {nombres} {dibuja} su losa y «{tope[0].title}» "
        f"no (castillos y muros sin losa en su planta); los castillos de cada planta van del "
        f"nivel de la de abajo hasta el suyo"
    )


# Tarea 15e (R271): el título de un detalle de losa, y lo lejos que pueden estar sus cotas (en
# metros: R286, se compara con la distancia del dibujo pasada a metros).
_TITULO_DE_LOSA = re.compile(r"^\s*LOSA\b", re.I)
_COTAS_DE_SU_DETALLE_M = 6.0


def _cm_de_losa(valor: float) -> float | None:
    """El peralte de una losa en metros por lo que dice su cota: 8–60 en centímetros (la unidad
    de las cotas de un detalle), 0.08–0.60 en metros; otra cosa no es un peralte de losa."""
    if 8.0 <= valor <= 60.0:
        return valor / 100.0
    if 0.08 <= valor <= 0.60:
        return valor
    return None


def _losas_acotadas(
    entities: list[NormalizedEntity], unit_to_m: float = 1.0
) -> list[LosaAcotada]:
    """Tarea 15e (R271): el peralte que acota cada detalle de losa («LOSA DE VIGUETA Y BOVEDILLA
    12-5»): de las cotas verticales más cercanas a su título que a otro título de losa, la que
    abarca a las demás, si las que están dentro de ella la llenan y suman lo que dice (15 + 5 =
    20). Una cota sola (que puede ser cualquier cosa del detalle), una cadena que no suma o un
    detalle sin cotas verticales no acotan nada."""
    titulos = [
        e for e in entities if e.is_textual and e.text and _TITULO_DE_LOSA.match(e.text.strip())
    ]
    if not titulos:
        return []
    verticales: list[tuple[NormalizedEntity, float, float, float, float]] = []
    for e in entities:
        if e.entity_type.value != "dimension":
            continue
        props = e.properties or {}
        valor, tramo = props.get("display_value"), props.get("measured_segment")
        if valor is None or not tramo or len(tramo) != 2:
            continue
        (x0, y0), (x1, y1) = tramo
        if abs(x1 - x0) > 1e-6 or abs(y1 - y0) <= 1e-6:
            continue
        verticales.append((e, float(valor), min(y0, y1), max(y0, y1), x0))
    salida: list[LosaAcotada] = []
    for titulo in titulos:
        centro = punto_de_texto(titulo)
        suyas = []
        for cota in verticales:
            medio = (cota[4], (cota[2] + cota[3]) / 2)
            d = math.dist(medio, centro)
            if d * unit_to_m > _COTAS_DE_SU_DETALLE_M:
                continue
            otros = (o for o in titulos if o is not titulo)
            if all(math.dist(medio, punto_de_texto(otro)) >= d for otro in otros):
                suyas.append(cota)
        if not suyas:
            continue
        total = max(suyas, key=lambda c: c[3] - c[2])
        partes = [
            c for c in suyas
            if c is not total and c[2] >= total[2] - 1e-6 and c[3] <= total[3] + 1e-6
        ]  # fmt: skip
        largo = total[3] - total[2]
        if len(partes) < 2:
            continue
        cubierto = sum(c[3] - c[2] for c in partes)
        if abs(cubierto - largo) > 0.01 * largo or abs(sum(c[1] for c in partes) - total[1]) > 1e-6:
            continue
        espesor = _cm_de_losa(total[1])
        if espesor is None:
            continue
        cadena = " + ".join(f"«{c[1]:g}»" for c in sorted(partes, key=lambda c: c[2]))
        titulo_txt = " ".join((titulo.text or "").split())
        salida.append(
            LosaAcotada(
                espesor_m=round(espesor, 4),
                texto=(
                    f"el detalle «{titulo_txt}» ({titulo.raw_handle}) acota la losa en "
                    f"{total[1]:g} ({total[0].raw_handle} = {cadena})"
                ),
            )
        )
    return salida


# Tarea 15e (R272): un castillo de la cimentación sigue en la planta de arriba si, corrida la
# rejilla, hay uno de ella a esta distancia o menos (el ancho de dos castillos), uno a uno. En
# metros (R286): las distancias del dibujo se pasan a metros con el factor de su unidad.
_CONTINUACION_M = 0.30
_EJES_COINCIDEN_M = 0.02


def _corrimiento(
    abajo: list[float], arriba: list[float], unit_to_m: float = 1.0
) -> float | None:
    """Cuánto está corrida una rejilla de la otra en un sentido (en unidades del dibujo): la
    diferencia entre las coordenadas de sus ejes que más pares de ejes juntan (dos o más)."""
    coinciden = _EJES_COINCIDEN_M / unit_to_m
    mejor: tuple[int, float] | None = None
    for a in abajo:
        for b in arriba:
            delta = b - a
            pares = sum(
                1 for x in abajo if any(abs(x + delta - y) <= coinciden for y in arriba)
            )
            if pares >= 2 and (mejor is None or pares > mejor[0]):
                mejor = (pares, delta)
    return mejor[1] if mejor else None


def _continuaciones(
    views: list[ViewRegion],
    assignment: dict[str, str],
    detections: list[Detection],
    entities: list[NormalizedEntity],
    unit_to_m: float = 1.0,
) -> tuple[dict[str, tuple[str, float]], dict[str, str]]:
    """Tarea 15e (R272): de los castillos y columnas de la cimentación, los que siguen en la planta
    de superestructura más baja (corrida la rejilla de ejes de una a la otra, el de arriba a
    ``_CONTINUACION_M`` o menos, uno a uno, el más cercano primero) y los que no, con su aviso.
    Cada uno está donde está su marcador (su símbolo), o su etiqueta si no tiene. Las distancias,
    en metros (``unit_to_m``: el dibujo puede estar en cm o mm)."""
    plantas = sorted(
        (v for v in views if v.kind == ViewKind.plan and v.npt_level is not None),
        key=lambda v: v.npt_level or 0.0,
    )
    cimentacion = [v for v in plantas if v.level_key == "cimentacion"]
    encima = [v for v in plantas if v.level_key != "cimentacion"]
    if len(cimentacion) != 1 or not encima:
        return {}, {}
    cim, arriba = cimentacion[0], encima[0]
    por_id = {e.entity_id: e for e in entities}

    def punto(d: Detection) -> tuple[float, float]:
        if d.properties.get("section_source") and len(d.source_entities) > 1:
            marcador = por_id.get(d.source_entities[1])
            if marcador is not None:
                return bbox_center(marcador.bbox)
        return bbox_center(d.bbox)

    def de(vista: ViewRegion, tipo: str) -> list[Detection]:
        return [
            d for d in detections
            if assignment.get(d.detection_id) == vista.view_id and d.detection_type.value == tipo
        ]  # fmt: skip

    def ejes(vista: ViewRegion, sentido: str) -> list[float]:
        return [
            float(d.properties["coordinate"])
            for d in de(vista, "grid_line")
            if d.properties.get("axis") == sentido and d.properties.get("coordinate") is not None
        ]

    abajo_c, arriba_c = de(cim, "column_tag"), de(arriba, "column_tag")
    if not abajo_c:
        return {}, {}
    dx = _corrimiento(ejes(cim, "vertical"), ejes(arriba, "vertical"), unit_to_m)
    dy = _corrimiento(ejes(cim, "horizontal"), ejes(arriba, "horizontal"), unit_to_m)
    if dx is None or dy is None:
        aviso = (
            f"no se sabe si sigue en «{arriba.title}»: las rejillas de ejes de «{cim.title}» y de "
            f"«{arriba.title}» no se pueden empalmar"
        )
        return {}, {d.detection_id: aviso for d in abajo_c}
    pares = sorted(
        (math.dist((p[0] + dx, p[1] + dy), q) * unit_to_m, a.detection_id, b.detection_id)
        for a in abajo_c
        for p in [punto(a)]
        for b in arriba_c
        for q in [punto(b)]
    )
    siguen: dict[str, tuple[str, float]] = {}
    usados: set[str] = set()
    for distancia, a_id, b_id in pares:
        if distancia > _CONTINUACION_M:
            break
        if a_id in siguen or b_id in usados:
            continue
        siguen[a_id] = (b_id, round(distancia, 3))
        usados.add(b_id)
    sin: dict[str, str] = {}
    for a in abajo_c:
        if a.detection_id in siguen:
            continue
        cerca = min(
            (d for d, x, _b in pares if x == a.detection_id), default=None
        )  # fmt: skip
        donde = f"el más cercano está a {cerca:.2f} m" if cerca is not None else "no tiene ninguno"
        sin[a.detection_id] = (
            f"no sigue en «{arriba.title}»: corrida la rejilla de ejes ({dx * unit_to_m:+.2f}, "
            f"{dy * unit_to_m:+.2f} m), no "
            f"hay castillo ni columna a {_CONTINUACION_M:g} m o menos ({donde}); no es el "
            "arranque de uno de arriba y su altura no la dice el plano"
        )
    return siguen, sin


def _near_frame(frame: SheetFrame, point: tuple[float, float], margin: float = 0.05) -> bool:
    """Within a small margin of the frame (a mark drawn on its border)."""
    x0, y0, x1, y1 = frame.bbox
    dx, dy = (x1 - x0) * margin, (y1 - y0) * margin
    return x0 - dx <= point[0] <= x1 + dx and y0 - dy <= point[1] <= y1 + dy


def _segment_by_frames(
    entities: list[NormalizedEntity],
    detections: list[Detection],
    frames: list[SheetFrame],
    unit_to_m: float = 1.0,
) -> SheetSegmentation | None:
    """Sheet frames are views: every detection belongs to the frame that
    contains it (or the nearest frame when it sits on its border). What lies
    outside every frame — stray xrefs, blocks parked beside the sheets — is
    no sheet's content and is kept apart, excluded from quantities."""
    puntos = _Puntos(entities)

    def es_planta(frame: SheetFrame) -> bool:
        """Un marco cuenta como planta si su cajetín lo dice, o si está en una
        hoja de instalaciones y nada dijo que fuera otra cosa.

        En los planos de instalaciones el cajetín rara vez repite «PLANTA»: la
        clave de la hoja (HID-01, SAN-04, IAA-03) ya dice de qué es, y dentro
        del marco está la planta de esa instalación. Tratarlo como excluido
        afirma que es un detalle o un cuadro, y entonces sus salidas y sus
        metros desaparecen del presupuesto sin que nadie lo note. Un marco que
        SÍ dice «DETALLE» o «CORTE» sigue excluido, aquí y en cualquier hoja."""
        if frame.kind == "plan":
            return True
        return (
            frame.kind == "unknown"
            and bool(frame.source_file)
            and not reads_as_structure(frame.source_file)
        )

    usable = [f for f in frames if f.kind in ("plan", "excluded") or es_planta(f)]
    if len(usable) < 2 or not any(es_planta(f) for f in usable):
        return None
    regions: dict[str, ViewRegion] = {}
    for frame in frames:
        kind = ViewKind.plan if es_planta(frame) else ViewKind.excluded
        regions[frame.frame_id] = ViewRegion(
            view_id=frame.frame_id,
            title=f"{frame.code} · {frame.title}".strip(" ·") or frame.code,
            kind=kind,
            level_key=frame.level_key if kind == ViewKind.plan else None,
            npt_level=_frame_level(entities, frame) if kind == ViewKind.plan else None,
            niveles_leidos=_frame_levels(entities, frame) if kind == ViewKind.plan else [],
            structural=reads_as_structure(frame.source_file) if frame.source_file else True,
            anchor=bbox_center(frame.bbox),
            bbox=frame.bbox,
        )
    outside = ViewRegion(
        view_id="outside_frames",
        title="Fuera de los marcos de hoja",
        kind=ViewKind.excluded,
        level_key=None,
        anchor=bbox_center(frames[0].bbox),
        bbox=frames[0].bbox,
    )
    assignment: dict[str, str] = {}
    for detection in detections:
        center = puntos.de(detection)
        # Each file is its own coordinate space: only its frames can hold it.
        source = detection.evidence.source
        own = [f for f in frames if not f.source_file or not source or f.source_file == source]
        holder = next((f for f in own if bbox_contains_point(f.bbox, center)), None)
        if holder is None:
            holder = next((f for f in own if _near_frame(f, center)), None)
        region = regions[holder.frame_id] if holder is not None else outside
        assignment[detection.detection_id] = region.view_id
        region.detection_ids.append(detection.detection_id)
        region.detection_counts[detection.detection_type.value] = (
            region.detection_counts.get(detection.detection_type.value, 0) + 1
        )
    if outside.detection_ids:
        regions[outside.view_id] = outside
    plans = [r for r in regions.values() if r.kind == ViewKind.plan]
    levels = sorted({r.npt_level for r in plans if r.npt_level is not None})
    lectura = _lectura_bajo_su_losa(list(regions.values()), assignment, detections)
    siguen, sin = (
        _continuaciones(list(regions.values()), assignment, detections, entities, unit_to_m)
        if lectura
        else ({}, {})
    )
    return SheetSegmentation(
        views=list(regions.values()),
        assignment=assignment,
        is_segmented=True,
        losas_acotadas=_losas_acotadas(entities, unit_to_m),
        losas_leidas=True,
        continuaciones=siguen,
        sin_continuacion=sin,
        npt_levels=levels or _npt_levels(entities),
        notes=[
            f"{len(frames)} marcos de hoja detectados: {len(plans)} plantas, "
            f"{len(frames) - len(plans)} de detalle/corte/otros."
        ]
        + ([f"Niveles: {lectura}"] if lectura else []),
        lectura_de_niveles=lectura,
    )


def segment_views(
    entities: list[NormalizedEntity],
    detections: list[Detection],
    frames: list[SheetFrame] | None = None,
    unit_to_m: float = 1.0,
) -> SheetSegmentation:
    """``unit_to_m``: metros por unidad del dibujo (R286): las distancias que se comparan con un
    umbral en metros (las cotas de un detalle de losa, la continuación de un castillo, los ejes
    que coinciden) se pasan a metros, para que un dibujo en cm o mm se lea como uno en m."""
    if frames:
        by_frames = _segment_by_frames(entities, detections, frames, unit_to_m)
        if by_frames is not None:
            return by_frames
    anchors = _merge_plan_anchors(_collect_anchors(entities))
    puntos = _Puntos(entities)
    plan_anchors = [a for a in anchors if a.kind == ViewKind.plan]

    if len(plan_anchors) < 2:
        return SheetSegmentation(
            views=[],
            assignment={},
            is_segmented=False,
            notes=[
                f"Se encontraron {len(plan_anchors)} vista(s) de planta etiquetadas; "
                "el plano se trata como una sola vista."
            ],
        )

    # Build one region per anchor; assign each detection to the nearest anchor.
    regions: dict[str, ViewRegion] = {}
    for index, anchor in enumerate(anchors):
        view_id = f"view_{index:02d}_{anchor.level_key or anchor.kind.value}"
        regions[view_id] = ViewRegion(
            view_id=view_id,
            title=anchor.title,
            kind=anchor.kind,
            level_key=anchor.level_key,
            npt_level=anchor.npt_level,
            anchor=anchor.point,
        )
    anchor_ids = list(regions.keys())
    # Tarea 15e: el nivel de cada planta, de la leyenda pegada a su título («N.P.T. +3.45» bajo
    # «PLANTA BAJA»), por la geometría del dibujo y nunca por el orden de las leyendas.
    for index, leyendas in _leyendas_de_nivel(entities, anchors).items():
        _nivel_de_sus_leyendas(regions[anchor_ids[index]], leyendas)

    # Un ancla no adopta lo que está lejos de todos los títulos: el Voronoi
    # tiene tope — más allá de 1.5× la separación mediana entre anclas, la
    # detección queda excluida en vez de atribuida a la menos lejana.
    cap_sq: float | None = None
    if len(anchor_ids) >= 2:
        spacings = sorted(
            min(
                (regions[other].anchor[0] - regions[vid].anchor[0]) ** 2
                + (regions[other].anchor[1] - regions[vid].anchor[1]) ** 2
                for other in anchor_ids
                if other != vid
            )
            for vid in anchor_ids
        )
        cap = ANCHOR_ASSIGN_FACTOR * spacings[len(spacings) // 2] ** 0.5
        cap_sq = cap * cap
    far_region: ViewRegion | None = None

    # Tarea 15c: el dibujo de cada planta es su rejilla de ejes. Lo que está dentro de la rejilla
    # de una sola planta es de esa planta, esté el título que esté más cerca (PRUEBA-1: el título
    # de PLANTA ALTA, debajo de su planta, queda junto a la esquina de arriba de la AZOTEA); lo
    # que está dentro de las de dos, lo decide su dibujo, o es una duda (``VISTA_EN_DUDA``).
    rejillas = _rejillas_de_las_plantas(detections, regions)
    por_rejilla: dict[str, str] = {}
    en_dos: dict[str, tuple[str, ...]] = {}
    for detection in detections:
        punto = puntos.de(detection)
        dentro = tuple(sorted({vid for caja, vid in rejillas if bbox_contains_point(caja, punto)}))
        if len(dentro) == 1:
            por_rejilla[detection.detection_id] = dentro[0]
        elif dentro:
            en_dos[detection.detection_id] = dentro

    assignment: dict[str, str] = {}
    member_boxes: dict[str, list[BBox]] = {vid: [] for vid in anchor_ids}
    for detection in detections:
        if detection.detection_id in por_rejilla or detection.detection_id in en_dos:
            suya = por_rejilla.get(detection.detection_id) or en_dos[detection.detection_id][0]
            assignment[detection.detection_id] = suya
            regions[suya].detection_ids.append(detection.detection_id)
            regions[suya].detection_counts[detection.detection_type.value] = (
                regions[suya].detection_counts.get(detection.detection_type.value, 0) + 1
            )
            continue
        cx, cy = puntos.de(detection)
        nearest_id = min(
            anchor_ids,
            key=lambda vid: (regions[vid].anchor[0] - cx) ** 2
            + (regions[vid].anchor[1] - cy) ** 2,
        )
        nearest_sq = (regions[nearest_id].anchor[0] - cx) ** 2 + (
            regions[nearest_id].anchor[1] - cy
        ) ** 2
        if cap_sq is not None and nearest_sq > cap_sq:
            if far_region is None:
                far_region = ViewRegion(
                    view_id="far_from_titles",
                    title="Lejos de todo título",
                    kind=ViewKind.excluded,
                    level_key=None,
                    anchor=(cx, cy),
                )
                regions["far_from_titles"] = far_region
            assignment[detection.detection_id] = far_region.view_id
            far_region.detection_ids.append(detection.detection_id)
            far_region.detection_counts[detection.detection_type.value] = (
                far_region.detection_counts.get(detection.detection_type.value, 0) + 1
            )
            continue
        assignment[detection.detection_id] = nearest_id
        region = regions[nearest_id]
        region.detection_ids.append(detection.detection_id)
        region.detection_counts[detection.detection_type.value] = (
            region.detection_counts.get(detection.detection_type.value, 0) + 1
        )
        member_boxes[nearest_id].append(detection.bbox)

    # R165: a detection about as near two titles (within 10 %) is not decided by the titles'
    # centres (a title's centre moving to where its text really lies tipped three PRUEBA-1 slab
    # panels into the legend): the drawing it belongs to decides — the linework it is part of,
    # and the view of the detections clearly assigned on that same drawing. If the drawing
    # cannot say, it stays at the nearest title with the aviso «vista dudosa».
    dudosas = _desempatar(entities, detections, regions, assignment, por_rejilla, en_dos)
    if any(despues == VISTA_EN_DUDA for _a, despues, _x in dudosas.values()):
        regions[VISTA_EN_DUDA] = ViewRegion(
            view_id=VISTA_EN_DUDA,
            title="En duda entre dos plantas",
            kind=ViewKind.excluded,
            level_key=None,
            anchor=regions[anchor_ids[0]].anchor,
        )
    tipos = {d.detection_id: d.detection_type.value for d in detections}
    for detection_id, (antes, despues, _aviso) in dudosas.items():
        if antes != despues:
            regions[antes].detection_ids.remove(detection_id)
            regions[despues].detection_ids.append(detection_id)
            tipo = tipos[detection_id]
            regions[antes].detection_counts[tipo] -= 1
            if regions[antes].detection_counts[tipo] == 0:
                del regions[antes].detection_counts[tipo]
            cuentas = regions[despues].detection_counts
            cuentas[tipo] = cuentas.get(tipo, 0) + 1
            assignment[detection_id] = despues
    member_boxes = {vid: [] for vid in anchor_ids}
    for detection in detections:
        vid = assignment.get(detection.detection_id)
        if vid in member_boxes:
            member_boxes[vid].append(detection.bbox)

    for view_id, boxes in member_boxes.items():
        if boxes:
            regions[view_id].bbox = bbox_union_all(boxes)

    # N.P.T. captions are often smaller than the view titles, so scan all text
    # for level annotations rather than relying on the title anchors alone.
    npt_levels = sorted(
        {a.npt_level for a in plan_anchors if a.npt_level is not None}
        | {
            float(m.group(1))
            for e in entities
            if e.is_textual and e.text
            for m in [_NPT_RE.search(e.text)]
            if m
        }
    )
    npt_levels = sorted(
        set(npt_levels) | {r.npt_level for r in regions.values() if r.npt_level is not None}
    )
    n_en_duda = sum(1 for x in dudosas.values() if x[1] == VISTA_EN_DUDA)
    n_dudosas = sum(1 for x in dudosas.values() if x[2]) - n_en_duda
    lectura = _lectura_bajo_su_losa(list(regions.values()), assignment, detections)
    siguen, sin = (
        _continuaciones(list(regions.values()), assignment, detections, entities, unit_to_m)
        if lectura
        else ({}, {})
    )
    return SheetSegmentation(
        views=list(regions.values()),
        assignment=assignment,
        is_segmented=True,
        losas_acotadas=_losas_acotadas(entities, unit_to_m),
        losas_leidas=True,
        continuaciones=siguen,
        sin_continuacion=sin,
        npt_levels=npt_levels,
        notes=[
            f"Se detectaron {len(plan_anchors)} vistas de planta y "
            f"{len(anchors) - len(plan_anchors)} regiones de detalle/tabla."
        ]
        + ([f"{n_dudosas} detecciones en vista dudosa"] if n_dudosas else [])
        + ([f"{n_en_duda} detecciones en vista en duda"] if n_en_duda else [])
        + ([f"Niveles: {lectura}"] if lectura else []),
        vistas_dudosas={k: x[2] for k, x in dudosas.items() if x[2]},
        rejillas=rejillas,
        lectura_de_niveles=lectura,
    )


# R165: two titles are about as near when the second is at most this much farther.
EMPATE_DE_TITULOS = 1.10
# The share of the votes of the clearly assigned detections on the same drawing that decides.
_MAYORIA = 2.0 / 3.0


def _desempatar(
    entities: list[NormalizedEntity],
    detections: list[Detection],
    regions: dict[str, "ViewRegion"],
    assignment: dict[str, str],
    por_rejilla: dict[str, str] | None = None,
    en_dos: dict[str, tuple[str, ...]] | None = None,
) -> dict[str, tuple[str, str, str]]:
    """For every detection about as near two titles: (its nearest view, the view its drawing
    gives, the aviso «vista dudosa» when the drawing cannot say). The drawing is the connected
    linework the detection's own entities belong to (walls, outlines, the symbols that touch
    them); its view is the vote of the clearly assigned detections on it.

    Tarea 15c: what one planta's grid holds (``por_rejilla``) is decided — never a tie — and
    votes for that planta. What the grids of several plantas hold (``en_dos``: the plantas) is
    decided the same way among those plantas; when its drawing cannot say, it goes to
    ``VISTA_EN_DUDA`` with the aviso «vista en duda» (no planta counts it until it is decided)."""
    por_rejilla = por_rejilla or {}
    en_dos = en_dos or {}
    fuera = ("far_from_titles", VISTA_EN_DUDA)
    candidatos = {vid: r for vid, r in regions.items() if vid not in fuera}
    if len(candidatos) < 2:
        return {}
    puntos = _Puntos(entities)
    empatadas: dict[str, tuple[str, ...]] = {}
    claras: dict[str, str] = {}
    for detection in detections:
        did = detection.detection_id
        if did in en_dos:
            empatadas[did] = en_dos[did]
            continue
        if did in por_rejilla:
            claras[did] = por_rejilla[did]
            continue
        vid = assignment.get(did)
        if vid not in candidatos:
            continue
        cx, cy = puntos.de(detection)
        cerca = sorted((math.dist((cx, cy), r.anchor), k) for k, r in candidatos.items())
        if cerca[1][0] <= EMPATE_DE_TITULOS * cerca[0][0]:
            empatadas[did] = (cerca[0][1], cerca[1][1])
        else:
            claras[did] = vid
    if not empatadas:
        return {}
    anclas = [r.anchor for r in candidatos.values()]
    separacion = statistics.median(
        min(math.dist(a, b) for j, b in enumerate(anclas) if j != i) for i, a in enumerate(anclas)
    )
    dibujo = _Dibujos(entities, _TRAZO_LARGO * separacion, _MARGEN * separacion)
    votos: dict[int, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    por_id = {d.detection_id: d for d in detections}
    for detection_id, vid in claras.items():
        for c in dibujo.de(por_id[detection_id]):
            votos[c][vid] += 1
    salida: dict[str, tuple[str, str, str]] = {}
    for detection_id, opciones in empatadas.items():
        cuenta: dict[str, int] = defaultdict(int)
        for c in dibujo.de(por_id[detection_id]):
            for vid in opciones:
                cuenta[vid] += votos[c].get(vid, 0)
        total = sum(cuenta[v] for v in opciones)
        primera = opciones[0]
        ganadora = max(opciones, key=lambda v: (cuenta[v], v == primera))
        empate = sum(1 for v in opciones if cuenta[v] == cuenta[ganadora]) > 1
        if total >= 2 and cuenta[ganadora] >= _MAYORIA * total and not empate:
            salida[detection_id] = (assignment[detection_id], ganadora, "")
        elif detection_id in en_dos:
            orden = sorted(opciones, key=lambda v: regions[v].title)
            titulos = [f"«{regions[v].title}»" for v in orden]
            cuentas = " contra ".join(str(cuenta[v]) for v in orden)
            ninguna = "ninguna de las dos" if len(orden) == 2 else "ninguna de ellas"
            salida[detection_id] = (
                assignment[detection_id],
                VISTA_EN_DUDA,
                f"vista en duda: está dentro de la rejilla de {titulos[0]} y de la de "
                + " y de la de ".join(titulos[1:])
                + f", y su dibujo no dice de cuál es ({cuentas}); no se cuenta en {ninguna} "
                "hasta que se decida",
            )
        else:
            segunda = opciones[1]
            titulo_a, titulo_b = regions[primera].title, regions[segunda].title
            salida[detection_id] = (
                primera,
                primera,
                f"vista dudosa: casi igual de cerca de «{titulo_a}» y de «{titulo_b}», y su "
                f"dibujo no dice de cuál es ({cuenta[primera]} contra {cuenta[segunda]}); se "
                f"deja en «{titulo_a}»",
            )
    return salida


# Tarea 15c: a grid is one planta's when that planta's title is at most half as far from it as
# any other title (a title is drawn beside its own planta, below or above it).
_TITULO_DE_SU_REJILLA = 2.0


def _rejillas_de_las_plantas(
    detections: list[Detection], regions: dict[str, "ViewRegion"]
) -> list[tuple[BBox, str]]:
    """Tarea 15c: each planta's drawn extent, its grid: the axes (``grid_line``) that cross one
    another, at least two each way, and the box of their lines (they reach past the outer walls
    to their bubbles). A grid is the planta's whose title is clearly the nearest to its box
    (``_TITULO_DE_SU_REJILLA``); a grid nearest a detail's title, or about as near two titles,
    places nothing."""
    ejes = [
        d
        for d in detections
        if d.detection_type.value == "grid_line"
        and (d.properties or {}).get("axis") in ("horizontal", "vertical")
    ]
    if len(ejes) < 4 or len(regions) < 2:
        return []
    padre = list(range(len(ejes)))

    def raiz(i: int) -> int:
        while padre[i] != i:
            padre[i] = padre[padre[i]]
            i = padre[i]
        return i

    tol = 1e-6
    for i, a in enumerate(ejes):
        for j in range(i + 1, len(ejes)):
            b = ejes[j]
            if a.properties["axis"] == b.properties["axis"]:
                continue
            if (
                a.bbox[0] <= b.bbox[2] + tol
                and b.bbox[0] <= a.bbox[2] + tol
                and a.bbox[1] <= b.bbox[3] + tol
                and b.bbox[1] <= a.bbox[3] + tol
            ):
                padre[raiz(j)] = raiz(i)
    grupos: dict[int, list[Detection]] = defaultdict(list)
    for i, eje in enumerate(ejes):
        grupos[raiz(i)].append(eje)
    salida: list[tuple[BBox, str]] = []
    for grupo in grupos.values():
        sentidos = [e.properties["axis"] for e in grupo]
        if sentidos.count("horizontal") < 2 or sentidos.count("vertical") < 2:
            continue
        caja = bbox_union_all([e.bbox for e in grupo])
        cerca = sorted(
            (_distancia_a_caja(r.anchor, caja), vid)
            for vid, r in regions.items()
            if vid not in ("far_from_titles", VISTA_EN_DUDA)
        )
        (d1, vid), (d2, _otra) = cerca[0], cerca[1]
        if regions[vid].kind != ViewKind.plan or d2 <= _TITULO_DE_SU_REJILLA * d1:
            continue
        salida.append((caja, vid))
    return salida


def _distancia_a_caja(punto: tuple[float, float], caja: BBox) -> float:
    dx = max(caja[0] - punto[0], 0.0, punto[0] - caja[2])
    dy = max(caja[1] - punto[1], 0.0, punto[1] - caja[3])
    return math.hypot(dx, dy)


# Lines longer than this share of the titles' median spacing (sheet borders, grid axes, slab
# edges across a sheet) and grid axes do not join two drawings into one.
_TRAZO_LARGO = 0.25
# A detection's drawing includes the linework this share of that spacing around its box.
_MARGEN = 0.01
_CAPAS_DE_EJES = ["EJE", "EJES", "GRID", "AXIS"]


class _Dibujos:
    """The connected pieces of linework of a sheet (lines, polylines, arcs, circles and hatches
    that touch), to know which drawing a detection belongs to — without sheet borders, grid axes
    and other lines longer than ``largo_max``, which would join drawings that only share a
    sheet. Built only when needed."""

    def __init__(self, entities: list[NormalizedEntity], largo_max: float, margen: float) -> None:
        self._margen = margen
        trazos = [
            e
            for e in entities
            if not e.is_textual
            and not e.is_annotation
            and e.entity_type.value in ("line", "polyline", "arc", "circle", "hatch")
            and not layer_matches(e.layer, _CAPAS_DE_EJES)
            and math.hypot(e.bbox[2] - e.bbox[0], e.bbox[3] - e.bbox[1]) <= largo_max
        ]
        self._formas = Formas(trazos)
        geoms = [self._formas.de(e) for e in trazos]
        tamano = [max(e.bbox[2] - e.bbox[0], e.bbox[3] - e.bbox[1]) for e in trazos]
        tol = 1e-3 * (statistics.median(tamano) if tamano else 1.0)
        self._ids = {e.entity_id: i for i, e in enumerate(trazos)}
        padre = list(range(len(trazos)))

        def raiz(i: int) -> int:
            while padre[i] != i:
                padre[i] = padre[padre[i]]
                i = padre[i]
            return i

        self._arbol = STRtree(geoms) if geoms else None
        self._geoms = geoms
        if self._arbol is not None:
            for i, g in enumerate(geoms):
                for j in self._arbol.query(g.buffer(tol)):
                    j = int(j)
                    if j > i and g.distance(geoms[j]) <= tol:
                        padre[raiz(j)] = raiz(i)
        self._pieza = [raiz(i) for i in range(len(trazos))]

    def de(self, detection: Detection) -> set[int]:
        """The pieces a detection's own entities belong to, and those within ``margen`` of its
        box (a castillo's tag and marker sit on the walls of their planta)."""
        piezas = {self._pieza[self._ids[i]] for i in detection.source_entities if i in self._ids}
        if self._arbol is None:
            return piezas
        caja = box(*detection.bbox).buffer(self._margen)
        return piezas | {
            self._pieza[int(j)] for j in self._arbol.query(caja, predicate="intersects")
        }
