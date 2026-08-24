"""Vanos: la puerta y la ventana valen dos veces — como pieza de cancelería y
como hueco que el muro no tiene."""

import ezdxf
from klave_engine.common.ids import IdGenerator
from klave_engine.detection.opening_detector import (
    OpeningDetectorConfig,
    detect_openings,
)
from klave_engine.detection.results import DetectionType, make_detection
from klave_engine.detection.taxonomy import Family, classify_family
from klave_engine.detection.wall_detector import WallDetectorConfig, detect_walls
from klave_engine.dxf.parser import DxfParser
from klave_engine.geometry.spatial_index import SpatialIndex


def _entities(tmp_path, name, build):
    doc = ezdxf.new("R2010")
    doc.header["$INSUNITS"] = 6
    build(doc)
    path = tmp_path / name
    doc.saveas(path)
    return DxfParser().parse_file(path).entities


def _muro(det_id: str, bbox, thickness: float = 0.15):
    return make_detection(
        det_id, DetectionType.wall, "MUR", bbox, 0.8, ["w"], "wall_paired_parallel_lines",
        [], {"estimated_length": 10.0, "estimated_thickness": thickness}, "a.dxf",
    )


def _familias(output) -> dict[str, int]:
    conteo: dict[str, int] = {}
    for d in output.detections:
        key = d.properties["opening_family"]
        conteo[key] = conteo.get(key, 0) + 1
    return conteo


def test_cada_simbolo_de_vano_es_una_pieza(tmp_path):
    def build(doc):
        for name in ("PUERTA-90", "VENTANA-120", "CANC_ALUM"):
            doc.blocks.new(name=name).add_line((0, 0), (1, 0))
        msp = doc.modelspace()
        msp.add_blockref("PUERTA-90", (1, 1), dxfattribs={"layer": "PTAS CANCEL"})
        msp.add_blockref("VENTANA-120", (5, 1), dxfattribs={"layer": "PTAS CANCEL"})
        msp.add_blockref("CANC_ALUM", (9, 1), dxfattribs={"layer": "PTAS CANCEL"})

    salida = detect_openings(
        _entities(tmp_path, "v.dxf", build), [], None, IdGenerator("d"), 1.0
    )
    assert _familias(salida) == {"puerta": 1, "ventana": 1, "cancel": 1}
    assert all(d.detection_type == DetectionType.opening for d in salida.detections)
    assert all(d.properties["width_m"] > 0 for d in salida.detections)
    assert all(classify_family(d) == Family.vano for d in salida.detections)


def test_el_ancho_medido_va_en_la_evidencia_y_la_altura_no_se_inventa(tmp_path):
    def build(doc):
        doc.blocks.new(name="PUERTA").add_line((0, 0), (0.9, 0))
        doc.modelspace().add_blockref("PUERTA", (1, 1), dxfattribs={"layer": "PTAS"})

    d = detect_openings(
        _entities(tmp_path, "a.dxf", build), [], None, IdGenerator("d"), 1.0
    ).detections[0]
    assert d.properties["width_m"] == 0.9
    evidencia = " ".join(d.evidence.notes)
    assert "0.90 m de ancho" in evidencia
    assert "cuadro de puertas y ventanas" in evidencia
    assert "por pieza" in evidencia


def test_la_capa_de_nomenclatura_guarda_nombres_y_un_nombre_no_es_una_cosa(tmp_path):
    """En Marina hay 35 bloques CANC_ALUM sobre NOMENCLATURA, todos del mismo
    ancho al centímetro: son las etiquetas de los canceles, no los canceles."""
    def build(doc):
        doc.blocks.new(name="CANC_ALUM").add_line((0, 0), (0.73, 0))
        msp = doc.modelspace()
        for i in range(5):
            msp.add_blockref("CANC_ALUM", (i, 9), dxfattribs={"layer": "NOMENCLATURA"})
        msp.add_blockref("CANC_ALUM", (1, 1), dxfattribs={"layer": "PTAS CANCEL"})

    salida = detect_openings(
        _entities(tmp_path, "n.dxf", build), [], None, IdGenerator("d"), 1.0
    )
    assert len(salida.detections) == 1
    assert salida.detections[0].properties["layer"] == "PTAS CANCEL"


