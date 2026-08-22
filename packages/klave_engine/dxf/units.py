"""Drawing unit detection.

Real drawings usually declare their unit in the DXF header ($INSUNITS).
When the header is missing or unitless, a conservative heuristic based on
annotation text heights is applied. The detected unit drives detector
threshold presets and lets quantity/cost reports speak in real units.
"""

import statistics

from pydantic import BaseModel, Field

from klave_engine.dxf.entities import NormalizedEntity
from klave_engine.geometry.bbox import BBox

INSUNITS_TO_UNIT = {
    1: "in",
    2: "ft",
    4: "mm",
    5: "cm",
    6: "m",
}

METERS_FACTOR = {
    "m": 1.0,
    "cm": 0.01,
    "mm": 0.001,
    "ft": 0.3048,
    "in": 0.0254,
}

UNKNOWN_UNIT = "drawing_units"


class DrawingUnits(BaseModel):
    unit: str = UNKNOWN_UNIT  # "m" | "cm" | "mm" | "ft" | "in" | "drawing_units"
    source: str = "unknown"  # "dxf_header" | "text_height_heuristic" | "unknown"
    confidence: float = 0.0
    notes: list[str] = Field(default_factory=list)

    @property
    def known(self) -> bool:
        return self.unit != UNKNOWN_UNIT

    def to_meters(self) -> float | None:
        return METERS_FACTOR.get(self.unit)


def _unit_from_factor(factor_to_m: float) -> str | None:
    """The unit whose metre factor matches within 5 %."""
    for unit, per_unit in METERS_FACTOR.items():
        if abs(factor_to_m - per_unit) <= 0.05 * per_unit:
            return unit
    return None


def _votes_from_dimensions(entities: list[NormalizedEntity]) -> dict[str, int]:
    """Displayed cota vs measured length: '2.50' over 250 drawing units is
    centimetres. Displayed values with decimals under 100 read as metres;
    integers between 5 and 500 read as centimetres."""
    votes: dict[str, int] = {}
    for entity in entities:
        if entity.entity_type.value != "dimension":
            continue
        measured = entity.properties.get("measurement")
        shown = entity.properties.get("display_value")
        lfac = float(entity.properties.get("dimlfac") or 1.0)
        if not measured or not shown or measured <= 0 or lfac != 1.0:
            continue
        text = str(entity.properties.get("display_text", ""))
        has_decimals = "." in text or "," in text
        if has_decimals and shown < 100:
            shown_m = shown
        elif not has_decimals and 5 <= shown <= 500:
            shown_m = shown / 100.0
        else:
            continue
        unit = _unit_from_factor(shown_m / float(measured))
        if unit:
            votes[unit] = votes.get(unit, 0) + 1
    return votes


def _vote_from_extent(extent: BBox | None) -> tuple[str, str] | None:
    """A building's model extent is tens of metres: 5–500 in m, 500–50 000
    in cm, 50 000–5 000 000 in mm."""
    if extent is None:
        return None
    diagonal = ((extent[2] - extent[0]) ** 2 + (extent[3] - extent[1]) ** 2) ** 0.5
    if 5 <= diagonal < 500:
        return "m", f"extensión del modelo {diagonal:.0f} u.dib."
    if 500 <= diagonal < 50_000:
        return "cm", f"extensión del modelo {diagonal:.0f} u.dib."
    if 50_000 <= diagonal < 5_000_000:
        return "mm", f"extensión del modelo {diagonal:.0f} u.dib."
    return None


def _vote_from_text_heights(entities: list[NormalizedEntity]) -> tuple[str, str] | None:
    heights = [
        float(e.properties["height"])
        for e in entities
        if e.is_textual and "height" in e.properties and float(e.properties["height"]) > 0
    ]
    if len(heights) < 10:
        return None
    median = statistics.median(heights)
    # Plotted annotation text is ~2-3 mm on paper; at common structural
    # scales that lands near 0.05-0.30 drawing units in meters, 5-30 in
    # centimetres and 50-300 in millimeters.
    if median <= 0.5:
        return "m", f"altura mediana de texto {median:.3f}"
    if 5.0 <= median < 50.0:
        return "cm", f"altura mediana de texto {median:.1f}"
    if 50.0 <= median <= 500.0:
        return "mm", f"altura mediana de texto {median:.1f}"
    return None


def detect_units(
    insunits: int | None,
    entities: list[NormalizedEntity],
    extent: BBox | None = None,
) -> DrawingUnits:
    """Units from the DXF header; otherwise from the cotas the engineer
    wrote, the model's extent, and text heights — voting, with the
    confidence the agreement earns."""
    if insunits in INSUNITS_TO_UNIT:
        unit = INSUNITS_TO_UNIT[insunits]
        return DrawingUnits(
            unit=unit,
            source="dxf_header",
            confidence=0.9,
            notes=[f"DXF header $INSUNITS={insunits} declares '{unit}'"],
        )

    dimension_votes = _votes_from_dimensions(entities)
    total_dims = sum(dimension_votes.values())
    if total_dims >= 5:
        unit, count = max(dimension_votes.items(), key=lambda kv: kv[1])
        if count / total_dims >= 0.8:
            return DrawingUnits(
                unit=unit,
                source="dimensions",
                confidence=0.85,
                notes=[
                    f"{count} de {total_dims} cotas muestran valores coherentes con "
                    f"'{unit}' (valor mostrado ÷ longitud medida)"
                ],
            )

    weak: list[tuple[str, str]] = []
    for vote in (_vote_from_extent(extent), _vote_from_text_heights(entities)):
        if vote:
            weak.append(vote)
    if dimension_votes:
        unit, count = max(dimension_votes.items(), key=lambda kv: kv[1])
        weak.append((unit, f"{count} cotas coherentes con '{unit}'"))
    if weak:
        tally: dict[str, list[str]] = {}
        for unit, reason in weak:
            tally.setdefault(unit, []).append(reason)
        unit, reasons = max(tally.items(), key=lambda kv: len(kv[1]))
        agreeing = len(reasons)
        confidence = 0.75 if agreeing >= 2 else 0.55
        return DrawingUnits(
            unit=unit,
            source="heuristics",
            confidence=confidence,
            notes=[f"Indicios: {'; '.join(reasons)}"]
            + ([f"Otras lecturas: {', '.join(u for u in tally if u != unit)}"]
               if len(tally) > 1 else []),
        )

    return DrawingUnits(
        unit=UNKNOWN_UNIT,
        source="unknown",
        confidence=0.0,
        notes=["Sin encabezado de unidades, sin cotas legibles y sin extensión concluyente"],
    )
