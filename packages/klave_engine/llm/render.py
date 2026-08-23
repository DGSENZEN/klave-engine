"""Render a sheet (or one frame of it) to a PNG an engineer — or a vision
model — can read.

The rules read geometry; a picture is how a person reads a plan: cuadros,
notes, marks next to their elements, legends. The renderer draws the
normalized entities of one file inside a bbox — linework by layer in dark
ink, hatches faint, texts at their size, cotas as their spans — onto a
white page at a resolution where a 10 cm letter is still legible.
"""

import io
import math
from dataclasses import dataclass

from PIL import Image, ImageDraw, ImageFont

from klave_engine.dxf.entities import EntityType, NormalizedEntity
from klave_engine.geometry.bbox import BBox

_FONT_CANDIDATES = (
    "/System/Library/Fonts/Supplemental/Arial.ttf",
    "/System/Library/Fonts/Helvetica.ttc",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
)


@dataclass
class Highlight:
    """A shape to draw over the render: a polygon (≥3 points) or a bbox."""

    points: list[tuple[float, float]]
    color: tuple[int, int, int] = (220, 38, 38)
    label: str = ""


@dataclass
class RegionTransform:
    x0: float
    y0: float
    scale: float
    width: int
    height: int

    def px(self, p: tuple[float, float]) -> tuple[float, float]:
        return ((p[0] - self.x0) * self.scale, self.height - (p[1] - self.y0) * self.scale)


def region_transform(bbox: BBox, long_side_px: int, margin: float = 0.02) -> RegionTransform:
    """The drawing→pixel mapping `render_region` uses for a bbox, so an
    overlay can be drawn on a cached render without re-rendering it."""
    x0, y0, x1, y1 = bbox
    dx, dy = max(x1 - x0, 1e-9), max(y1 - y0, 1e-9)
    x0, x1 = x0 - dx * margin, x1 + dx * margin
    y0, y1 = y0 - dy * margin, y1 + dy * margin
    dx, dy = x1 - x0, y1 - y0
    scale = long_side_px / max(dx, dy)
    return RegionTransform(
        x0=x0, y0=y0, scale=scale, width=max(int(dx * scale), 16), height=max(int(dy * scale), 16)
    )