def test_una_fachada_completa_no_es_un_vano(tmp_path):
    def build(doc):
        doc.blocks.new(name="CANCEL").add_line((0, 0), (18, 0))
        doc.modelspace().add_blockref("CANCEL", (0, 0), dxfattribs={"layer": "PTAS CANCEL"})

    salida = detect_openings(
        _entities(tmp_path, "f.dxf", build), [], None, IdGenerator("d"), 1.0
    )
    assert salida.detections == []


def test_un_rectangulo_suelto_en_cualquier_capa_no_es_una_ventana(tmp_path):
    """Sin bloque, sólo cuenta si la capa dice que ahí hay vanos."""
    def build(doc):
        msp = doc.modelspace()
        msp.add_lwpolyline([(0, 0), (1, 0), (1, 0.1), (0, 0.1)], close=True,
                           dxfattribs={"layer": "MUROS1"})
        msp.add_lwpolyline([(5, 0), (6, 0), (6, 0.1), (5, 0.1)], close=True,
                           dxfattribs={"layer": "PTAS CANCEL"})

    salida = detect_openings(
        _entities(tmp_path, "r.dxf", build), [], None, IdGenerator("d"), 1.0
    )
    assert [d.properties["layer"] for d in salida.detections] == ["PTAS CANCEL"]


def test_la_marca_del_cuadro_de_vanos_se_lee_del_texto_de_al_lado(tmp_path):
    def build(doc):
        doc.blocks.new(name="VENTANA").add_line((0, 0), (1.2, 0))
        msp = doc.modelspace()
        msp.add_blockref("VENTANA", (5, 5), dxfattribs={"layer": "PTAS CANCEL"})
        msp.add_text("V-03", dxfattribs={"layer": "TEXTOS", "height": 0.2}).set_placement(
            (5.4, 5.4)
        )

    d = detect_openings(
        _entities(tmp_path, "m.dxf", build), [], None, IdGenerator("d"), 1.0
    ).detections[0]
    assert d.properties["mark"] == "V-03"
    assert d.label == "V-03"


# ------------------------------------------------ el hueco en el muro ------


def test_el_vano_le_devuelve_su_ancho_al_muro_sobre_el_que_se_para(tmp_path):
    """El descuento de vanos deja de ser un porcentaje supuesto: sale de una
    medición."""
    def build(doc):
        doc.blocks.new(name="PUERTA").add_line((0, 0), (0.9, 0))
        doc.modelspace().add_blockref("PUERTA", (3, 0), dxfattribs={"layer": "PTAS"})

    muro = _muro("w1", (0.0, 0.0, 10.0, 0.15))
    salida = detect_openings(
        _entities(tmp_path, "h.dxf", build), [muro], None, IdGenerator("d"), 1.0
    )
    assert salida.detections[0].properties["on_wall"] == "w1"
    assert muro.properties["openings"] == [0.9]
    assert muro.properties["opening_length"] == 0.9


def test_dos_vanos_sobre_el_mismo_muro_suman(tmp_path):
    def build(doc):
        doc.blocks.new(name="PUERTA").add_line((0, 0), (0.9, 0))
        msp = doc.modelspace()
        msp.add_blockref("PUERTA", (2, 0), dxfattribs={"layer": "PTAS"})
        msp.add_blockref("PUERTA", (6, 0), dxfattribs={"layer": "PTAS"})

    muro = _muro("w1", (0.0, 0.0, 10.0, 0.15))
    detect_openings(_entities(tmp_path, "d.dxf", build), [muro], None, IdGenerator("d"), 1.0)
    assert muro.properties["opening_length"] == 1.8


