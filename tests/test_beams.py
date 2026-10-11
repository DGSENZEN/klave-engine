"""Trabe marks: Mexican patterns and the line a mark belongs to."""

import ezdxf
import pytest
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
    # A grid axis passes 0.2 from the mark; the trabe line is 0.6 away; a wall line farther.
    msp.add_line((0, 0.2), (100, 0.2), dxfattribs={"layer": "S-GRID"})
    msp.add_line((0, -0.6), (5, -0.6), dxfattribs={"layer": "E-TRABES"})
    msp.add_line((0, -0.9), (4, -0.9), dxfattribs={"layer": "A-WALL"})
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


# ------------------------------------------------- Tarea 9, paso previo A: R135


def _etiqueta_y_lineas(tmp_path, construir):
    doc = ezdxf.new("R2010")
    construir(doc.modelspace())
    path = tmp_path / "vigas.dxf"
    doc.saveas(path)
    return DxfParser().parse_file(path).entities


_PRESET = BeamDetectorConfig(
    line_search_radius=1.0,
    min_beam_length=1.5,
    max_beam_length=15,
    layer_tolerance=0.15,
    max_face_gap=0.35,
    support_tolerance=0.05,
)


def test_a_leader_is_never_the_beam_line(tmp_path):
    # R135 (CE-4 en Marina, ES-300): la directriz de la nota «MURO DE 20 CM» (LEADER en la capa
    # EST-LOSA NERVADA, 1.606 de largo) pasa a 0.15 de la etiqueta; la línea de la dala (5.85)
    # está a 0.18. Una directriz es anotación, nunca la línea de una trabe.
    def construir(msp):
        msp.add_text("CE-4", height=0.1).set_placement((200.04, -26.903))
        msp.add_leader(
            [(199.0, -27.05), (199.7, -27.6), (200.4, -27.6)],
            dxfattribs={"layer": "EST-LOSA NERVADA"},
        )
        msp.add_lwpolyline(
            [(197.0, -26.623), (202.85, -26.623)], dxfattribs={"layer": "EST-LOSA VIG Y BOV"}
        )

    entidades = _etiqueta_y_lineas(tmp_path, construir)
    lider = next(e for e in entidades if e.properties.get("derived_from") == "LEADER")
    (viga,) = detect_beams(entidades, SpatialIndex(entidades), _PRESET).detections
    assert lider.entity_id not in viga.source_entities
    assert viga.properties["estimated_span_length"] == 5.85
    assert viga.properties["span_layer"] == "EST-LOSA VIG Y BOV"


def test_a_multileader_line_is_never_the_beam_line(tmp_path):
    # R135: lo mismo con una MULTILEADER (sus líneas llegan como polilíneas abiertas, R133).
    from ezdxf.math import Vec2
    from ezdxf.render import mleader

    def construir(msp):
        msp.add_text("CE-4", height=0.1).set_placement((0.0, 0.0))
        ml = msp.add_multileader_mtext("Standard")
        ml.set_content("MURO DE 20 CM", char_height=0.1)
        ml.set_connection_properties(landing_gap=0.02, dogleg_length=0.3)
        ml.add_leader_line(mleader.ConnectionSide.left, [Vec2(-1.5, 0.15)])
        ml.build(insert=Vec2(0.5, 0.6))
        msp.add_lwpolyline([(-2.0, -0.3), (3.85, -0.3)], dxfattribs={"layer": "MUROS1"})

    entidades = _etiqueta_y_lineas(tmp_path, construir)
    anotacion = {
        e.entity_id for e in entidades if e.properties.get("derived_from") == "MULTILEADER"
    }
    assert anotacion
    (viga,) = detect_beams(entidades, SpatialIndex(entidades), _PRESET).detections
    assert not anotacion & set(viga.source_entities)
    assert viga.properties["estimated_span_length"] == 5.85


def _ent(entity_id, tipo, bbox, **extra):
    from klave_engine.dxf.entities import EvidencePacket, NormalizedEntity

    return NormalizedEntity(
        entity_id=entity_id,
        entity_type=tipo,
        source_file="a.dxf",
        layer=extra.pop("layer", "MUROS1"),
        bbox=bbox,
        raw_handle=entity_id,
        evidence=EvidencePacket(source="a.dxf", method="t", entity_ids=[entity_id], bbox=bbox),
        **extra,
    )


