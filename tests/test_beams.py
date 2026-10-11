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


# ------------------------------------------------- Tarea 9, paso previo A: R135


def _etiqueta_y_lineas(tmp_path, construir):
    doc = ezdxf.new("R2010")
    construir(doc.modelspace())
    path = tmp_path / "vigas.dxf"
    doc.saveas(path)
    return DxfParser().parse_file(path).entities


_PRESET = BeamDetectorConfig(line_search_radius=1.0, min_beam_length=1.5, max_beam_length=15)


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


def _ce1(lineas):
    from klave_engine.dxf.entities import EntityType

    etiqueta = _ent(
        "ent_000009", EntityType.text, (209.211, -59.866, 209.451, -59.766), text="CE-1"
    )
    return [etiqueta, *lineas]


# Como CE-1 en Marina (ES-400, la de -59.866): dos líneas de MUROS1 tocan la caja de la etiqueta
# (distancia 0), la de 14.9 con su punto medio junto a la etiqueta y la de 9.1 lejos. Antes ganaba
# la que el índice espacial diera primero (9.1 en 8be1e7a, 14.9 en 12397e3).
_CE1_14_9 = ((209.3, -67.25), (209.3, -52.35))
_CE1_9_1 = ((209.3, -59.8), (209.3, -50.7))
# La de 9.1 del otro lado: su punto medio abajo de la etiqueta (el índice la da en otro orden).
_CE1_9_1_ABAJO = ((209.3, -68.9), (209.3, -59.8))


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
        (((209.4, -66.8), (209.4, -52.8)), False),
        # Una línea más lejos (no empatada) no hace dudoso el claro.
        (((209.9, -60.0), (209.9, -51.0)), False),
        # 14.9 contra 13.0: 13 % — dudoso.
        (((209.4, -65.0), (209.4, -52.0)), True),
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
