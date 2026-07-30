"""Label taxonomy: family classification, stable display labels, descriptions."""

import random

from klave_engine.detection.results import Detection, DetectionType, make_detection
from klave_engine.detection.taxonomy import (
    Family,
    classify_family,
    describe,
    enrich_detections,
)


def _det(
    det_id: str,
    dtype: DetectionType,
    label: str,
    bbox: tuple[float, float, float, float] = (0.0, 0.0, 1.0, 1.0),
    notes: list[str] | None = None,
    properties: dict | None = None,
    confidence: float = 0.84,
) -> Detection:
    return make_detection(
        det_id,
        dtype,
        label,
        bbox,
        confidence,
        ["e1"],
        "column_tag_regex_near_grid",
        notes or [],
        properties,
    )


def test_family_classification_follows_mexican_marks() -> None:
    assert classify_family(_det("d1", DetectionType.column_tag, "K-5")) == Family.castillo
    assert classify_family(_det("d2", DetectionType.column_tag, "C-1")) == Family.columna
    assert classify_family(_det("d3", DetectionType.column_tag, "COL-2")) == Family.columna
    assert classify_family(_det("d4", DetectionType.beam_tag, "CTA-3")) == Family.contratrabe
    assert classify_family(_det("d5", DetectionType.beam_tag, "CT-2")) == Family.contratrabe
    assert classify_family(_det("d6", DetectionType.beam_tag, "T2-7")) == Family.trabe
    assert classify_family(_det("d7", DetectionType.beam_tag, "TB-1")) == Family.trabe
    assert classify_family(_det("d8", DetectionType.footing, "F3")) == Family.zapata
    assert classify_family(_det("d9", DetectionType.wall, "W12")) == Family.muro
    assert classify_family(_det("d10", DetectionType.slab_region, "SLAB2")) == Family.losa
    assert classify_family(_det("d11", DetectionType.grid_line, "A")) == Family.eje


def test_marks_preserved_for_text_tags_and_empty_for_synthetic() -> None:
    detections = [
        _det("d1", DetectionType.column_tag, "K-5"),
        _det("d2", DetectionType.wall, "W447"),
        _det(
            "d3",
            DetectionType.grid_line,
            "H1",
            notes=["No grid label found near line endpoints"],
        ),
        _det("d4", DetectionType.grid_line, "B", notes=["Grid label 'B' found near line endpoint"]),
    ]
    enrich_detections(detections)
    assert detections[0].mark == "K-5"
    assert detections[1].mark == ""  # counter, not a mark on the sheet
    assert detections[2].mark == ""  # auto-named axis
    assert detections[3].mark == "B"  # real axis label from the plano


def test_display_labels_are_deterministic_across_input_order() -> None:
    def build() -> list[Detection]:
        return [
            _det("a", DetectionType.column_tag, "K-5", bbox=(10.0, 0.0, 11.0, 1.0)),
            _det("b", DetectionType.column_tag, "K-5", bbox=(0.0, 0.0, 1.0, 1.0)),
            _det("c", DetectionType.column_tag, "C-1", bbox=(5.0, 0.0, 6.0, 1.0)),
            _det("d", DetectionType.beam_tag, "T2-7"),
        ]

    first = build()
    enrich_detections(first)
    shuffled = build()
    random.Random(7).shuffle(shuffled)
    enrich_detections(shuffled)

    by_id_first = {d.detection_id: d.display_label for d in first}
    by_id_shuffled = {d.detection_id: d.display_label for d in shuffled}
    assert by_id_first == by_id_shuffled
    # Same mark, different position → distinct stable instance labels.
    assert by_id_first["b"] == "CAS-01"
    assert by_id_first["a"] == "CAS-02"
    assert by_id_first["c"] == "COL-01"
    assert by_id_first["d"] == "TRB-01"


def test_description_reads_like_evidence_in_spanish() -> None:
    detection = _det(
        "d1",
        DetectionType.column_tag,
        "K-5",
        properties={
            "nearest_grid": "B/3",
            "section_area_du2": 0.0225,  # 15×15 cm in meters
            "section_source": "circle_diameter",
        },
    )
    text = describe(detection, unit_to_m=1.0)
    assert "Castillo K-5" in text
    assert "etiqueta «K-5» leída del plano" in text
    assert "cerca del eje B/3" in text
    assert "15×15 cm" in text
    assert "confianza 84%" in text


def test_enrich_fills_all_fields() -> None:
    detections = [_det("d1", DetectionType.beam_tag, "CTA-3")]
    enrich_detections(detections)
    d = detections[0]
    assert d.family == "contratrabe"
    assert d.family_label == "Contratrabe"
    assert d.display_label == "CTR-01"
    assert d.mark == "CTA-3"
    assert d.description.startswith("Contratrabe CTA-3")