def _linea(entity_id, p, q, **extra):
    from klave_engine.dxf.entities import EntityType

    bbox = (min(p[0], q[0]), min(p[1], q[1]), max(p[0], q[0]), max(p[1], q[1]))
    return _ent(entity_id, EntityType.line, bbox, points=[p, q], **extra)


def _texto(entity_id, texto, insert, alto=0.1, giro=0.0, capa="EST-CADENAS Y DALAS"):
    """Un TEXT alineado a la izquierda como lo deja el normalizador: su caja, la real (R146)."""
    from klave_engine.dxf.entities import EntityType
    from klave_engine.dxf.text_extent import extension_de_texto

    e = _ent(entity_id, EntityType.text, (*insert, *insert), text=texto, rotation=giro,
             layer=capa, properties={"height": alto, "insert": insert})  # fmt: skip
    e.bbox = extension_de_texto(e)
    return e


def _ce1(lineas):
    # CE-1 «4DE40» en Marina (ES-400): girado 270°, sus letras bajan de (209.211, -59.866).
    return [_texto("ent_000009", "CE-1", (209.211, -59.866), giro=270.0), *lineas]


# Como CE-1 en Marina: dos líneas de MUROS1 pasan por las letras de la etiqueta (distancia 0), la de
# 14.9 con su punto medio junto a la etiqueta y la de 9.1 lejos. Antes ganaba la que el índice
# espacial diera primero (9.1 en 8be1e7a, 14.9 en 12397e3).
_CE1_14_9 = ((209.3, -67.25), (209.3, -52.35))
_CE1_9_1 = ((209.3, -64.0), (209.3, -54.9))
# La de 9.1 del otro lado: su punto medio abajo de la etiqueta (el índice la da en otro orden).
_CE1_9_1_ABAJO = ((209.3, -66.0), (209.3, -56.9))


@pytest.mark.parametrize("orden", [0, 1])
@pytest.mark.parametrize("ids", [("ent_000001", "ent_000002"), ("ent_000002", "ent_000001")])
@pytest.mark.parametrize("corta_en", [_CE1_9_1, _CE1_9_1_ABAJO])
def test_a_distance_tie_goes_to_the_nearest_midpoint_whatever_the_index_order(orden, ids, corta_en):
    larga = _linea(ids[0], *_CE1_14_9)
    corta = _linea(ids[1], *corta_en)
    lineas = [larga, corta] if orden == 0 else [corta, larga]
    entidades = _ce1(lineas)
    (viga,) = detect_beams(entidades, SpatialIndex(entidades), _PRESET).detections
    assert viga.properties["estimated_span_length"] == 14.9
    assert larga.entity_id in viga.source_entities


def test_tied_lines_more_than_ten_percent_apart_say_claro_dudoso():
    # R135: 14.9 y 9.1 igual de cerca: el claro se toma, y se dice que es dudoso.
    entidades = _ce1([_linea("ent_000001", *_CE1_14_9), _linea("ent_000002", *_CE1_9_1)])
    (viga,) = detect_beams(entidades, SpatialIndex(entidades), _PRESET).detections
    aviso = viga.properties["claro_dudoso"]
    assert aviso.startswith("claro dudoso:") and "9.1" in aviso and "14.9" in aviso
    assert any(n.startswith("claro dudoso:") for n in viga.evidence.notes)


@pytest.mark.parametrize(
    "otra,dudoso",
    [
        # 14.9 contra 14.0: 6 % — no es dudoso.
        (((209.3, -66.8), (209.3, -52.8)), False),
        # Una línea más lejos (no empatada) no hace dudoso el claro.
        (((209.9, -60.0), (209.9, -51.0)), False),
        # 14.9 contra 13.0: 13 % — dudoso.
        (((209.3, -65.0), (209.3, -52.0)), True),
    ],
)
def test_claro_dudoso_only_for_tied_candidates_beyond_ten_percent(otra, dudoso):
    entidades = _ce1([_linea("ent_000001", *_CE1_14_9), _linea("ent_000002", *otra)])
    (viga,) = detect_beams(entidades, SpatialIndex(entidades), _PRESET).detections
    assert viga.properties["estimated_span_length"] == 14.9
    assert ("claro_dudoso" in viga.properties) is dudoso


