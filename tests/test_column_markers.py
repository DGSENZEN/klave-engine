"""El marcador de una etiqueta de columna: entre los igual de cercanos, el más chico (R130)."""

import pytest
from klave_engine.detection.column_detector import detect_columns
from klave_engine.dxf.entities import EntityType, EvidencePacket, NormalizedEntity
from klave_engine.geometry.spatial_index import SpatialIndex


def _ent(entity_id, tipo, bbox, **extra):
    return NormalizedEntity(
        entity_id=entity_id,
        entity_type=tipo,
        source_file="a.dxf",
        layer="0",
        bbox=bbox,
        raw_handle=entity_id,
        evidence=EvidencePacket(source="a.dxf", method="t", entity_ids=[entity_id], bbox=bbox),
        **extra,
    )


@pytest.mark.parametrize("al_reves", [False, True])
def test_the_smallest_marker_wins_a_tie_at_distance_zero(al_reves):
    # R130 (los K-0 de PRUEBA-1): la etiqueta toca el círculo de su castillo (r 0.070) y la caja
    # del bloque que lo contiene todo (249 u²), los dos a distancia 0: gana el círculo, sea cual
    # sea el orden del índice espacial.
    etiqueta = _ent("ent_000003", EntityType.text, (0.0, 0.0, 0.18, 0.1), text="K-0")
    bloque = _ent("ent_000001", EntityType.insert, (-8.0, -8.0, 7.6, 8.0), block_name="A$C1")
    circulo = _ent(
        "ent_000002",
        EntityType.circle,
        (0.1, 0.03, 0.24, 0.17),
        properties={"center": (0.17, 0.1), "radius": 0.07},
    )
    marcadores = [circulo, bloque] if al_reves else [bloque, circulo]
    entidades = [etiqueta, *marcadores]
    salida = detect_columns(entidades, SpatialIndex(entidades))
    (tag,) = salida.detections
    assert tag.properties["section_source"] == "marcador_circular"
    assert tag.properties["section_area_du2"] == pytest.approx(
        3.141592653589793 * 0.07**2, abs=1e-6
    )
