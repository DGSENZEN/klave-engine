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


# ------------------------------------------------- Tarea 9b, R146: la distancia a lo dibujado


def _metros():
    from klave_engine.detection.column_detector import ColumnDetectorConfig

    return ColumnDetectorConfig(geometry_search_radius=0.6, max_marker_area=1.0)


def _texto(entity_id, texto, insert, alto=0.1, punto=3):
    """Un MTEXT como los K de PRUEBA-1 (insertado arriba a la derecha): su caja, la real."""
    from klave_engine.dxf.text_extent import extension_de_texto

    e = _ent(entity_id, EntityType.mtext, (*insert, *insert), text=texto,
             properties={"height": alto, "insert": insert, "attachment_point": punto})  # fmt: skip
    e.bbox = extension_de_texto(e)
    return e


def _cuadro_abierto(entity_id, x0, y0, lado, layer="castillos"):
    """Un castillo de PRUEBA-1: cinco vértices, el último sobre el primero, sin la bandera."""
    puntos = [(x0, y0), (x0 + lado, y0), (x0 + lado, y0 - lado), (x0, y0 - lado), (x0, y0)]
    return _ent(entity_id, EntityType.polyline, (x0, y0 - lado, x0 + lado, y0), points=puntos,
                properties={"closed": False}, layer=layer)  # fmt: skip


def test_an_enclosing_block_is_never_a_marker():
    # PRUEBA-1 (K-1 en -5.13, -56.00): la etiqueta está dentro de la caja del bloque que dibuja los
    # muros de toda la planta (249 m²); su castillo es un cuadro de 0.15 cerrado por sus vértices.
    # Antes ganaba la caja del bloque (distancia 0) y el castillo se presupuestaba supuesto.
    etiqueta = _texto("ent_000009", "K-1", (-5.043, -55.945))
    bloque = _ent("ent_000001", EntityType.insert, (-17.4, -64.84, -2.9, -47.64), block_name="W")
    bloque.raw_handle = "8254"
    muro = _ent("ent_000002", EntityType.line, (-6.0, -55.77, -4.0, -55.77),
                points=[(-6.0, -55.77), (-4.0, -55.77)],
                properties={"parent_insert": "8254"}, layer="A-WALL")  # fmt: skip
    castillo = _cuadro_abierto("ent_000003", -5.56, -55.914, 0.15)
    entidades = [etiqueta, bloque, muro, castillo]
    (tag,) = detect_columns(entidades, SpatialIndex(entidades), config=_metros()).detections
    assert tag.source_entities[1] == "ent_000003"
    assert tag.properties["section_source"] == "marcador_poligonal"
    assert tag.properties["section_area_du2"] == pytest.approx(0.0225, abs=1e-9)


def test_the_distance_to_a_block_is_to_what_it_draws():
    # Un bloque de símbolo cuya caja contiene la etiqueta pero que dibuja un círculo a 0.5 de ella
    # no está a distancia 0: el castillo a 0.05 de las letras es el marcador.
    etiqueta = _texto("ent_000009", "K-2", (1.0, 1.0))
    simbolo = _ent("ent_000001", EntityType.insert, (0.2, 0.2, 1.1, 1.1), block_name="S")
    simbolo.raw_handle = "S1"
    propiedades = {"center": (0.25, 0.25), "radius": 0.05, "parent_insert": "S1"}
    circulo = _ent("ent_000002", EntityType.circle, (0.2, 0.2, 0.3, 0.3), properties=propiedades)
    castillo = _cuadro_abierto("ent_000003", 1.05, 0.95, 0.15)
    entidades = [etiqueta, simbolo, circulo, castillo]
    (tag,) = detect_columns(entidades, SpatialIndex(entidades), config=_metros()).detections
    assert tag.source_entities[1] == "ent_000003"


def test_a_castillo_drawn_only_as_its_fill_is_its_marker():
    # PRUEBA-1: 4 castillos se dibujan sólo con su sombreado (sin cuadro ni círculo).
    etiqueta = _texto("ent_000009", "K-0", (81.741, -58.018))
    puntos = [(81.80, -57.80), (81.95, -57.80), (81.95, -57.70), (81.80, -57.70)]
    relleno = _ent("ent_000001", EntityType.hatch, (81.80, -57.80, 81.95, -57.70), points=puntos,
                   properties={"closed": True}, layer="castillos")  # fmt: skip
    entidades = [etiqueta, relleno]
    (tag,) = detect_columns(entidades, SpatialIndex(entidades), config=_metros()).detections
    assert tag.properties["section_source"] == "marcador_sombreado"
    assert tag.properties["section_area_du2"] == pytest.approx(0.015, abs=1e-9)


