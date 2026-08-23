"""Croquis for the números generadores: the planta with the elements that
produce a concept's quantity marked on it.

A generador without a croquis is a list of labels; with one, the reviewer
sees *where* the 176 castillos are and which tableros the losa counts. One
image per (concept, planta): the sheet's cached render with the line's
detections highlighted, cropped to where they are, cached per detection
run under the control dir (croquis/<run_id>/<code>__<view>.png).
"""

from __future__ import annotations

import io
from dataclasses import dataclass
from pathlib import Path

from PIL import Image

from klave_engine.costing.models import BoqLine
from klave_engine.detection.frames import SheetFrame
from klave_engine.detection.results import Detection
from klave_engine.detection.views import SheetSegmentation
from klave_engine.dxf.entities import NormalizedEntity
from klave_engine.geometry.bbox import BBox
from klave_engine.llm.render import (
    Highlight,
    draw_highlights,
    region_transform,
    render_region,
)
from klave_engine.llm.service import _load_entities, render_frame_png

CROQUIS_DIRNAME = "croquis"
FRAME_RENDER_PX = 2600  # must match render_frame_png's long side
CROQUIS_PX = 1600
PAD = 0.12  # padding around the elements, as a share of the sheet's size
MAX_PER_LINE = 8


@dataclass
class Croquis:
    view_id: str
    title: str
    path: Path
    count: int


def _highlight(detection: Detection) -> Highlight:
    polygon = detection.properties.get("polygon")
    if isinstance(polygon, list) and len(polygon) >= 3:
        pts = [(float(p[0]), float(p[1])) for p in polygon]
    else:
        x0, y0, x1, y1 = detection.bbox
        pts = [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]
    return Highlight(points=pts, label=detection.mark or "")


def _union(dets: list[Detection]) -> BBox:
    return (
        min(d.bbox[0] for d in dets), min(d.bbox[1] for d in dets),
        max(d.bbox[2] for d in dets), max(d.bbox[3] for d in dets),
    )


def _crop_box(union: BBox, frame: BBox) -> BBox:
    """The elements' extent padded, never beyond the sheet, never smaller
    than a third of it — context is what makes a croquis readable."""
    fx0, fy0, fx1, fy1 = frame
    fw, fh = fx1 - fx0, fy1 - fy0
    ux0, uy0, ux1, uy1 = union
    w = max(ux1 - ux0 + 2 * PAD * fw, fw / 3)
    h = max(uy1 - uy0 + 2 * PAD * fh, fh / 3)
    cx, cy = (ux0 + ux1) / 2, (uy0 + uy1) / 2
    x0, y0 = max(fx0, cx - w / 2), max(fy0, cy - h / 2)
    x1, y1 = min(fx1, x0 + w), min(fy1, y0 + h)
    x0, y0 = max(fx0, x1 - w), max(fy0, y1 - h)
    return (x0, y0, x1, y1)


def _downscale(image: Image.Image, long_side_px: int) -> Image.Image:
    longest = max(image.size)
    if longest <= long_side_px:
        return image
    ratio = long_side_px / longest
    return image.resize(
        (max(int(image.width * ratio), 1), max(int(image.height * ratio), 1)),
        Image.Resampling.LANCZOS,
    )


def _from_frame_render(
    artifact_dir: Path, control_dir: Path, frame: SheetFrame, dets: list[Detection]
) -> Image.Image | None:
    base_path = render_frame_png(
        artifact_dir, control_dir, frame.code, long_side_px=FRAME_RENDER_PX
    )
    if base_path is None:
        return None
    transform = region_transform(frame.bbox, FRAME_RENDER_PX)
    image = Image.open(base_path).convert("RGB")
    if image.size != (transform.width, transform.height):
        return None  # rendered with other settings; fall back to a fresh render
    draw_highlights(image, transform, [_highlight(d) for d in dets])
    cx0, cy0, cx1, cy1 = _crop_box(_union(dets), frame.bbox)
    left, top = transform.px((cx0, cy1))
    right, bottom = transform.px((cx1, cy0))
    return image.crop((int(left), int(top), int(right), int(bottom)))


def _from_entities(
    entities: list[NormalizedEntity], region: BBox, dets: list[Detection]
) -> Image.Image:
    rendered = render_region(
        entities, region, long_side_px=CROQUIS_PX, highlights=[_highlight(d) for d in dets]
    )
    return Image.open(io.BytesIO(rendered.png)).convert("RGB")


def croquis_for_line(
    artifact_dir: Path,
    control_dir: Path,
    line: BoqLine,
    detections_by_id: dict[str, Detection],
    segmentation: SheetSegmentation | None,
    frames: list[SheetFrame],
    *,
    run_id: str,
    long_side_px: int = CROQUIS_PX,
) -> list[Croquis]:
    """One croquis per planta holding the line's elements (cached)."""
    dets = [detections_by_id[i] for i in line.source_detections if i in detections_by_id]
    if not dets:
        return []
    assignment = segmentation.assignment if segmentation else {}
    titles = {v.view_id: v.title for v in segmentation.views} if segmentation else {}
    groups: dict[str, list[Detection]] = {}
    for d in dets:
        groups.setdefault(assignment.get(d.detection_id, "all"), []).append(d)
    frames_by_id = {f.frame_id: f for f in frames}
    out_dir = control_dir / CROQUIS_DIRNAME / run_id
    out_dir.mkdir(parents=True, exist_ok=True)
    entities: list[NormalizedEntity] | None = None
    out: list[Croquis] = []
    ordered = sorted(groups.items(), key=lambda kv: -len(kv[1]))[:MAX_PER_LINE]
    for view_id, group in ordered:
        target = out_dir / f"{line.concept_code}__{view_id}.png"
        title = titles.get(view_id, "Plano completo" if view_id == "all" else view_id)
        if not target.exists():
            image: Image.Image | None = None
            frame = frames_by_id.get(view_id)
            if frame is not None:
                image = _from_frame_render(artifact_dir, control_dir, frame, group)
            if image is None:
                if entities is None:
                    entities = _load_entities(artifact_dir)
                source = group[0].evidence.source
                own = [e for e in entities if not source or e.source_file == source] or entities
                region = _crop_box(_union(group), frame.bbox if frame else _extent(own))
                image = _from_entities(own, region, group)
            _downscale(image, long_side_px).save(target, format="PNG", optimize=True)
        out.append(Croquis(view_id=view_id, title=title, path=target, count=len(group)))
    return out


def _extent(entities: list[NormalizedEntity]) -> BBox:
    return (
        min(e.bbox[0] for e in entities), min(e.bbox[1] for e in entities),
        max(e.bbox[2] for e in entities), max(e.bbox[3] for e in entities),
    )
