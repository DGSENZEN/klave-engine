"""La pieza de cancelería se lee de su clave: el bloque de nomenclatura
(CANC_ALUM con atributo CLAVE) ya declara qué es y dónde va."""

import ezdxf
from klave_engine.common.ids import IdGenerator
from klave_engine.detection.cancel_pieces import detect_cancel_pieces
from klave_engine.dxf.parser import DxfParser


def test_la_pieza_sabe_su_clave(tmp_path):
    doc = ezdxf.new("R2010")
    block = doc.blocks.new(name="CANC_ALUM")
    block.add_line((0, 0), (0.4, 0))
    block.add_attdef("CLAVE", (0, 0), dxfattribs={"height": 0.2})
    msp = doc.modelspace()
    for i, clave in enumerate(("CA-01", "PA-02", "CA-01")):
        ref = msp.add_blockref("CANC_ALUM", (i * 5, 0), dxfattribs={"layer": "NOMENCLATURA"})
        ref.add_auto_attribs({"CLAVE": clave})
    msp.add_blockref("CANC_ALUM", (30, 0), dxfattribs={"layer": "NOMENCLATURA"})  # sin clave
    path = tmp_path / "canc.dxf"
    doc.saveas(path)

    entities = DxfParser().parse_file(path).entities
    output = detect_cancel_pieces(entities, IdGenerator("d"))
    assert len(output.detections) == 3
    familias = sorted(d.properties["opening_family"] for d in output.detections)
    assert familias == ["cancel", "cancel", "puerta"]
    marcas = sorted(d.label for d in output.detections)
    assert marcas == ["CA-01", "CA-01", "PA-02"]
    assert all(d.detection_type.value == "opening" for d in output.detections)
    assert any("sin clave legible" in w for w in output.warnings)