def test_a_castillos_outline_beats_its_own_fill():
    # Marina (129 castillos) y PRUEBA-1: el cuadro del castillo y su sombreado ocupan lo mismo; el
    # marcador es el cuadro, que es lo que lee R142 (K-15A: su L de 2300 cm²).
    etiqueta = _ent("ent_000009", EntityType.text, (0.35, 0.1, 0.6, 0.2), text="K-15A")
    a = _rect("ent_000001", 0.0, 0.0, 0.3, 0.6)
    b = _rect("ent_000002", 0.3, 0.0, 0.55, 0.2)
    relleno = _ent("ent_000000", EntityType.hatch, (0.0, 0.0, 0.3, 0.6),
                   points=[(0.0, 0.0), (0.3, 0.0), (0.3, 0.6), (0.0, 0.6)],
                   properties={"closed": True}, layer="EST-CASTILLOS")  # fmt: skip
    entidades = [etiqueta, relleno, a, b]
    (tag,) = detect_columns(entidades, SpatialIndex(entidades)).detections
    assert tag.source_entities[1] in ("ent_000001", "ent_000002")  # un cuadro, nunca el relleno
    assert tag.properties["contorno_area_du2"] == pytest.approx(0.23, abs=1e-6)


@pytest.mark.parametrize("x_k2", [-10.8, -11.4])
def test_a_marker_another_marks_tag_reaches_as_near_is_flagged(x_k2):
    # R166 (PRUEBA-1, -10.25, -53.37, coordenadas redondeadas): el 15×30 de K-2 está a 0.066 de la
    # caja de K-0 y a 0.070 de la de K-2; el círculo de K-0, a 0.110. El valor se conserva y las dos
    # etiquetas dicen «marcador dudoso», con su siguiente candidato. Con K-2 lejos, nada que decir.
    k0 = _texto("ent_000009", "K-0", (-10.253, -53.372))
    k2 = _texto("ent_000008", "K-2", (x_k2, -53.05))
    rectangulo = _rect("ent_000001", -10.73, -53.339, -10.58, -53.039, layer="castillos")
    propiedades = {"center": (-10.502, -53.192), "radius": 0.07}
    caja = (-10.572, -53.262, -10.432, -53.122)
    circulo = _ent("ent_000002", EntityType.circle, caja, properties=propiedades, layer="castillos")
    entidades = [k0, k2, rectangulo, circulo]
    salida = detect_columns(entidades, SpatialIndex(entidades), config=_metros())
    tags = {d.label: d for d in salida.detections}
    assert tags["K-0"].source_entities[1] == "ent_000001"
    assert tags["K-0"].properties["section_area_du2"] == pytest.approx(0.045, abs=1e-9)
    if x_k2 == -10.8:
        assert tags["K-0"].properties["marcador_dudoso"] == (
            "marcador dudoso: el marcador tomado (polilínea de 0.045 u²) está a 0.066 de esta "
            "etiqueta y a 0.070 de «K-2», otra marca; el siguiente: círculo de 0.01539 u² a "
            "0.110; se conserva"
        )
        assert "«K-0»" in tags["K-2"].properties["marcador_dudoso"]
    else:
        assert "marcador_dudoso" not in tags["K-0"].properties


# ------------------------------------------------- Tarea 9b, ronda de arreglos 1: R175


def _config_metros():
    from klave_engine.detection.column_detector import ColumnDetectorConfig

    # Como el preset en metros de la suite.
    return ColumnDetectorConfig(
        geometry_search_radius=0.6, max_marker_area=1.0, marker_tie_tolerance=1e-4
    )


def _marcador(etiqueta, *marcadores):
    entidades = [etiqueta, *marcadores]
    (tag,) = detect_columns(entidades, SpatialIndex(entidades), config=_config_metros()).detections
    return tag.source_entities[1]


def test_a_castillo_symbol_beats_a_pile_cap_a_float_noise_nearer():
    # R175 (Marina C-3 C793B): el dado del pilote (EST-PILOTES, 70x70) está a 0.1616613 de las
    # letras y el castillo de C-3 (EST-CASTILLOS, 45x50) a 0.1616794: 1.8e-5 no es estar más
    # cerca. Igual de cerca, el símbolo en la capa de castillos, y el más chico (R130).
    etiqueta = _ent("ent_000009", EntityType.text, (0.0, 0.0, 0.27, 0.1), text="C-3")
    dado = _rect("ent_000001", -0.2, -0.8616613, 0.5, -0.1616613, layer="EST-PILOTES")
    castillo = _rect("ent_000002", 0.0, -0.6616794, 0.45, -0.1616794)
    assert _marcador(etiqueta, dado, castillo) == "ent_000002"