def test_equal_midpoints_go_to_the_first_entity_id():
    # Dos copias de la misma línea (de un bloque y del espacio modelo): gana el id menor, sea cual
    # sea el orden de la lista; numérico, no de texto («ent_10» va después de «ent_9»).
    a = _linea("ent_10", *_CE1_14_9)
    b = _linea("ent_9", *_CE1_14_9)
    for lineas in ([a, b], [b, a]):
        entidades = _ce1(lineas)
        (viga,) = detect_beams(entidades, SpatialIndex(entidades), _PRESET).detections
        assert viga.source_entities[-1] == "ent_9"
        assert "claro_dudoso" not in viga.properties


def test_no_detector_is_handed_annotation_geometry(tmp_path):
    # R135: la suite no le da a ningún detector de geometría lo que es anotación (las líneas de un
    # LEADER o de una MULTILEADER), aunque el índice que recibe las traiga: aquí, la directriz de
    # una nota en la capa del agua fría no son metros de tubería.
    from klave_engine.common.ids import IdGenerator
    from klave_engine.detection.suite import DetectorSuiteConfig, run_detectors
    from klave_engine.dxf.units import DrawingUnits
    from klave_engine.ingestion.manifest import ProjectManifest

    def construir(msp):
        msp.add_line((0, 0), (10, 0), dxfattribs={"layer": "P-04IH-CPIP"})
        msp.add_line((10, 0), (10, 6), dxfattribs={"layer": "P-04IH-CPIP"})
        msp.add_leader([(2, 1), (4, 3), (6, 3)], dxfattribs={"layer": "P-04IH-CPIP"})

    entidades = _etiqueta_y_lineas(tmp_path, construir)
    salidas = run_detectors(
        entidades,
        SpatialIndex(entidades),
        ProjectManifest(project_id="t", project_name="t", root_path=str(tmp_path)),
        DetectorSuiteConfig(),
        ids=IdGenerator("d"),
        units=DrawingUnits(unit="m", source="dxf_header", confidence=0.9),
        structural=False,
    )
    (corrida,) = [d for o in salidas for d in o.detections if d.detection_type == "pipe_run"]
    assert corrida.properties["length_m"] == 16.0
    assert corrida.properties["segments"] == 2


# ------------------------------------------------- Tarea 9b, R146: líneas alineadas y reales


def _vigas(entidades, apoyos=None):
    from klave_engine.detection.results import DetectorOutput

    salida = detect_beams(entidades, SpatialIndex(entidades), _PRESET, supports=apoyos)
    assert isinstance(salida, DetectorOutput)
    return {d.source_entities[0]: d for d in salida.detections}


def test_a_tag_takes_an_aligned_line_never_a_perpendicular_one():
    # CE-4 en Marina (ES-300): la vigueta vertical de 5.85 pasa por la etiqueta horizontal; la
    # dala corre en el muro horizontal de abajo. Antes tomaba la vigueta.
    entidades = [
        _texto("t", "CE-4", (200.04, -26.903)),
        _linea("vigueta", (200.2, -29.5), (200.2, -23.65), layer="EST-LOSA VIG Y BOV"),
        _linea("muro", (198.5, -26.95), (201.85, -26.95), layer="MUROS1"),
    ]
    viga = _vigas(entidades)["t"]
    assert viga.properties["estimated_span_length"] == 3.35
    assert viga.source_entities[1] == "muro"


