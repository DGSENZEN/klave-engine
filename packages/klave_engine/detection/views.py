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
    texto: str


# El Voronoi de títulos tiene tope: 1.5× la separación mediana entre anclas.
ANCHOR_ASSIGN_FACTOR = 1.5


class SheetSegmentation(BaseModel):
    views: list[ViewRegion]
    assignment: dict[str, str]  # detection_id -> view_id
    is_segmented: bool  # True when ≥2 plan views were found
    npt_levels: list[float] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)
    # R165: detections whose two nearest titles are about as near and whose drawing does not
    # say which view they belong to: kept at the nearest title, with this aviso.
    vistas_dudosas: dict[str, str] = Field(default_factory=dict)

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
        levels (named in ``texto``), or repeated from the planta below for the top one."""
        leveled = sorted(
            (v for v in self.structural_plan_views() if v.npt_level is not None),
            key=lambda v: v.npt_level or 0.0,
        )
        if len(leveled) < 2:
            return {}
        clusters: list[list[ViewRegion]] = []
        for view in leveled:
            level = view.npt_level or 0.0
            if clusters and level - (clusters[-1][0].npt_level or 0.0) < SAME_LEVEL_M:
                clusters[-1].append(view)
            else:
                clusters.append([view])

        def nombre(cluster: list[ViewRegion]) -> str:
            """The cluster's level, its plantas and (M-4) how many texts say each level."""
            nivel = cluster[0].npt_level or 0.0
            partes = []
            for v in cluster:
                votos = ", ".join(f"{n:+g} ×{c}" for n, c in v.niveles_leidos[:4])
                partes.append(f"{v.title}: {votos}" if votos else v.title)
            return f"{nivel:+.2f} ({'; '.join(partes)})"

        heights: dict[str, AlturaDeEntrepiso] = {}
        previous: AlturaDeEntrepiso | None = None
        previous_titulos: list[str] = []
        for index, cluster in enumerate(clusters):
            base = cluster[0].npt_level or 0.0
            if index + 1 < len(clusters):
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
                abajo = ", ".join(t for t in previous_titulos)
                altura = AlturaDeEntrepiso(
                    altura_m=delta,
                    nivel_m=base,
                    repetida=True,
                    texto=(
                        f"la planta más alta, {nombre(cluster)}, no tiene un nivel declarado "
                        f"encima: repite la altura de la planta de abajo, «{abajo}» ({delta:g} m, "
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
        return heights

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


def _near_frame(frame: SheetFrame, point: tuple[float, float], margin: float = 0.05) -> bool:
    """Within a small margin of the frame (a mark drawn on its border)."""
    x0, y0, x1, y1 = frame.bbox
    dx, dy = (x1 - x0) * margin, (y1 - y0) * margin
    return x0 - dx <= point[0] <= x1 + dx and y0 - dy <= point[1] <= y1 + dy


def _segment_by_frames(
    entities: list[NormalizedEntity], detections: list[Detection], frames: list[SheetFrame]
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
    return SheetSegmentation(
        views=list(regions.values()),
        assignment=assignment,
        is_segmented=True,
        npt_levels=levels or _npt_levels(entities),
        notes=[
            f"{len(frames)} marcos de hoja detectados: {len(plans)} plantas, "
            f"{len(frames) - len(plans)} de detalle/corte/otros."
        ],
    )


def segment_views(
    entities: list[NormalizedEntity],
    detections: list[Detection],
    frames: list[SheetFrame] | None = None,
) -> SheetSegmentation:
    if frames:
        by_frames = _segment_by_frames(entities, detections, frames)
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

    assignment: dict[str, str] = {}
    member_boxes: dict[str, list[BBox]] = {vid: [] for vid in anchor_ids}
    for detection in detections:
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
    dudosas = _desempatar(entities, detections, regions, assignment)
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
    return SheetSegmentation(
        views=list(regions.values()),
        assignment=assignment,
        is_segmented=True,
        npt_levels=npt_levels,
        notes=[
            f"Se detectaron {len(plan_anchors)} vistas de planta y "
            f"{len(anchors) - len(plan_anchors)} regiones de detalle/tabla."
        ]
        + (
            [f"{sum(1 for x in dudosas.values() if x[2])} detecciones en vista dudosa"]
            if any(x[2] for x in dudosas.values())
            else []
        ),
        vistas_dudosas={k: x[2] for k, x in dudosas.items() if x[2]},
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
) -> dict[str, tuple[str, str, str]]:
    """For every detection about as near two titles: (its nearest view, the view its drawing
    gives, the aviso «vista dudosa» when the drawing cannot say). The drawing is the connected
    linework the detection's own entities belong to (walls, outlines, the symbols that touch
    them); its view is the vote of the clearly assigned detections on it."""
    candidatos = {vid: r for vid, r in regions.items() if vid != "far_from_titles"}
    if len(candidatos) < 2:
        return {}
    puntos = _Puntos(entities)
    empatadas: dict[str, tuple[str, str]] = {}
    claras: dict[str, str] = {}
    for detection in detections:
        vid = assignment.get(detection.detection_id)
        if vid not in candidatos:
            continue
        cx, cy = puntos.de(detection)
        cerca = sorted((math.dist((cx, cy), r.anchor), k) for k, r in candidatos.items())
        if cerca[1][0] <= EMPATE_DE_TITULOS * cerca[0][0]:
            empatadas[detection.detection_id] = (cerca[0][1], cerca[1][1])
        else:
            claras[detection.detection_id] = vid
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
    for detection_id, (primera, segunda) in empatadas.items():
        cuenta: dict[str, int] = defaultdict(int)
        for c in dibujo.de(por_id[detection_id]):
            for vid in (primera, segunda):
                cuenta[vid] += votos[c].get(vid, 0)
        total = cuenta[primera] + cuenta[segunda]
        ganadora = max((primera, segunda), key=lambda v: (cuenta[v], v == primera))
        if total >= 2 and cuenta[ganadora] >= _MAYORIA * total:
            salida[detection_id] = (primera, ganadora, "")
        else:
            titulo_a, titulo_b = regions[primera].title, regions[segunda].title
            salida[detection_id] = (
                primera,
                primera,
                f"vista dudosa: casi igual de cerca de «{titulo_a}» y de «{titulo_b}», y su "
                f"dibujo no dice de cuál es ({cuenta[primera]} contra {cuenta[segunda]}); se "
                f"deja en «{titulo_a}»",
            )
    return salida


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
