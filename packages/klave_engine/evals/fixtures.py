"""Deterministic synthetic DXF fixtures with known gold labels.

The demo drawing contains a known grid, column tags, footings, a beam, a slab,
a wall pair, and detail references (one resolved, one dangling). Tests and the
evaluation suite both build on this fixture, so its geometry is deliberate:
every detection below is engineered, not accidental.
"""

from pathlib import Path

import ezdxf


def build_demo_dxf(path: Path) -> Path:
    """Write the S-101 demo sheet. Extent is roughly (0, 0) to (1010, 810)."""
    doc = ezdxf.new("R2018")
    # Pin the fixture to unitless so unit-aware detector presets never apply
    # (ezdxf defaults new documents to meters).
    doc.header["$INSUNITS"] = 0
    msp = doc.modelspace()

    def text(value: str, insert: tuple[float, float], layer: str) -> None:
        msp.add_text(value, dxfattribs={"layer": layer, "height": 5.0}).set_placement(insert)

    # Grid: two horizontal (A at y=200, B at y=600), two vertical (1 at x=200, 2 at x=500).
    msp.add_line((0, 200), (1000, 200), dxfattribs={"layer": "S-GRID"})
    msp.add_line((0, 600), (1000, 600), dxfattribs={"layer": "S-GRID"})
    msp.add_line((200, 0), (200, 800), dxfattribs={"layer": "S-GRID"})
    msp.add_line((500, 0), (500, 800), dxfattribs={"layer": "S-GRID"})
    text("A", (5, 202), "S-GRID")
    text("B", (5, 602), "S-GRID")
    text("1", (202, 2), "S-GRID")
    text("2", (502, 2), "S-GRID")

    # Columns at B/1 and A/2: circle marker + tag text + square footing.
    msp.add_circle((200, 600), 8, dxfattribs={"layer": "S-COL"})
    text("C1", (210, 608), "S-COL-TAG")
    msp.add_lwpolyline(
        [(170, 570), (230, 570), (230, 630), (170, 630)],
        close=True,
        dxfattribs={"layer": "S-FOOTING"},
    )
    msp.add_circle((500, 200), 8, dxfattribs={"layer": "S-COL"})
    text("C2", (510, 208), "S-COL-TAG")
    msp.add_lwpolyline(
        [(470, 170), (530, 170), (530, 230), (470, 230)],
        close=True,
        dxfattribs={"layer": "S-FOOTING"},
    )

    # Duplicate C1 far from any grid intersection (risk fixture).
    text("C1", (900, 700), "S-COL-TAG")

    # Beam B1: 300-unit line with its tag text just above it.
    msp.add_line((550, 400), (850, 400), dxfattribs={"layer": "S-BEAM"})
    text("B1", (690, 405), "S-BEAM")

    # Slab region: large closed polyline (area 120000).
    msp.add_lwpolyline(
        [(600, 500), (1000, 500), (1000, 800), (600, 800)],
        close=True,
        dxfattribs={"layer": "S-SLAB"},
    )

    # Wall: paired parallel lines, 200 long, 10 apart.
    msp.add_line((50, 700), (250, 700), dxfattribs={"layer": "S-WALL"})
    msp.add_line((50, 710), (250, 710), dxfattribs={"layer": "S-WALL"})

    # Detail references: one dangling (S-501 missing), one resolved (S-101 = this sheet).
    text("5/S-501", (700, 100), "S-ANNO")
    text("2/S-101", (700, 140), "S-ANNO")

    path.parent.mkdir(parents=True, exist_ok=True)
    doc.saveas(str(path))
    return path


def write_demo_project(project_root: Path) -> list[Path]:
    """Create the full demo project folder with its drawings."""
    return [build_demo_dxf(project_root / "drawings" / "S-101.dxf")]


# Gold labels for the demo fixture. Detection labels are matched as multisets.
DEMO_GOLD: dict = {
    "detections": {
        "grid_line": ["A", "B", "1", "2"],
        "grid_intersection": ["A/1", "A/2", "B/1", "B/2"],
        "column_tag": ["C1", "C2", "C1"],
        "footing": ["F1", "F2"],
        "beam_tag": ["B1"],
        "slab_region": ["SLAB1"],
        "wall": ["W1"],
        "detail_reference": ["5/S-501", "2/S-101"],
    },
    "semantic_node_counts": {
        "grid_line": 4,
        "grid_intersection": 4,
        "column_tag": 3,
        "footing": 2,
        "beam_tag": 1,
        "slab_region": 1,
        "wall": 1,
        "detail_reference": 2,
    },
    "quantities": {
        "column_tag_count": 3,
        "footing_count": 2,
        "beam_tag_count": 1,
        "estimated_beam_length": 300.0,
        "wall_count": 1,
        "estimated_wall_length": 200.0,
        "slab_region_count": 1,
        "estimated_slab_area": 120000.0,
        "detail_reference_count": 2,
        "unresolved_detail_reference_count": 1,
        # Every demo element sits on a semantic layer, so the evidence-fusion
        # model scores them all ≥0.7; the low-confidence path is covered by a
        # targeted unit test instead (test_risks.py).
        "low_confidence_detection_count": 0,
    },
    "expected_risk_types": [
        "unresolved_detail_reference",
        "column_tag_without_grid",
        "duplicate_column_tag",
        "unknown_drawing_units",
    ],
}
