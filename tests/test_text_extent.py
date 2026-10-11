"""R146 (parte 1): la caja de cada TEXT y MTEXT es donde el texto está dibujado — su alineación,
su punto de inserción, la alineación de sus párrafos, su giro, su factor de ancho y su espejo —,
no un rectángulo desde el ``insert`` tendido de lado."""

import math

import ezdxf
import pytest
from ezdxf import bbox as ezdxf_bbox
from ezdxf.enums import TextEntityAlignment
from klave_engine.dxf.parser import DxfParser
from klave_engine.dxf.text_extent import ANCHO_POR_CARACTER, esquinas_de_texto


def _parse(doc, tmp_path):
    path = tmp_path / "t.dxf"
    doc.saveas(path)
    return [e for e in DxfParser().parse_file(path).entities if e.is_textual]


def _cerca(a, b, tol=1e-6):
    return all(math.isclose(x, y, abs_tol=tol) for x, y in zip(a, b, strict=True))


def test_a_left_aligned_text_starts_at_its_insert(tmp_path):
    doc = ezdxf.new("R2010")
    doc.modelspace().add_text("ABCD", height=0.5).set_placement((10, 20))
    (t,) = _parse(doc, tmp_path)
    assert _cerca(t.bbox, (10, 20, 10 + ANCHO_POR_CARACTER * 0.5 * 4, 20.5))


def test_a_text_turned_270_lies_down_the_sheet(tmp_path):
    # CE-1 «260AD» en Marina (ES-400): girado 270°, sus letras bajan desde el insert y suben del
    # renglón hacia +x; la caja de antes lo tendía de lado hacia la derecha.
    doc = ezdxf.new("R2010")
    doc.modelspace().add_text("CE-1", height=0.1, rotation=270).set_placement((205.511, -54.899))
    (t,) = _parse(doc, tmp_path)
    largo = ANCHO_POR_CARACTER * 0.1 * 4
    assert _cerca(t.bbox, (205.511, -54.899 - largo, 205.611, -54.899))
    assert t.rotation == 270


def test_a_centred_text_uses_the_width_the_cad_computed(tmp_path):
    # AutoCAD guarda en el insert (código 10) el inicio de la línea base que calculó: su ancho es
    # el doble de la distancia al punto de alineación, no una estimación por carácter.
    doc = ezdxf.new("R2010")
    t = doc.modelspace().add_text("V-1", height=0.2)
    t.dxf.halign, t.dxf.align_point, t.dxf.insert = 1, (5.0, 0.0), (4.0, 0.0)
    (n,) = _parse(doc, tmp_path)
    assert _cerca(n.bbox, (4.0, 0.0, 6.0, 0.2))


def test_a_middle_text_is_centred_both_ways(tmp_path):
    doc = ezdxf.new("R2010")
    doc.modelspace().add_text("12", height=1.0).set_placement(
        (3, 4), align=TextEntityAlignment.MIDDLE_CENTER
    )
    (t,) = _parse(doc, tmp_path)
    ancho = ANCHO_POR_CARACTER * 2
    assert _cerca(t.bbox, (3 - ancho / 2, 3.5, 3 + ancho / 2, 4.5))


def test_a_mtext_attached_top_right_hangs_left_and_down(tmp_path):
    # K-0 en PRUEBA-1: MTEXT con su punto de inserción arriba a la derecha (3); las letras quedan
    # a la izquierda y abajo del punto, no a la derecha y arriba.
    doc = ezdxf.new("R2010")
    doc.modelspace().add_mtext("K-0", dxfattribs={"char_height": 0.1, "attachment_point": 3,
                                                  "insert": (53.475, -53.251)})  # fmt: skip
    (t,) = _parse(doc, tmp_path)
    ancho = ANCHO_POR_CARACTER * 0.1 * 3
    assert _cerca(t.bbox, (53.475 - ancho, -53.351, 53.475, -53.251))


def test_a_mtext_turned_by_its_direction_vector_is_turned(tmp_path):
    # Un MTEXT guarda su giro como vector (código 11), sin código 50: el normalizador lo leía como
    # 0° (140 en Marina, 31 en PRUEBA-1).
    doc = ezdxf.new("R2010")
    m = doc.modelspace().add_mtext("ZC-1", dxfattribs={"char_height": 0.125, "insert": (0, 0),
                                                       "attachment_point": 7})  # fmt: skip
    m.dxf.text_direction = (0, 1, 0)
    m.dxf.discard("rotation")
    (t,) = _parse(doc, tmp_path)
    assert math.isclose(t.rotation, 90.0)
    largo = ANCHO_POR_CARACTER * 0.125 * 4
    assert _cerca(t.bbox, (-0.125, 0.0, 0.0, largo))


def test_a_mtext_in_a_turned_block_keeps_the_turn(tmp_path):
    doc = ezdxf.new("R2010")
    bloque = doc.blocks.new("B")
    bloque.add_mtext("CE-1", dxfattribs={"char_height": 0.1, "insert": (0, 0)})
    doc.modelspace().add_blockref("B", (10, 10), dxfattribs={"rotation": 90})
    (t,) = _parse(doc, tmp_path)
    assert math.isclose(t.rotation, 90.0)
    assert t.bbox[2] - t.bbox[0] < t.bbox[3] - t.bbox[1]  # de pie, no tendido


