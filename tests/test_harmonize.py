"""Per-sheet units: a file in centimetres joins a project in metres scaled."""

from klave_engine.dxf.entities import EntityType, EvidencePacket, NormalizedEntity
from klave_engine.dxf.harmonize import harmonize_units, scale_entity


def _line(entity_id, source, x0, y0, x1, y1, **props):
    bbox = (x0, y0, x1, y1)
    return NormalizedEntity(
        entity_id=entity_id, entity_type=EntityType.line, source_file=source, layer="L",
        bbox=bbox, points=[(x0, y0), (x1, y1)], raw_handle=entity_id, properties=props,
        evidence=EvidencePacket(source=source, method="t", entity_ids=[entity_id], bbox=bbox,
                                confidence=1.0),
    )


def test_scale_entity_scales_geometry_and_keeps_cota_text_consistent():
    e = _line("d", "a.dxf", 0, 0, 100, 0, measurement=100.0, display_value=1.0, dimlfac=0.01,
              measured_segment=[(0, 0), (100, 0)], radius=5.0, height=2.5, insert=(10, 20))
    scale_entity(e, 0.01)
    assert e.bbox == (0, 0, 1.0, 0) and e.points == [(0, 0), (1.0, 0)]
    assert e.evidence.bbox == (0, 0, 1.0, 0)
    p = e.properties
    assert p["measurement"] == 1.0 and p["measured_segment"] == [(0, 0), (1.0, 0)]
    assert p["radius"] == 0.05 and p["height"] == 0.025 and p["insert"] == (0.1, 0.2)
    # display = measurement × dimlfac still holds after scaling.
    assert abs(p["measurement"] * p["dimlfac"] - p["display_value"]) < 1e-9


def test_heaviest_reliable_file_sets_the_project_unit_and_others_scale():
    metres = [_line(f"m{i}", "02 ESTRUCTURAL.dxf", 0, i, 12.0, i) for i in range(40)]
    centimetres = [_line(f"c{i}", "05 DETALLE.dxf", 0, i, 1200.0, i) for i in range(5)]
    inches = [_line("i0", "00 INDICE.dxf", 0, 0, 400.0, 0)]
    units, per_file = harmonize_units([
        ("00 INDICE.dxf", 1, inches),
        ("02 ESTRUCTURAL.dxf", 6, metres),
        ("05 DETALLE.dxf", 5, centimetres),
    ])
    assert units.unit == "m" and units.source == "dxf_header"
    scales = {f.source_file: f.scale for f in per_file}
    assert scales["02 ESTRUCTURAL.dxf"] == 1.0
    assert abs(scales["05 DETALLE.dxf"] - 0.01) < 1e-12
    assert abs(scales["00 INDICE.dxf"] - 0.0254) < 1e-12
    assert centimetres[0].bbox[2] == 12.0  # 1200 cm → 12 m, in place
    assert any("00 INDICE" in n and "×0.0254" in n for n in units.notes)
