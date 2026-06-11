"""Drawing unit detection.

Real drawings usually declare their unit in the DXF header ($INSUNITS).
When the header is missing or unitless, a conservative heuristic based on
annotation text heights is applied. The detected unit drives detector
threshold presets and lets quantity/cost reports speak in real units.
"""

import statistics

from pydantic import BaseModel, Field

from klave_engine.dxf.entities import NormalizedEntity

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


def detect_units(
    insunits: int | None,
    entities: list[NormalizedEntity],
) -> DrawingUnits:
    """Detect drawing units from the DXF header, else from text heights."""
    if insunits in INSUNITS_TO_UNIT:
        unit = INSUNITS_TO_UNIT[insunits]
        return DrawingUnits(
            unit=unit,
            source="dxf_header",
            confidence=0.9,
            notes=[f"DXF header $INSUNITS={insunits} declares '{unit}'"],
        )

    heights = [
        float(e.properties["height"])
        for e in entities
        if e.is_textual and "height" in e.properties and float(e.properties["height"]) > 0
    ]
    if len(heights) >= 10:
        median = statistics.median(heights)
        # Plotted annotation text is ~2-3 mm on paper; at common structural
        # scales that lands near 0.05-0.30 drawing units in meters and
        # 50-300 in millimeters.
        if median <= 0.5:
            return DrawingUnits(
                unit="m",
                source="text_height_heuristic",
                confidence=0.6,
                notes=[f"Median text height {median:.3f} is consistent with meters"],
            )
        if 50.0 <= median <= 500.0:
            return DrawingUnits(
                unit="mm",
                source="text_height_heuristic",
                confidence=0.6,
                notes=[f"Median text height {median:.1f} is consistent with millimeters"],
            )

    return DrawingUnits(
        unit=UNKNOWN_UNIT,
        source="unknown",
        confidence=0.0,
        notes=["No unit header and text heights are inconclusive"],
    )
