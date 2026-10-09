"""La asociación de la lectura estructural: dónde está de verdad cada texto."""

import ezdxf
from ezdxf.enums import TextEntityAlignment
from klave_engine.dxf.parser import DxfParser
from klave_engine.estructura.asociacion import ancla_texto


def _entities(tmp_path, build):
    doc = ezdxf.new("R2010")
    build(doc.modelspace())
    path = tmp_path / "specs.dxf"
    doc.saveas(path)
    return DxfParser().parse_file(path).entities


def test_text_alignment_is_kept(tmp_path):
    def build(msp):
        t = msp.add_text("K-11", height=0.13)
        t.set_placement((213.343, -1.99), align=TextEntityAlignment.BOTTOM_CENTER)
        msp.add_text("8#6", height=0.10).set_placement((213.2, -1.45))

    ents = _entities(tmp_path, build)
    label = next(e for e in ents if e.text == "K-11")
    line = next(e for e in ents if e.text == "8#6")
    assert label.properties["halign"] == 1 and label.properties["align_point"] == (213.343, -1.99)
    assert ancla_texto(label) == (213.343, -1.99)
    assert line.properties["halign"] == 0 and ancla_texto(line) == (213.2, -1.45)


def test_vertical_only_alignment_and_mtext_attachment(tmp_path):
    def build(msp):
        t = msp.add_text("C-2", height=0.2)
        t.set_placement((5.0, 7.0), align=TextEntityAlignment.BOTTOM_LEFT)
        msp.add_mtext("8#6\\PE#3@15", dxfattribs={"insert": (10.0, 20.0), "char_height": 0.2})

    ents = _entities(tmp_path, build)
    etiqueta = next(e for e in ents if e.text == "C-2")
    bloque = next(e for e in ents if e.text and e.text.startswith("8#6"))
    assert (etiqueta.properties["halign"], etiqueta.properties["valign"]) == (0, 1)
    assert ancla_texto(etiqueta) == (5.0, 7.0)
    assert bloque.properties["attachment_point"] == 1
    assert ancla_texto(bloque) == (10.0, 20.0)


def test_aligned_and_fit_text_anchor_on_the_start_of_the_baseline(tmp_path):
    def build(msp):
        for texto, modo, p1, p2 in (
            ("ES-1", TextEntityAlignment.ALIGNED, (30.0, 4.0), (34.0, 4.0)),
            ("ES-2", TextEntityAlignment.FIT, (40.0, 8.0), (43.0, 8.0)),
        ):
            msp.add_text(texto, height=0.2).set_placement(p1, p2, align=modo)

    ents = _entities(tmp_path, build)
    alineado = next(e for e in ents if e.text == "ES-1")
    ajustado = next(e for e in ents if e.text == "ES-2")
    # Group 11 is where the baseline ENDS in these two modes: keep it, but anchor on the start.
    assert alineado.properties["halign"] == 3 and alineado.properties["align_point"] == (34.0, 4.0)
    assert ancla_texto(alineado) == (30.0, 4.0)
    assert ajustado.properties["halign"] == 5 and ajustado.properties["align_point"] == (43.0, 8.0)
    assert ancla_texto(ajustado) == (40.0, 8.0)
