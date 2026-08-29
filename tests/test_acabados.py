"""La marca de acabado sabe su clave: PI y PL declaran el piso y el plafón
del local donde están parados."""

import ezdxf
from klave_engine.common.ids import IdGenerator
from klave_engine.detection.acabado_marks import detect_acabado_marks
from klave_engine.dxf.parser import DxfParser


def test_la_marca_sabe_su_clave(tmp_path):
    doc = ezdxf.new("R2010")
    pi = doc.blocks.new(name="PI")
    pi.add_circle((0, 0), 0.15)
    pi.add_attdef("P1", (0, 0), dxfattribs={"height": 0.1})
    pl = doc.blocks.new(name="PL")
    pl.add_circle((0, 0), 0.15)
    pl.add_attdef("PL1", (0, 0), dxfattribs={"height": 0.1})
    msp = doc.modelspace()
    msp.add_blockref("PI", (2, 2)).add_auto_attribs({"P1": "4"})
    msp.add_blockref("PL", (3, 3)).add_auto_attribs({"PL1": "A"})
    msp.add_blockref("PI", (9, 9))  # sin clave
    path = tmp_path / "aca.dxf"
    doc.saveas(path)

    entities = DxfParser().parse_file(path).entities
    out = detect_acabado_marks(entities, IdGenerator("d"))
    assert len(out.detections) == 2
    por_familia = {d.properties["fixture_family"]: d for d in out.detections}
    assert por_familia["acabado_piso"].properties["clave"] == "4"
    assert por_familia["acabado_plafon"].properties["clave"] == "A"
    assert any("marcas de acabado sin clave" in w for w in out.warnings)
