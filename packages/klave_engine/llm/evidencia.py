"""Where on the sheet a model's reading came from — and the picture of it.

An explanation of an AI reading is worth very little on its own. Bansal et al.
measured that explanations raise the chance a person accepts a machine's
answer *regardless of whether it is correct*, and Eiband et al. found that
explanations with no content at all produce nearly the same trust as real
ones. What does work, per Vasconcelos et al. and Fok & Weld, is an
explanation that makes **verification cheap** — and cheap verification is
rare, because most tasks do not permit it.

Reading a construction drawing is one of the tasks that does. The model says
"K-1 is 15x20 with 4#3"; the sheet either says that in ink or it does not. So
instead of a rationale, each reading carries a crop of the exact place its
mark appears — chosen, when possible, as the place where the mark and the
values the model reported appear *together*, which is the strongest thing a
crop can be. The engineer confirms or rejects by looking, in seconds.

The location is found deterministically, in the drawing's own text entities:
the model is never asked where it looked, because a model's account of its
own attention is exactly the kind of plausible narration this module exists
to avoid.
"""

from __future__ import annotations

import io
import re
from pathlib import Path

from PIL import Image

from klave_engine.detection.frames import SheetFrame
from klave_engine.dxf.entities import NormalizedEntity
from klave_engine.geometry.bbox import BBox

# The crop keeps this much of the sheet around the mark, as a share of the
# frame: enough context to see which cuadro or detalle it sits in.
PAD = 0.05
# Never crop tighter than a fifth of the sheet: a mark is usually the caption
# of a detail drawn above it, and a crop of the caption alone proves nothing.
MIN_SPAN = 0.20
NEAR = 0.06  # "beside the mark", as a share of the frame's diagonal


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text.strip().upper())


def _mark_pattern(mark: str) -> re.Pattern[str] | None:
    """A mark matches as a whole token: K-1 must not match K-15."""
    clean = _normalize(mark)
    if len(clean) < 2:
        return None
    return re.compile(rf"(?<![A-Z0-9]){re.escape(clean)}(?![A-Z0-9])")


def _center(bbox: BBox) -> tuple[float, float]:
    return ((bbox[0] + bbox[2]) / 2, (bbox[1] + bbox[3]) / 2)


def find_mark_region(
    entities: list[NormalizedEntity],
    frame: SheetFrame,
    mark: str,
    corroborating: list[str] | None = None,
) -> BBox | None:
    """The part of the sheet where this mark is written.

    When the reading also carried a section or a rebar string, candidates are
    scored by how many of those appear nearby: the crop that shows the mark
    *and* the values beside it is the one that lets someone check the claim
    rather than merely locate it."""
    pattern = _mark_pattern(mark)
    if pattern is None:
        return None
    fx0, fy0, fx1, fy1 = frame.bbox
    inside = [
        e
        for e in entities
        if e.text
        and e.source_file == frame.source_file
        and fx0 <= _center(e.bbox)[0] <= fx1
        and fy0 <= _center(e.bbox)[1] <= fy1
    ]
    hits = [e for e in inside if pattern.search(_normalize(e.text or ""))]
    if not hits:
        return None

    wanted = [_normalize(v) for v in (corroborating or []) if v and len(_normalize(v)) >= 2]
    if wanted:
        diagonal = ((fx1 - fx0) ** 2 + (fy1 - fy0) ** 2) ** 0.5
        radius = diagonal * NEAR

        def score(hit: NormalizedEntity) -> int:
            hx, hy = _center(hit.bbox)
            neighbourhood = " ".join(
                _normalize(e.text or "")
                for e in inside
                if abs(_center(e.bbox)[0] - hx) <= radius
                and abs(_center(e.bbox)[1] - hy) <= radius
            )
            return sum(1 for value in wanted if value in neighbourhood)

        hits.sort(key=score, reverse=True)

    best = hits[0]
    fw, fh = fx1 - fx0, fy1 - fy0
    cx, cy = _center(best.bbox)
    half_w = max((best.bbox[2] - best.bbox[0]) / 2 + PAD * fw, MIN_SPAN * fw / 2)
    half_h = max((best.bbox[3] - best.bbox[1]) / 2 + PAD * fh, MIN_SPAN * fh / 2)
    x0 = max(fx0, min(cx - half_w, fx1 - 2 * half_w))
    y0 = max(fy0, min(cy - half_h, fy1 - 2 * half_h))
    return (x0, y0, min(fx1, x0 + 2 * half_w), min(fy1, y0 + 2 * half_h))


def crop_from_frame_render(
    render_path: Path, frame: SheetFrame, region: BBox, long_side_px: int = 2600
) -> bytes | None:
    """Cut the region out of the frame's cached image, in that image's own
    pixel space. Returns None when the render was made with other settings —
    a stale crop would be worse than none."""
    from klave_engine.llm.render import region_transform

    transform = region_transform(frame.bbox, long_side_px)
    try:
        image = Image.open(render_path).convert("RGB")
    except OSError:
        return None
    if image.size != (transform.width, transform.height):
        return None
    left, top = transform.px((region[0], region[3]))
    right, bottom = transform.px((region[2], region[1]))
    crop = image.crop((int(left), int(top), int(right), int(bottom)))
    if crop.width < 8 or crop.height < 8:
        return None
    buffer = io.BytesIO()
    crop.save(buffer, format="PNG", optimize=True)
    return buffer.getvalue()