def test_a_left_paragraph_in_a_centred_column_starts_at_the_column(tmp_path):
    # «PLANTILLA» en PRUEBA-1: insertado al centro (5) de una columna de 2.53, con el párrafo a
    # la izquierda («\pxql»): el texto empieza en el borde izquierdo de la columna.
    doc = ezdxf.new("R2010")
    atributos = {"char_height": 0.113, "width": 2.53, "attachment_point": 5}
    atributos["insert"] = (18.703, -78.215)
    doc.modelspace().add_mtext("\\pxql;PLANTILLA", dxfattribs=atributos)
    (t,) = _parse(doc, tmp_path)
    ancho = ANCHO_POR_CARACTER * 0.113 * 9
    assert math.isclose(t.bbox[0], 18.703 - 2.53 / 2)
    assert math.isclose(t.bbox[2] - t.bbox[0], ancho)


def test_a_column_wraps_between_words(tmp_path):
    # Una palabra más larga que la columna no se corta: un renglón; dos palabras que no caben
    # juntas: dos renglones.
    doc = ezdxf.new("R2010")
    msp = doc.modelspace()
    msp.add_mtext("3mm", dxfattribs={"char_height": 0.1, "width": 0.05, "insert": (0, 0)})
    msp.add_mtext("AB CD", dxfattribs={"char_height": 0.1, "width": 0.3, "insert": (5, 0)})
    a, b = sorted(_parse(doc, tmp_path), key=lambda e: e.bbox[0])
    assert math.isclose(a.bbox[3] - a.bbox[1], 0.1)
    assert math.isclose(a.bbox[2] - a.bbox[0], ANCHO_POR_CARACTER * 0.1 * 3)
    assert math.isclose(b.bbox[3] - b.bbox[1], 0.1 + 5 / 3 * 0.1)


def test_the_width_factor_and_the_mirror(tmp_path):
    doc = ezdxf.new("R2010")
    msp = doc.modelspace()
    msp.add_text("ABCD", height=1.0, dxfattribs={"width": 0.5}).set_placement((0, 0))
    al_reves = msp.add_text("ABCD", height=1.0)
    al_reves.set_placement((10, 0))
    al_reves.dxf.text_generation_flag = 2
    angosto, espejo = sorted(_parse(doc, tmp_path), key=lambda e: e.bbox[2])
    assert _cerca(angosto.bbox, (0, 0, ANCHO_POR_CARACTER * 4 * 0.5, 1))
    assert _cerca(espejo.bbox, (10 - ANCHO_POR_CARACTER * 4, 0, 10, 1))


def test_control_codes_draw_one_character(tmp_path):
    doc = ezdxf.new("R2010")
    doc.modelspace().add_text("4%%C12", height=1.0).set_placement((0, 0))
    (t,) = _parse(doc, tmp_path)
    assert math.isclose(t.bbox[2], ANCHO_POR_CARACTER * 4)


@pytest.mark.parametrize("giro", [0, 30, 90, 180, 270])
@pytest.mark.parametrize(
    "alineacion",
    [
        TextEntityAlignment.LEFT,
        TextEntityAlignment.CENTER,
        TextEntityAlignment.RIGHT,
        TextEntityAlignment.MIDDLE_CENTER,
        TextEntityAlignment.TOP_LEFT,
        TextEntityAlignment.MIDDLE_RIGHT,
    ],
)
def test_ezdxf_draws_the_text_inside_the_box(tmp_path, giro, alineacion):
    # Donde ezdxf es fiable (un TEXT, dibujado con sus letras): el centro de lo que dibuja cae
    # dentro del rectángulo del normalizador, girado con el texto. El ancho difiere (ezdxf no tiene
    # las fuentes SHX del dibujo), el lugar y la orientación no.
    doc = ezdxf.new("R2010")
    texto = doc.modelspace().add_text("T2-10", height=0.3, rotation=giro)
    texto.set_placement((7, 3), align=alineacion)
    caja = ezdxf_bbox.extents([texto], fast=False)
    (t,) = _parse(doc, tmp_path)
    cx, cy = (caja.extmin.x + caja.extmax.x) / 2, (caja.extmin.y + caja.extmax.y) / 2
    esquinas = esquinas_de_texto(t)
    a, b, _c, d = esquinas
    u = ((cx - a[0]) * (b[0] - a[0]) + (cy - a[1]) * (b[1] - a[1])) / math.dist(a, b) ** 2
    v = ((cx - a[0]) * (d[0] - a[0]) + (cy - a[1]) * (d[1] - a[1])) / math.dist(a, d) ** 2
    assert 0.0 <= u <= 1.0 and 0.0 <= v <= 1.0
    assert t.bbox[0] <= cx <= t.bbox[2] and t.bbox[1] <= cy <= t.bbox[3]