def test_the_l_shaped_wall_counts_each_leg_by_itself():
    # MUROS1 «1F96B» en Marina (ES-400): (204.076,-61.698)→(209.526,-61.698)→(209.526,-52.398),
    # 14.9 de largo. Su caja contenía 7 etiquetas a distancia 0 y cada una contaba 14.9. Ahora cada
    # etiqueta toma el tramo recto junto a ella; la que está dentro de la caja lejos de los dos
    # tramos no toma ninguno y lo dice.
    muro = _ent(
        "muro", _tipo("polyline"), (204.076, -61.698, 209.526, -52.398),
        points=[(204.076, -61.698), (209.526, -61.698), (209.526, -52.398)],
    )  # fmt: skip
    entidades = [
        muro,
        _texto("h", "CE-1", (205.5, -61.65)),
        _texto("v", "CE-1", (209.45, -55.0), giro=270.0),
        _texto("lejos", "CE-1", (206.0, -57.0)),
    ]
    vigas = _vigas(entidades)
    assert vigas["h"].properties["estimated_span_length"] == 5.45
    assert vigas["v"].properties["estimated_span_length"] == 9.3
    assert "estimated_span_length" not in vigas["lejos"].properties
    assert vigas["lejos"].properties["sin_claro"].startswith("longitud: ninguna línea alineada")


def _tipo(nombre):
    from klave_engine.dxf.entities import EntityType

    return EntityType(nombre)


def test_a_tag_past_the_lines_end_does_not_take_it():
    entidades = [
        _texto("t", "T-1", (5.5, 0.05), capa="TEXTO"),
        _linea("l", (0.0, 0.0), (5.0, 0.0), layer="EST-TRABES"),
    ]
    assert "estimated_span_length" not in _vigas(entidades)["t"].properties
    entidades[0] = _texto("t", "T-1", (4.85, 0.05), capa="TEXTO")
    assert _vigas(entidades)["t"].properties["estimated_span_length"] == 5.0


@pytest.mark.parametrize("y_trabe,toma", [(-0.06, "trabe"), (-0.3, "muro")])
def test_the_layer_preference_only_chooses_among_lines_about_as_near(y_trabe, toma):
    # R146: la capa de la trabe sólo decide entre líneas casi igual de cerca (0.05): a 0.06 contra
    # el muro a 0.03, la trabe; a 0.3, el muro, que es lo que corre junto a la etiqueta.
    entidades = [
        _texto("t", "T-1", (1.0, 0.0), capa="TEXTO"),
        _linea("muro", (0.0, -0.03), (4.0, -0.03), layer="MUROS1"),
        _linea("trabe", (0.0, y_trabe), (5.0, y_trabe), layer="EST-TRABES"),
    ]
    assert _vigas(entidades)["t"].source_entities[1] == toma


def test_each_family_takes_its_own_layer_on_coincident_lines():
    # T3-19 y CE-1 en Marina (ES-300): el muro (MUROS1, 4.45) y la trabe (EST-TRABES, 5.65) se
    # dibujan en la misma recta, a la misma distancia de las dos etiquetas: la dala toma el muro
    # que corona y la trabe la suya.
    entidades = [
        _texto("ce", "CE-1", (198.64, -23.0), giro=270.0),
        _texto("t", "T3-19", (198.64, -25.0), giro=270.0, capa="TEXTO"),
        _linea("muro", (198.69, -26.0), (198.69, -21.55), layer="MUROS1"),
        _linea("trabe", (198.69, -27.2), (198.69, -21.55), layer="EST-TRABES"),
    ]
    vigas = _vigas(entidades)
    assert vigas["ce"].source_entities[1] == "muro"
    assert vigas["t"].source_entities[1] == "trabe"


def test_a_cerramiento_takes_its_own_short_line():
    # CR-1 en Marina (ES-400, 209.27,-52.12): su cerramiento mide 0.45 entre K-2A y K-1, en
    # EST-CERRAMIENTOS; el muro de 9.3 corre a 0.24. En su propia capa una línea corta es el
    # elemento; fuera de ella, menos de 1.5 es un trazo.
    entidades = [
        _texto("cr", "CR-1", (209.2, -51.8), giro=270.0, capa="EST-CERRAMIENTOS"),
        _linea("cerr", (209.34, -52.3), (209.34, -51.85), layer="EST-CERRAMIENTOS"),
        _linea("muro", (209.54, -61.0), (209.54, -51.7), layer="MUROS1"),
    ]
    viga = _vigas(entidades)["cr"]
    assert viga.source_entities[1] == "cerr"
    assert viga.properties["estimated_span_length"] == 0.45