def test_a_castillo_symbol_beats_a_wall_box_a_float_noise_nearer():
    # R175 (Marina K-2 8E264 y 8E288): la caja de MUROS1 (55x20) a 0.0373160, su castillo (15x20)
    # a 0.0373178.
    etiqueta = _ent("ent_000009", EntityType.text, (0.0, 0.0, 0.27, 0.1), text="K-2")
    caja = _rect("ent_000001", -0.5, -0.237316, 0.05, -0.037316, layer="MUROS1")
    castillo = _rect("ent_000002", 0.1, -0.2373178, 0.25, -0.0373178)
    assert _marcador(etiqueta, caja, castillo) == "ent_000002"


def test_among_equally_near_castillos_the_smallest_wins():
    # R130 con R175: dos símbolos de castillo a 5e-5 uno del otro son igual de cercanos.
    etiqueta = _ent("ent_000009", EntityType.text, (0.0, 0.0, 0.27, 0.1), text="K-1")
    grande = _rect("ent_000001", -0.25, -0.35, 0.05, -0.05)
    chico = _rect("ent_000002", 0.1, -0.20005, 0.25, -0.05005)
    assert _marcador(etiqueta, grande, chico) == "ent_000002"


def test_a_castillo_symbol_within_half_a_text_height_beats_a_slab_piece():
    # R179 (Marina K-1 8E092): un pedazo de EST-LOSA MACIZA a 0.005 de las letras y el castillo de
    # K-1 a 0.044: a media altura de texto (0.05) del más cercano, gana el símbolo en la capa de
    # castillos.
    etiqueta = _ent("ent_000009", EntityType.text, (0.0, 0.0, 0.27, 0.1), text="K-1")
    losa = _rect("ent_000001", -0.2, -0.705, 0.5, -0.005, layer="EST-LOSA MACIZA")
    castillo = _rect("ent_000002", 0.0, -0.194, 0.15, -0.044)
    assert _marcador(etiqueta, losa, castillo) == "ent_000002"


def test_an_outline_nearer_by_more_than_half_a_text_height_still_wins():
    # R179: más allá de media altura de texto, el más cercano, sea de la capa que sea.
    etiqueta = _ent("ent_000009", EntityType.text, (0.0, 0.0, 0.27, 0.1), text="K-1")
    losa = _rect("ent_000001", -0.2, -0.705, 0.5, -0.005, layer="EST-LOSA MACIZA")
    castillo = _rect("ent_000002", 0.0, -0.22, 0.15, -0.07)
    assert _marcador(etiqueta, losa, castillo) == "ent_000001"


def test_a_dado_is_not_a_castillos_symbol():
    # R179 (Marina K-15 DFC6C): la cara de un muro de concreto a 0.074, el dado de un pilote
    # (EST-DADOS, 90x90) a 0.097 y el castillo de K-15 (EST-CASTILLOS, 30x60) a 0.122, a media
    # altura de texto del más cercano: el del castillo, nunca el dado.
    etiqueta = _ent("ent_000009", EntityType.text, (0.0, 0.0, 0.36, 0.1), text="K-15")
    muro = _rect("ent_000001", -0.5, -0.2742438, 0.55, -0.0742438, layer="EST-MURO CONCRETO")
    dado = _rect("ent_000002", 0.4, -0.9969529, 1.3, -0.0969529, layer="EST-DADOS")
    castillo = _rect("ent_000003", 0.0, -0.7218038, 0.3, -0.1218038)
    assert _marcador(etiqueta, muro, dado, castillo) == "ent_000003"


def test_the_castillo_preference_never_takes_another_marks_symbol():
    # R182: K-1 junto a un contorno de A-WALL (a 0.02) y al 45×45 de C-1 (a 0.05, dentro de media
    # altura de texto), que la etiqueta C-1 alcanza más cerca (0.01): ese símbolo es de C-1; K-1
    # conserva el más cercano y dice «marcador dudoso».
    k1 = _ent("ent_000009", EntityType.text, (0.0, 0.0, 0.27, 0.1), text="K-1")
    c1 = _ent("ent_000008", EntityType.text, (0.6, -0.4, 0.87, -0.3), text="C-1")
    muro = _rect("ent_000001", -0.3, -0.12, 0.05, -0.02, layer="A-WALL")
    columna = _rect("ent_000002", 0.2, -0.5, 0.65, -0.05)
    entidades = [k1, c1, muro, columna]
    salida = detect_columns(entidades, SpatialIndex(entidades), config=_config_metros())
    tag = next(d for d in salida.detections if d.label == "K-1")
    assert tag.source_entities[1] == "ent_000001"
    assert "«C-1», otra marca" in tag.properties["marcador_dudoso"]
