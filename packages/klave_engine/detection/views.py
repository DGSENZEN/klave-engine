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

import re
import statistics
from enum import StrEnum

from pydantic import BaseModel, Field

from klave_engine.detection.frames import SheetFrame
from klave_engine.detection.results import Detection
from klave_engine.dxf.entities import NormalizedEntity
from klave_engine.geometry.bbox import BBox, bbox_center, bbox_contains_point, bbox_union_all

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
    anchor: tuple[float, float]
    bbox: BBox | None = None
    detection_ids: list[str] = Field(default_factory=list)
    detection_counts: dict[str, int] = Field(default_factory=dict)


class SheetSegmentation(BaseModel):
    views: list[ViewRegion]
    assignment: dict[str, str]  # detection_id -> view_id
    is_segmented: bool  # True when ≥2 plan views were found
    npt_levels: list[float] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)

    def plan_views(self) -> list[ViewRegion]:
        return [v for v in self.views if v.kind == ViewKind.plan]

    def foundation_views(self) -> list[ViewRegion]:
        return [v for v in self.plan_views() if v.level_key == "cimentacion"]

    def superstructure_views(self) -> list[ViewRegion]:
        return [v for v in self.plan_views() if v.level_key != "cimentacion"]

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
                point=bbox_center(entity.bbox),
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
    usable = [f for f in frames if f.kind in ("plan", "excluded")]
    if len(usable) < 2 or not any(f.kind == "plan" for f in usable):
        return None
    regions: dict[str, ViewRegion] = {}
    for frame in frames:
        kind = ViewKind.plan if frame.kind == "plan" else ViewKind.excluded
        regions[frame.frame_id] = ViewRegion(
            view_id=frame.frame_id,
            title=f"{frame.code} · {frame.title}".strip(" ·") or frame.code,
            kind=kind,
            level_key=frame.level_key if kind == ViewKind.plan else None,
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
        center = bbox_center(detection.bbox)
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
    return SheetSegmentation(
        views=list(regions.values()),
        assignment=assignment,
        is_segmented=True,
        npt_levels=_npt_levels(entities),
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

    assignment: dict[str, str] = {}
    member_boxes: dict[str, list[BBox]] = {vid: [] for vid in anchor_ids}
    for detection in detections:
        cx, cy = bbox_center(detection.bbox)
        nearest_id = min(
            anchor_ids,
            key=lambda vid: (regions[vid].anchor[0] - cx) ** 2
            + (regions[vid].anchor[1] - cy) ** 2,
        )
        assignment[detection.detection_id] = nearest_id
        region = regions[nearest_id]
        region.detection_ids.append(detection.detection_id)
        region.detection_counts[detection.detection_type.value] = (
            region.detection_counts.get(detection.detection_type.value, 0) + 1
        )
        member_boxes[nearest_id].append(detection.bbox)

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
        ],
    )