@pytest.mark.parametrize("capa,dudoso", [("EST-MURO CONCRETO", True), ("EST-CONTRATRABE", False)])
def test_a_short_piece_of_the_supporting_wall_is_a_doubtful_span(capa, dudoso):
    # R165 (CTA-3 en Marina, ES-000): el tramo de 0.45 junto a la etiqueta es un pedazo de la cara
    # del muro MC-1 (dibujado en cajas cerradas), no la contratrabe: se toma, pero dudoso, con las
    # otras líneas alineadas. En su propia capa, una línea corta es el elemento.
    entidades = [
        _texto("t", "CTA-3", (0.0, 0.05), capa="TEXTO"),
        _linea("a", (-0.1, 0.0), (0.35, 0.0), layer=capa),
        _linea("b", (0.55, 0.0), (1.0, 0.0), layer="EST-MURO CONCRETO"),
    ]
    viga = _vigas(entidades)["t"]
    assert viga.source_entities[1] == "a"
    assert viga.properties["estimated_span_length"] == 0.45
    if dudoso:
        assert viga.properties["claro_dudoso"] == (
            "claro dudoso: el tramo tomado mide 0.45, menos que una viga (1.5), y es de la capa en "
            "que se apoya (EST-MURO CONCRETO), no de la suya; otras líneas alineadas: "
            "EST-MURO CONCRETO 0.45 a 0.11"
        )
    else:
        assert "claro_dudoso" not in viga.properties


def test_a_line_shared_by_its_tags_counts_once():
    # R146 (5): cuatro CTA-5 sobre la contratrabe de 20 que cruza el edificio (Marina ES-000):
    # cada una su tramo, cortado a medio camino; suman la línea una vez. Una sola etiqueta sobre
    # una línea de 20 no es un claro; una línea de 20 que no es de su familia, tampoco se toma.
    entidades = [_linea("cta", (0.0, 0.0), (20.0, 0.0), layer="EST-CONTRATRABE")]
    entidades += [_texto(f"t{x}", "CTA-5", (x, 0.05), capa="TEXTO") for x in (2.0, 7.0, 12.0, 17.0)]
    vigas = _vigas(entidades)
    largos = [vigas[f"t{x}"].properties["estimated_span_length"] for x in (2.0, 7.0, 12.0, 17.0)]
    # Las etiquetas CTA-5 (0.45 de largo) tienen su centro 0.225 después de su x.
    assert largos == pytest.approx([4.725, 5.0, 5.0, 5.275], abs=1e-3)
    assert sum(largos) == pytest.approx(20.0)
    aviso = vigas["t2.0"].properties["claro_compartido"]
    assert aviso.startswith("claro compartido: tramo partido entre 4 etiquetas (CTA-5)")
    sola = [entidades[0], _texto("s", "CTA-5", (7.0, 0.05), capa="TEXTO")]
    assert "más que el máximo" in _vigas(sola)["s"].properties["sin_claro"]
    ajena = [_linea("muro", (0.0, 0.0), (20.0, 0.0), layer="A-LOSA"), sola[1]]
    assert "estimated_span_length" not in _vigas(ajena)["s"].properties


