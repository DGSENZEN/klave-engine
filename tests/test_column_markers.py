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
        layer=extra.pop("layer", "0"),
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


def _rect(entity_id, x0, y0, x1, y1, layer="EST-CASTILLOS"):
    puntos = [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]
    return _ent(
        entity_id, EntityType.polyline, (x0, y0, x1, y1), points=puntos,
        properties={"closed": True}, layer=layer,
    )  # fmt: skip


def test_an_l_shaped_castillo_records_its_whole_outline():
    # R142 (K-15A en Marina, ES-100/ES-200): el castillo es una L dibujada con dos rectángulos en
    # EST-CASTILLOS (30x60 y 25x20 pegados); el marcador es el de 30x60 y el contorno, la L entera:
    # 0.23 m², no rectangular. La sección medida del marcador no cambia.
    etiqueta = _ent("ent_000009", EntityType.text, (0.35, 0.1, 0.6, 0.2), text="K-15A")
    a = _rect("ent_000001", 0.0, 0.0, 0.3, 0.6)
    b = _rect("ent_000002", 0.3, 0.0, 0.55, 0.2)
    entidades = [etiqueta, a, b]
    (tag,) = detect_columns(entidades, SpatialIndex(entidades)).detections
    p = tag.properties
    assert p["contorno_area_du2"] == pytest.approx(0.23, abs=1e-4)
    assert p["contorno_rectangular"] is False and p["contorno_capa"] == "EST-CASTILLOS"
    assert sorted(p["contorno_entidades"]) == ["ent_000001", "ent_000002"]


def test_a_rectangular_castillo_outline_is_rectangular():
    etiqueta = _ent("ent_000009", EntityType.text, (0.2, 0.25, 0.4, 0.35), text="K-1")
    entidades = [etiqueta, _rect("ent_000001", 0.0, 0.0, 0.15, 0.2)]
    (tag,) = detect_columns(entidades, SpatialIndex(entidades)).detections
    assert tag.properties["contorno_rectangular"] is True
    assert tag.properties["contorno_area_du2"] == pytest.approx(0.03, abs=1e-6)


def test_another_tags_marker_is_never_part_of_an_outline():
    # R150 (K-14 y K-3 en Marina, ES-000/ES-100): el marcador de K-14 (30x40) toca el de K-3
    # (15x30); cada contorno es el de su marcador, nunca los dos juntos (0.165 m²).
    k14 = _ent("ent_000008", EntityType.text, (0.05, 0.45, 0.3, 0.55), text="K-14")
    k3 = _ent("ent_000009", EntityType.text, (0.35, 0.35, 0.5, 0.45), text="K-3")
    a = _rect("ent_000001", 0.0, 0.0, 0.3, 0.4)
    b = _rect("ent_000002", 0.3, 0.0, 0.45, 0.3)
    entidades = [k14, k3, a, b]
    tags = {t.label: t for t in detect_columns(entidades, SpatialIndex(entidades)).detections}
    assert tags["K-14"].properties["contorno_area_du2"] == pytest.approx(0.12, abs=1e-6)
    assert tags["K-14"].properties["contorno_rectangular"] is True
    assert tags["K-3"].properties["contorno_area_du2"] == pytest.approx(0.045, abs=1e-6)
