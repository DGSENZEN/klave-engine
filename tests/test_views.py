"""View segmentation tests."""

from klave_engine.detection.results import Detection, DetectionType
from klave_engine.detection.views import ViewKind, segment_views
from klave_engine.dxf.entities import EntityType, NormalizedEntity
from klave_engine.graph.evidence import EvidencePacket


def _title(text: str, x: float, y: float, height: float = 0.5) -> NormalizedEntity:
    return NormalizedEntity(
        entity_id=f"t_{x}_{y}",
        entity_type=EntityType.text,
        source_file="s.dxf",
        layer="TITULOS",
        bbox=(x, y, x + 1, y + 0.5),
        raw_handle="H",
        text=text,
        properties={"height": height},
        evidence=EvidencePacket(source="s.dxf", method="test"),
    )


def _small_text(text: str, x: float, y: float) -> NormalizedEntity:
    return _title(text, x, y, height=0.1)


def _det(did: str, dtype: DetectionType, x: float, y: float) -> Detection:
    return Detection(
        detection_id=did,
        detection_type=dtype,
        label=did,
        bbox=(x, y, x + 0.3, y + 0.3),
        confidence=0.9,
        evidence=EvidencePacket(source="s.dxf", method="test"),
    )


def test_single_plan_is_not_segmented() -> None:
    ents = [_title("PLANTA BAJA", 0, 0)] + [_small_text("x", i, 1) for i in range(20)]
    seg = segment_views(ents, [])
    assert seg.is_segmented is False
    assert seg.views == []


def test_two_plans_segment_and_assign() -> None:
    # Median text height is small so the big titles clear the threshold.
    ents = [_small_text("nota", i * 0.1, 5) for i in range(20)]
    ents += [
        _title("PLANTA DE CIMENTACIÓN", 0, 0),
        _title("PLANTA BAJA N.P.T. +3.45", 100, 0),
        _title("DETALLE DE CASTILLO", 50, -50),
    ]
    dets = [
        _det("a", DetectionType.footing, 2, 1),       # near cimentación
        _det("b", DetectionType.column_tag, 101, 1),  # near planta baja
        _det("c", DetectionType.column_tag, 50, -49),  # near detail (excluded)
    ]
    seg = segment_views(ents, dets)
    assert seg.is_segmented is True
    assert len(seg.plan_views()) == 2
    assert {v.level_key for v in seg.plan_views()} == {"cimentacion", "planta_baja"}
    assert seg.npt_levels == [3.45]
    # foundation detection routed to the cimentación plan
    found = next(v for v in seg.plan_views() if v.level_key == "cimentacion")
    assert "a" in found.detection_ids
    # detail detection routed to the excluded region
    excluded = [v for v in seg.views if v.kind == ViewKind.excluded]
    assert excluded and "c" in excluded[0].detection_ids


def test_npt_total_height() -> None:
    ents = [_small_text("n", i * 0.1, 9) for i in range(20)]
    ents += [
        _title("PLANTA BAJA N.P.T. +0.15", 0, 0),
        _title("AZOTEA N.P.T. +6.60", 100, 0),
    ]
    seg = segment_views(ents, [])
    assert seg.total_height() == 6.60
    assert seg.foundation_views() == []
    assert len(seg.superstructure_views()) == 2