def test_a_shared_line_is_cut_at_the_castillos_on_it():
    # T3-8 en Marina (ES-300): cuatro etiquetas sobre una trabe de 9.55 con castillos en ella: los
    # cortes caen en el castillo más cercano a medio camino entre dos etiquetas.
    from klave_engine.detection.column_detector import ColumnDetectorConfig, detect_columns

    entidades = [_linea("trabe", (0.0, 0.0), (9.55, 0.0), layer="EST-TRABES")]
    entidades += [_texto(f"t{x}", "T3-8", (x, 0.05), capa="TEXTO") for x in (1.0, 3.5, 6.2, 8.5)]
    for k, x in enumerate((2.9, 4.6, 7.4)):  # castillos de 0.15 sobre la línea
        entidades.append(
            _ent(f"c{k}", _tipo("polyline"), (x, -0.15, x + 0.15, 0.0), layer="EST-CASTILLOS",
                 points=[(x, -0.15), (x + 0.15, -0.15), (x + 0.15, 0.0), (x, 0.0)],
                 properties={"closed": True})
        )  # fmt: skip
        entidades.append(_texto(f"k{k}", "K-1", (x, -0.3), capa="TEXTO"))
    indice = SpatialIndex(entidades)
    columnas = detect_columns(
        entidades, indice, None,
        ColumnDetectorConfig(geometry_search_radius=0.6, max_marker_area=1.0),
    )  # fmt: skip
    vigas = _vigas(entidades, columnas)
    largos = [vigas[f"t{x}"].properties["estimated_span_length"] for x in (1.0, 3.5, 6.2, 8.5)]
    # Los centros de las etiquetas, 0.18 después de su x: 1.18, 3.68, 6.38, 8.68. Cortes: el
    # castillo de 2.975; entre 3.68 y 6.38 el de 4.675 (el único entre ellas); el de 7.475.
    assert largos == pytest.approx([2.975, 1.7, 2.8, 2.075], abs=1e-3)
    assert "en los apoyos entre ellas" in vigas["t1.0"].properties["claro_compartido"]


def test_the_two_faces_of_one_beam_are_one_line():
    # R146 (4): dos etiquetas de la misma dala, una de cada lado del muro, toman sus dos caras (0.15
    # entre ellas, 4.45 y 4.65): es una viga, medida en su eje (4.55) y partida entre las dos.
    entidades = [
        _linea("cara1", (0.1, 0.0), (4.55, 0.0)),
        _linea("cara2", (0.0, 0.15), (4.65, 0.15)),
        _texto("a", "CE-1", (1.0, -0.15)),
        _texto("b", "CE-1", (3.0, 0.2)),
    ]
    vigas = _vigas(entidades)
    total = sum(vigas[k].properties["estimated_span_length"] for k in ("a", "b"))
    assert total == pytest.approx(4.55)
    assert vigas["a"].properties["claro_caras"].startswith("claro de una viga dibujada con 2 caras")
    assert {"cara1", "cara2"} <= set(vigas["a"].source_entities)


def test_a_foreign_tag_takes_its_next_line_or_none():
    # R146 (5): la línea de la trabe es de la trabe; el cerramiento que la tenía más cerca toma su
    # siguiente línea alineada, o ninguna, y lo dice.
    trabe = _linea("trabe", (0.0, 0.0), (3.75, 0.0), layer="EST-TRABES")
    t = _texto("t", "T2-15", (2.0, 0.05), capa="TEXTO")
    cr = _texto("cr", "CR-2", (0.5, 0.04), capa="TEXTO")
    muro = _linea("muro", (0.0, 0.5), (1.6, 0.5))
    vigas = _vigas([trabe, t, cr, muro])
    assert vigas["t"].source_entities[1] == "trabe"
    assert vigas["t"].properties["estimated_span_length"] == 3.75
    assert vigas["cr"].source_entities[1] == "muro"
    assert any("es de otra familia (trabe)" in n for n in vigas["cr"].evidence.notes)
    sin = _vigas([trabe, t, cr])["cr"]
    assert "es de otra familia" in sin.properties["sin_claro"]


def test_two_kinds_of_dala_on_one_wall_are_not_partitioned():
    # Una cadena de enrase y otra dala del mismo muro (otra clase: DL) coronan el muro a otra
    # altura: cada una lo cuenta entero; dos CE-1 sí se lo reparten.
    muro = _linea("muro", (0.0, 0.0), (4.0, 0.0))
    vigas = _vigas([muro, _texto("a", "CE-1", (1.0, 0.04)), _texto("b", "DL-1", (2.5, 0.04))])
    assert [vigas[k].properties["estimated_span_length"] for k in ("a", "b")] == [4.0, 4.0]
    vigas = _vigas([muro, _texto("a", "CE-1", (1.0, 0.04)), _texto("b", "CE-1", (2.5, 0.04))])
    assert sum(vigas[k].properties["estimated_span_length"] for k in ("a", "b")) == 4.0
