"""Los candidatos: figuras con tamaño de elemento que ninguna regla tomó —
ni los hijos de un bloque reventado, ni lo que ya cubre una detección, ni el
índice."""

from klave_engine.detection.candidates import candidatos
from klave_engine.detection.results import DetectionType, make_detection
from klave_engine.dxf.entities import EntityType, NormalizedEntity
from klave_engine.graph.evidence import EvidencePacket


def _ent(eid, kind, bbox, source="e.dxf", closed=True, parent=False, block=None, layer="EST"):
    props = {"closed": closed}
    if parent:
        props["parent_insert"] = "H1"
    return NormalizedEntity(
        entity_id=eid, entity_type=kind, source_file=source, layer=layer, bbox=bbox,
        raw_handle=eid, properties=props, evidence=EvidencePacket(source=source, method="t"),
        block_name=block,
    )


def test_only_unclaimed_element_sized_shapes():
    covered = make_detection("d", DetectionType.column_tag, "C", (0, 0, 0.3, 0.3), 0.9, ["d"],
                             "tag", [], {}, "e.dxf")
    ents = [
        _ent("libre", EntityType.polyline, (5, 5, 5.3, 5.4)),
        _ent("cubierta", EntityType.polyline, (0.05, 0.05, 0.25, 0.25)),
        _ent("abierta", EntityType.polyline, (8, 8, 8.3, 8.3), closed=False),
        _ent("hijo", EntityType.polyline, (10, 10, 10.3, 10.3), parent=True),
        _ent("enorme", EntityType.polyline, (0, 0, 20, 20)),
        _ent("indice", EntityType.insert, (1, 1, 1.4, 1.4), source="indice.dxf", block="NIVEL"),
        _ent("bloque", EntityType.insert, (3, 3, 3.5, 3.5), block="Z-1"),
    ]
    rows = candidatos(ents, [covered], 1.0, {"indice.dxf": "indice"})
    assert sorted(r["entity_id"] for r in rows) == ["bloque", "libre"]
    bloque = next(r for r in rows if r["entity_id"] == "bloque")
    assert bloque["veredicto"] == "no_considerado" and bloque["features"]["bloque_tokens"] == ["z"]
