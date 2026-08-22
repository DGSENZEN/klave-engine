"""Trabe marks: Mexican patterns and the line a mark belongs to."""

import ezdxf
from klave_engine.detection.beam_detector import BeamDetectorConfig, detect_beams
from klave_engine.detection.text_patterns import TextPatternConfig, match_category
from klave_engine.dxf.parser import DxfParser
from klave_engine.geometry.spatial_index import SpatialIndex


def test_mexican_trabe_marks_match():
    config = TextPatternConfig()
    for mark in ("T-1", "T-11", "T3", "TL-1", "TR-2", "TP-4A", "CT-1", "T2-7", "TB-1"):
        assert match_category(mark, config, "beam_tag"), mark
    for not_mark in ("T", "TE", "TEXTO", "TL", "4"):
        assert match_category(not_mark, config, "beam_tag") is None, not_mark


def test_beam_prefers_its_layer_over_a_nearer_axis(tmp_path):
    doc = ezdxf.new("R2010")
    msp = doc.modelspace()
    # A grid axis passes 0.2 from the mark; the trabe line is 0.6 away.
    msp.add_line((0, 0.2), (100, 0.2), dxfattribs={"layer": "S-GRID"})
    msp.add_line((0, -0.6), (5, -0.6), dxfattribs={"layer": "E-TRABES"})
    msp.add_line((0, -0.3), (4, -0.3), dxfattribs={"layer": "A-WALL"})
    msp.add_text("T-7", height=0.2).set_placement((2, 0))
    path = tmp_path / "beams.dxf"
    doc.saveas(path)
    drawing = DxfParser().parse_file(path)
    index = SpatialIndex(drawing.entities)
    config = BeamDetectorConfig(line_search_radius=1.0, min_beam_length=1.5, max_beam_length=15)

    output = detect_beams(drawing.entities, index, config)
    assert [d.label for d in output.detections] == ["T-7"]
    beam = output.detections[0]
    assert beam.properties["span_layer"] == "E-TRABES"
    assert beam.properties["estimated_span_length"] == 5.0
    assert any("capa E-TRABES" in note for note in beam.evidence.notes)