def draw_highlights(
    image: Image.Image, transform: RegionTransform, highlights: list[Highlight]
) -> None:
    """Translucent fill + strong outline per shape; tiny shapes get a marker
    so a 15 cm castillo is still findable on a 40 m sheet."""
    if not highlights:
        return
    overlay = Image.new("RGBA", image.size, (255, 255, 255, 0))
    draw = ImageDraw.Draw(overlay)
    marker = max(int(min(image.size) * 0.012), 6)
    for h in highlights:
        pts = [transform.px(p) for p in h.points]
        if not pts:
            continue
        xs, ys = [p[0] for p in pts], [p[1] for p in pts]
        w, hgt = max(xs) - min(xs), max(ys) - min(ys)
        fill = (*h.color, 70)
        if len(pts) >= 3 and max(w, hgt) >= marker:
            draw.polygon(pts, fill=fill, outline=(*h.color, 255), width=3)
        elif max(w, hgt) >= marker:
            draw.rectangle(
                (min(xs), min(ys), max(xs), max(ys)), fill=fill, outline=(*h.color, 255), width=3
            )
        else:
            cx, cy = (min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2
            draw.ellipse(
                (cx - marker, cy - marker, cx + marker, cy + marker),
                fill=fill, outline=(*h.color, 255), width=3,
            )
        if h.label:
            draw.text(
                (min(xs), min(ys) - 2), h.label, fill=(*h.color, 255), font=_font(marker + 4),
                anchor="lb",
            )
    image.paste(Image.alpha_composite(image.convert("RGBA"), overlay).convert("RGB"))


@dataclass
class RenderedSheet:
    png: bytes
    width: int
    height: int
    bbox: BBox
    scale: float  # pixels per drawing unit
    entity_count: int


def _font(size_px: int) -> ImageFont.ImageFont | ImageFont.FreeTypeFont:
    size = max(int(size_px), 6)
    for path in _FONT_CANDIDATES:
        try:
            return ImageFont.truetype(path, size)
        except OSError:
            continue
    return ImageFont.load_default(size=size)


def render_region(
    entities: list[NormalizedEntity],
    bbox: BBox,
    *,
    long_side_px: int = 2600,
    margin: float = 0.02,
    min_text_px: float = 5.0,
    highlights: list[Highlight] | None = None,
) -> RenderedSheet:
    """Draw every entity whose bbox intersects `bbox` into a PNG."""
    transform = region_transform(bbox, long_side_px, margin)
    x0, y0, scale = transform.x0, transform.y0, transform.scale
    width, height = transform.width, transform.height
    x1, y1 = x0 + width / scale, y0 + height / scale
    image = Image.new("RGB", (width, height), "white")
    draw = ImageDraw.Draw(image)
    px = transform.px

    def visible(e: NormalizedEntity) -> bool:
        b = e.bbox
        return b[0] <= x1 and b[2] >= x0 and b[1] <= y1 and b[3] >= y0

    ink = (30, 30, 30)
    faint = (150, 150, 150)
    hatch = (205, 205, 205)
    count = 0
    texts: list[NormalizedEntity] = []
    for e in entities:
        if not visible(e):
            continue
        count += 1
        props = e.properties or {}
        if e.entity_type == EntityType.hatch and e.points and len(e.points) >= 3:
            draw.polygon([px(p) for p in e.points], fill=hatch, outline=faint)
        elif e.entity_type in (EntityType.line, EntityType.polyline) and e.points:
            pts = [px(p) for p in e.points]
            if len(pts) >= 2:
                if e.entity_type == EntityType.polyline and e.is_closed:
                    pts.append(pts[0])
                draw.line(pts, fill=ink, width=1)
        elif e.entity_type == EntityType.circle:
            c, r = props.get("center"), props.get("radius")
            if c and r:
                cx, cy = px((c[0], c[1]))
                rp = r * scale
                draw.ellipse((cx - rp, cy - rp, cx + rp, cy + rp), outline=ink, width=1)
        elif e.entity_type == EntityType.arc:
            c, r = props.get("center"), props.get("radius")
            if c and r:
                cx, cy = px((c[0], c[1]))
                rp = r * scale
                a0, a1 = float(props.get("start_angle", 0)), float(props.get("end_angle", 360))
                # PIL measures angles clockwise from 3 o'clock on a y-down canvas.
                draw.arc((cx - rp, cy - rp, cx + rp, cy + rp), start=-a1, end=-a0, fill=ink)
        elif e.entity_type == EntityType.dimension:
            segment = props.get("measured_segment")
            if segment and len(segment) == 2:
                draw.line([px(tuple(segment[0])), px(tuple(segment[1]))], fill=faint, width=1)
                label = props.get("display_text")
                if label:
                    mx = (segment[0][0] + segment[1][0]) / 2
                    my = (segment[0][1] + segment[1][1]) / 2
                    draw.text(px((mx, my)), str(label), fill=faint, font=_font(10), anchor="mb")
        elif e.is_textual and e.text:
            texts.append(e)
    # Texts last, over the linework.
    for e in texts:
        props = e.properties or {}
        height_px = float(props.get("height") or (e.bbox[3] - e.bbox[1])) * scale
        if height_px < min_text_px:
            continue
        insert = props.get("insert") or (e.bbox[0], e.bbox[1])
        x, y = px((insert[0], insert[1]))
        content = " ".join(str(e.text).split())[:120]
        font = _font(int(height_px * 1.15))
        rotation = float(e.rotation or 0.0)
        if abs(rotation) < 1 or abs(rotation - 360) < 1:
            draw.text((x, y), content, fill=ink, font=font, anchor="ls")
        else:
            # Rotated text: draw on its own tile and paste rotated about the insert.
            tw = int(font.getlength(content)) + 4
            th = int(height_px * 1.4) + 4
            tile = Image.new("RGBA", (max(tw, 1), max(th, 1)), (255, 255, 255, 0))
            ImageDraw.Draw(tile).text((0, th - 2), content, fill=ink, font=font, anchor="ls")
            rotated = tile.rotate(rotation, expand=True, resample=Image.Resampling.BICUBIC)
            rad = math.radians(rotation)
            ox = -rotated.width / 2 + (tw / 2) * math.cos(rad)
            oy = -rotated.height / 2 - (tw / 2) * math.sin(rad)
            image.paste(rotated, (int(x + ox), int(y + oy)), rotated)
    if highlights:
        draw_highlights(image, transform, highlights)
    buffer = io.BytesIO()
    image.save(buffer, format="PNG", optimize=True)
    return RenderedSheet(
        png=buffer.getvalue(), width=width, height=height, bbox=(x0, y0, x1, y1),
        scale=scale, entity_count=count,
    )