def test_un_vano_lejos_de_todo_muro_cuenta_como_pieza_y_no_descuenta(tmp_path):
    """La cancelería casi siempre viene en su propia hoja, sin muros. Se dice
    en vez de aparentar que el descuento salió."""
    def build(doc):
        doc.blocks.new(name="PUERTA").add_line((0, 0), (0.9, 0))
        doc.modelspace().add_blockref("PUERTA", (50, 50), dxfattribs={"layer": "PTAS"})

    muro = _muro("w1", (0.0, 0.0, 10.0, 0.15))
    salida = detect_openings(
        _entities(tmp_path, "l.dxf", build), [muro], None, IdGenerator("d"), 1.0
    )
    assert len(salida.detections) == 1
    assert salida.detections[0].properties["on_wall"] == ""
    assert muro.properties.get("opening_length") is None
    assert any("no cayeron sobre ningún muro" in w for w in salida.warnings)


def test_el_detector_se_puede_apagar(tmp_path):
    def build(doc):
        doc.blocks.new(name="PUERTA").add_line((0, 0), (0.9, 0))
        doc.modelspace().add_blockref("PUERTA", (1, 1), dxfattribs={"layer": "PTAS"})

    apagado = OpeningDetectorConfig(enabled=False)
    salida = detect_openings(
        _entities(tmp_path, "o.dxf", build), [], apagado, IdGenerator("d"), 1.0
    )
    assert salida.detections == []


# --------------------------------------------------- vanos y muros ---------


def test_el_descuento_del_presupuesto_usa_los_vanos_leidos(tmp_path):
    """La prueba de arriba dice que el ancho llega al muro; ésta dice que el
    presupuesto lo usa y lo declara."""
    from klave_engine.costing.boq import generate_bill_of_quantities
    from klave_engine.costing.catalog import build_default_catalog
    from klave_engine.costing.models import CostingAssumptions
    from klave_engine.dxf.units import DrawingUnits

    def build(doc):
        doc.blocks.new(name="PUERTA").add_line((0, 0), (1.0, 0))
        msp = doc.modelspace()
        for y in (0.0, 0.15):
            msp.add_line((0, y), (10, y), dxfattribs={"layer": "MUROS1"})
        msp.add_blockref("PUERTA", (4, 0), dxfattribs={"layer": "PTAS"})

    entities = _entities(tmp_path, "b.dxf", build)
    ids = IdGenerator("det")
    config = WallDetectorConfig(
        min_length=1.5, max_thickness=0.45, min_thickness=0.05, merge_gap=0.30
    )
    walls = detect_walls(entities, SpatialIndex(entities), config, ids)
    assert walls.detections, "el muro tiene que detectarse para que haya de dónde descontar"
    detect_openings(entities, walls.detections, None, ids, 1.0)

    catalog = [c for c in build_default_catalog(CostingAssumptions()) if c.code == "ACA-001"]
    boq = generate_bill_of_quantities(
        "p", walls.detections, DrawingUnits(unit="m", source="declared", confidence=1.0),
        catalog, {}, "MXN",
    )
    linea = next(x for x in boq.lines if x.concept_code == "ACA-001")
    nota = " ".join(linea.assumptions)
    assert "Vanos −" in nota
    assert "leídas en los muros" in nota


def test_el_trazo_reventado_de_un_bloque_no_hace_dos_vanos_de_uno(tmp_path):
    """El parser revienta los bloques: la inserción y su geometría explotada
    caen en la misma capa, y contar las dos duplicaría la partida entera."""
    def build(doc):
        doc.blocks.new(name="PUERTA-90").add_line((0, 0), (0.9, 0))
        doc.modelspace().add_blockref("PUERTA-90", (1, 1), dxfattribs={"layer": "PTAS CANCEL"})

    salida = detect_openings(
        _entities(tmp_path, "e.dxf", build), [], None, IdGenerator("d"), 1.0
    )
    assert len(salida.detections) == 1
