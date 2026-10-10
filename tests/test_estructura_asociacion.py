"""La asociación de la lectura estructural: dónde está de verdad cada texto."""

import json
import math
import random
from pathlib import Path

import ezdxf
import pytest
from ezdxf.enums import TextEntityAlignment
from klave_engine.detection.frames import SheetFrame
from klave_engine.detection.text_patterns import TextPatternConfig
from klave_engine.dxf.parser import DxfParser
from klave_engine.estructura.asociacion import (
    ARMADO_RE,
    ancla_texto,
    asociar,
    lo_lee_una_nota,
    marca_en_rango,
    marca_en_texto,
    marcas_en_nota,
)
from klave_engine.estructura.textos import caja_de_texto


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


def test_mtext_keeps_its_column_and_paragraph_alignment(tmp_path):
    # Sin la columna y la alineación del párrafo, el MTEXT de P-5 parece estar junto a P-4.
    def build(msp):
        msp.add_mtext(
            "\\pxqc;4#8 + 12#6\\P3E#3 VER CORTE",
            dxfattribs={"insert": (189.0342, 68.3192), "char_height": 0.1, "width": 6.3892},
        )
        msp.add_mtext("E#3@15", dxfattribs={"insert": (0.0, 0.0), "char_height": 0.1})

    ents = _entities(tmp_path, build)
    centrado = next(e for e in ents if e.text and e.text.startswith("4#8"))
    suelto = next(e for e in ents if e.text == "E#3@15")
    assert centrado.properties["column_width"] == 6.3892
    assert centrado.properties["paragraph_align"] == "c"
    assert "column_width" not in suelto.properties and "paragraph_align" not in suelto.properties


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


# ---------------------------------------------------------------- la pila de cada marca

# La geometría medida en Marina: la etiqueta (alto 0.13, centrada) va DEBAJO de sus renglones de
# armado (alto 0.10, alineados a la izquierda), a 0.17–0.18 de paso. Desplazamientos desde el
# ancla de la etiqueta.
K11 = [("8#6", 0.134, 0.537), ("2E#3EXT@10", -0.179, 0.353), ("CENTRO@20", -0.179, 0.186)]
K12 = [("4#6+4#4", -0.109, 0.506), ("2E#3EXT@10", -0.219, 0.322), ("CENTRO@15", -0.219, 0.155)]


def _stacks(tmp_path, items, loose=(), as_block=None, at=(0.0, 0.0), rotacion=0.0):
    """Etiquetas centradas con sus renglones; ``loose`` son renglones sueltos (x, y)."""
    giro = math.radians(rotacion)

    def girar(x, y):
        return (x * math.cos(giro) - y * math.sin(giro), x * math.sin(giro) + y * math.cos(giro))

    def build(doc):
        msp = doc.modelspace()
        destino = doc.blocks.new(as_block) if as_block else msp
        for marca, (x, y), lineas in items:
            t = destino.add_text(marca, height=0.13, rotation=rotacion)
            t.set_placement(girar(x, y), align=TextEntityAlignment.BOTTOM_CENTER)
            for texto, dx, dy in lineas:
                destino.add_text(texto, height=0.10, rotation=rotacion).set_placement(
                    girar(x + dx, y + dy)
                )
        for texto, x, y in loose:
            destino.add_text(texto, height=0.10, rotation=rotacion).set_placement(girar(x, y))
        if as_block:
            msp.add_blockref(as_block, at)

    return _dxf(tmp_path, build)


def _dxf(tmp_path, build):
    doc = ezdxf.new("R2010")
    build(doc)
    path = tmp_path / "pilas.dxf"
    doc.saveas(path)
    return DxfParser().parse_file(path).entities


def _one_frame(ents, code="ES-200"):
    puntos = [ancla_texto(e) for e in ents if e.is_textual]
    xs, ys = [p[0] for p in puntos], [p[1] for p in puntos]
    caja = (min(xs) - 5.0, min(ys) - 5.0, max(xs) + 5.0, max(ys) + 5.0)
    return [SheetFrame(frame_id="f0", bbox=caja, source_file=ents[0].source_file, code=code)]


def _two_frames_split_at(ents, y):
    archivo = ents[0].source_file
    return [
        SheetFrame(frame_id="abajo", bbox=(-5.0, -5.0, 5.0, y), source_file=archivo, code="ES-100"),
        SheetFrame(frame_id="arriba", bbox=(-5.0, y, 5.0, 5.0), source_file=archivo, code="ES-200"),
    ]


def _huerfanos(rech):
    return sorted(r.texto for r in rech if r.motivo == "sin_dueno")


def test_marina_stacks_side_by_side(tmp_path):
    ents = _stacks(tmp_path, [("K-11", (0.0, 0.0), K11), ("K-12", (1.0, 0.0), K12)])
    asoc, rech = asociar(ents, _one_frame(ents), TextPatternConfig())
    by = {a.marca: a.textos for a in asoc}
    assert by == {
        "K-11": ["8#6", "2E#3EXT@10", "CENTRO@20"],
        "K-12": ["4#6+4#4", "2E#3EXT@10", "CENTRO@15"],
    }
    assert all(a.via == "pila" for a in asoc) and rech == []
    assert all(a.hoja == "ES-200" for a in asoc)
    k11 = next(a for a in asoc if a.marca == "K-11")
    por_id = {e.entity_id: e.text for e in ents}
    assert por_id[k11.etiqueta_id] == "K-11"
    assert [por_id[i] for i in k11.entidades] == k11.textos


def test_stack_inside_a_block(tmp_path):
    ents = _stacks(
        tmp_path, [("K-11", (0.0, 0.0), K11)], as_block="EST-CASTILLOS", at=(213.3, -2.0)
    )
    asoc, _ = asociar(ents, _one_frame(ents), TextPatternConfig())
    assert asoc[0].textos == ["8#6", "2E#3EXT@10", "CENTRO@20"]


def test_slab_label_never_attaches(tmp_path):
    ents = _stacks(
        tmp_path,
        [("K-12", (0.0, 0.0), K12)],
        loose=[("LOSA MACIZA DOBLEMENTE ARMADA H=20 LS #4@20 A/S LI #4@20 A/S", 0.0, 0.8)],
    )
    asoc, rech = asociar(ents, _one_frame(ents), TextPatternConfig())
    assert "LOSA" not in " ".join(asoc[0].textos)
    assert all(r.motivo != "sin_dueno" for r in rech)  # la etiqueta de losa es de la losa


def test_equidistant_line_is_rejected(tmp_path):
    # R8: a 0.085 de las dos etiquetas (de K-1 por arriba y de K-2 por abajo).
    ents = _stacks(
        tmp_path, [("K-1", (0.0, 0.0), []), ("K-2", (0.0, 0.40), [])], loose=[("6#4", -0.05, 0.215)]
    )
    asoc, rech = asociar(ents, _one_frame(ents), TextPatternConfig())
    assert asoc == [] and rech[0].motivo == "ambigua" and sorted(rech[0].marcas) == ["K-1", "K-2"]
    assert len(rech) == 1 and rech[0].texto == "6#4"


def test_other_frame_and_orphans(tmp_path):
    ents = _stacks(
        tmp_path, [("K-1", (0.0, 0.0), [])], loose=[("4#3", 0.0, 0.18), ("6#4", 30.0, 0.0)]
    )
    frames = _two_frames_split_at(ents, y=0.1)  # la etiqueta y su renglón en hojas distintas
    asoc, rech = asociar(ents, frames, TextPatternConfig())
    assert asoc == [] and {r.texto for r in rech if r.motivo == "sin_dueno"} == {"4#3", "6#4"}
    hojas = {r.texto: r.hoja for r in rech}
    assert hojas["4#3"] == "ES-200" and hojas["6#4"] == ents[0].source_file  # sin hoja: su archivo


def _marina(layout, d):
    """Un texto como lo guarda Marina: los centrados con su punto de alineación y el ``insert``
    que AutoCAD calculó (de ahí sale su ancho real)."""
    if "mtext" in d:
        layout.add_mtext(
            d["mtext"],
            dxfattribs={
                "insert": d["insert"],
                "char_height": d["alto"],
                "attachment_point": d["att"],
                "width": d["ancho"],
            },
        )
        return
    t = layout.add_text(d["texto"], height=d["alto"])
    if d["halign"] == 1:
        t.set_placement(d["align_point"], align=TextEntityAlignment.BOTTOM_CENTER)
        t.dxf.insert = d["insert"]
    else:
        t.set_placement(d["insert"])


# Lo que dice el plano bajo cada etiqueta del bloque EST-CASTILLOS (leído a mano del DXF).
CASTILLOS_DE_MARINA = {
    "K-0": ["REFUERZO 1#3"],
    "K-1": ["4#3", "E#2@15"],
    "K-2": ["4#3", "E#2@15"],
    "K-2A": ["4#4", "E#2@15"],
    "K-3": ["6#3", "EYG#2@15"],
    "K-3A": ["6#3", "EYG#2@15"],
    "K-4": ["6#4", "EYG#3@15"],
    "K-4A": ["4#4+2#3", "EYG#3@20"],
    "K-5": ["6#4", "EYG#3@15"],
    "K-6": ["4#5+2#4", "2E#3@15"],
    "K-6A": ["6#4", "2E#2@15"],
    "K-7": ["4#5+4#4", "2E#3@20"],
    "K-7A": ["6#5+4#4", "3E#3@20"],
    "K-8": ["8#4", "2E#3@20"],
    "K-9": ["4#6+2#4", "2E#3EXT@10", "CENTRO@15"],
    "K-10": ["6#6+4#4", "2E+1G#3EXT@10", "CENTRO@15"],  # su pila va DEBAJO de la etiqueta
    "K-11": ["8#6", "2E#3EXT@10", "CENTRO@20"],
    "K-12": ["4#6+4#4", "2E#3EXT@10", "CENTRO@15"],
    "K-14": ["8#6", "2E#3EXT@10", "CENTRO@15"],
    "K-15": ["8#8", "2E#3EXT@10", "CENTRO@20"],
    "K-15A": ["6#8+6#6", "4E#3EXT@10", "CENTRO@20"],
    "K-16": ["8#6", "2E#3EXT@10", "CENTRO@20"],
    "K-17": ["8#3", "2E#2@15"],
    "K-18": ["4#8+4#6", "2E#3EXT@10", "CENTRO@20"],
    "K-19": ["8#6", "2E#3EXT@10", "CENTRO@20"],
    "K-20": ["10#6", "2E#3EXT@10", "CENTRO@15"],
    "K-20A": ["8#6", "2E#3EXT@10", "CENTRO@15"],
    "K-X": ["REFUERZO 1#4"],
}


def test_marina_castillos_block_as_drawn(tmp_path):
    """El bloque EST-CASTILLOS de Marina, texto por texto, insertado en ES-200 y en ES-300."""
    datos = json.loads(
        (Path(__file__).parent / "fixtures" / "marina_est_castillos.json").read_text()
    )

    def build(doc):
        bloque = doc.blocks.new("EST-CASTILLOS")
        for d in datos["textos"]:
            _marina(bloque, d)
        msp = doc.modelspace()
        msp.add_blockref("EST-CASTILLOS", datos["insercion_es200"])
        msp.add_blockref("EST-CASTILLOS", (-0.44, -34.6607))  # la copia de ES-300

    ents = _dxf(tmp_path, build)
    archivo = ents[0].source_file
    frames = [
        SheetFrame(
            frame_id="f2", bbox=(185.34, -6.96, 229.34, 22.37), source_file=archivo, code="ES-200"
        ),
        SheetFrame(
            frame_id="f3", bbox=(185.34, -41.96, 229.34, -12.63), source_file=archivo, code="ES-300"
        ),
    ]
    asoc, rech = asociar(ents, frames, TextPatternConfig())
    for hoja in ("ES-200", "ES-300"):
        leidas = {a.marca: a.textos for a in asoc if a.hoja == hoja}
        assert leidas == CASTILLOS_DE_MARINA, hoja
    assert rech == []


COLUMNAS_Y_PILOTES_DE_MARINA = [
    {
        "texto": "COLUMNAS",
        "alto": 0.16,
        "halign": 1,
        "insert": [218.2173, 6.789],
        "align_point": [218.8497, 6.789],
    },
    {
        "texto": "ACOTACIONES EN CMS, SIN ESCALA",
        "alto": 0.1,
        "halign": 1,
        "insert": [217.4925, 6.4495],
        "align_point": [218.8497, 6.4495],
    },
    {
        "texto": "C-1",
        "alto": 0.13,
        "halign": 1,
        "insert": [215.4567, 7.0721],
        "align_point": [215.6176, 7.0721],
    },
    {"texto": "8#8", "alto": 0.1, "halign": 0, "insert": [215.5164, 7.5998]},
    {"texto": "2E#3EXT@10", "alto": 0.1, "halign": 0, "insert": [215.1856, 7.4159]},
    {"texto": "CENTRO@20", "alto": 0.1, "halign": 0, "insert": [215.1856, 7.2489]},
    {
        "texto": "C-2",
        "alto": 0.13,
        "halign": 1,
        "insert": [218.6224, 7.2406],
        "align_point": [218.8112, 7.2406],
    },
    {"texto": "10#8", "alto": 0.1, "halign": 0, "insert": [218.6762, 7.7683]},
    {"texto": "3E#3EXT@10", "alto": 0.1, "halign": 0, "insert": [218.3961, 7.5844]},
    {"texto": "CENTRO@20", "alto": 0.1, "halign": 0, "insert": [218.3961, 7.4173]},
    {
        "texto": "C-3",
        "alto": 0.13,
        "halign": 1,
        "insert": [221.9681, 6.9121],
        "align_point": [222.1569, 6.9121],
    },
    {"texto": "8#8+4#6", "alto": 0.1, "halign": 0, "insert": [221.843, 7.4398]},
    {"texto": "2E#3EXT@10", "alto": 0.1, "halign": 0, "insert": [221.7248, 7.2559]},
    {"texto": "CENTRO@20", "alto": 0.1, "halign": 0, "insert": [221.7248, 7.0889]},
    # El cuadro de pilotes de ES-000 (aquí corrido +0, -60 para caer en la misma hoja de prueba).
    {
        "texto": "PILOTES",
        "alto": 0.175,
        "halign": 1,
        "insert": [190.1427, 7.2749],
        "align_point": [190.6594, 7.2749],
    },
    {
        "texto": "ACOTACIONES EN CMS, SIN ESCALA",
        "alto": 0.1,
        "halign": 0,
        "insert": [189.1191, 6.9062],
    },
    {
        "texto": "P-2",
        "alto": 0.15,
        "halign": 1,
        "insert": [190.1642, 12.5611],
        "align_point": [190.4071, 12.5611],
    },
    {
        "texto": "2E#3 VER CORTE",
        "alto": 0.1,
        "halign": 1,
        "insert": [189.7937, 12.8089],
        "align_point": [190.4602, 12.8089],
    },
    {
        "texto": "REFUERZO 4#6+4#4",
        "alto": 0.1,
        "halign": 1,
        "insert": [189.5669, 13.0396],
        "align_point": [190.3596, 13.0396],
    },
    {
        "texto": "REFUERZO 12#6",
        "alto": 0.1,
        "halign": 1,
        "insert": [188.258, 8.4237],
        "align_point": [188.8888, 8.4237],
    },
    {
        "texto": "P-4",
        "alto": 0.15,
        "halign": 1,
        "insert": [188.6008, 7.9343],
        "align_point": [188.8472, 7.9343],
    },
    {
        "texto": "2E#3 VER CORTE",
        "alto": 0.1,
        "halign": 1,
        "insert": [188.2223, 8.1931],
        "align_point": [188.8888, 8.1931],
    },
    {
        "texto": "P-1",
        "alto": 0.15,
        "halign": 1,
        "insert": [187.4735, 12.7736],
        "align_point": [187.6949, 12.7736],
    },
    {
        "texto": "2E#3 VER CORTE",
        "alto": 0.1,
        "halign": 1,
        "insert": [187.0815, 13.0215],
        "align_point": [187.7481, 13.0215],
    },
    {
        "texto": "REFUERZO 4#5+4#4",
        "alto": 0.1,
        "halign": 1,
        "insert": [186.8547, 13.2521],
        "align_point": [187.6474, 13.2521],
    },
    # El armado de P-5 es un MTEXT de párrafos centrados («\\pxqc;») en una columna de 6.39
    # cuyo punto de inserción (arriba a la izquierda) cae junto a P-4: se lee centrado sobre P-5.
    {
        "texto": "P-5",
        "alto": 0.15,
        "halign": 1,
        "insert": [191.9977, 7.7727],
        "align_point": [192.2405, 7.7727],
    },
    {
        "texto": "P-3",
        "alto": 0.15,
        "halign": 1,
        "insert": [193.0831, 12.1699],
        "align_point": [193.3259, 12.1699],
    },
    {
        "texto": "2E#3 VER CORTE",
        "alto": 0.1,
        "halign": 1,
        "insert": [192.701, 12.4286],
        "align_point": [193.3675, 12.4286],
    },
    {
        "texto": "REFUERZO 4#8+4#4",
        "alto": 0.1,
        "halign": 1,
        "insert": [192.5748, 12.6592],
        "align_point": [193.3675, 12.6592],
    },
    {
        "mtext": "\\pxqc;4#8 + 12#6\\P3E#3 VER CORTE",
        "alto": 0.1,
        "att": 1,
        "insert": [189.0342, 8.3192],
        "ancho": 6.389176157551121,
    },
    # El cuadro de dados de ES-000 (corrido igual): la marca es «D-X», como «K-X».
    {
        "texto": "D-X",
        "alto": 0.13,
        "halign": 1,
        "insert": [219.2328, 16.2749],
        "align_point": [219.4216, 16.2749],
    },
    {"texto": "8#6", "alto": 0.1, "halign": 0, "insert": [219.3204, 16.672]},
    {"texto": "2E#3@10", "alto": 0.1, "halign": 0, "insert": [219.1089, 16.4881]},
    {
        "texto": "DADO",
        "alto": 0.16,
        "halign": 1,
        "insert": [219.155, 15.9179],
        "align_point": [219.4712, 15.9179],
    },
]


def test_marina_columns_and_piles_as_drawn(tmp_path):
    def build(doc):
        for d in COLUMNAS_Y_PILOTES_DE_MARINA:
            _marina(doc.modelspace(), d)

    ents = _dxf(tmp_path, build)
    asoc, rech = asociar(ents, _one_frame(ents), TextPatternConfig())
    assert {a.marca: a.textos for a in asoc} == {
        "C-1": ["8#8", "2E#3EXT@10", "CENTRO@20"],
        "C-2": ["10#8", "3E#3EXT@10", "CENTRO@20"],
        "C-3": ["8#8+4#6", "2E#3EXT@10", "CENTRO@20"],
        # Los pilotes dejan más aire entre renglones (0.23 de paso, 1.3 altos de hueco).
        "P-1": ["REFUERZO 4#5+4#4", "2E#3 VER CORTE"],
        "P-2": ["REFUERZO 4#6+4#4", "2E#3 VER CORTE"],
        "P-3": ["REFUERZO 4#8+4#4", "2E#3 VER CORTE"],
        "P-4": ["REFUERZO 12#6", "2E#3 VER CORTE"],
        "P-5": ["4#8 + 12#6", "3E#3 VER CORTE"],  # un MTEXT: un elemento por renglón
        "D-X": ["8#6", "2E#3@10"],
    }
    assert rech == []
    p5 = next(a for a in asoc if a.marca == "P-5")
    assert len(p5.entidades) == 2 and len(set(p5.entidades)) == 1  # los dos renglones del MTEXT


@pytest.mark.parametrize(
    "y_abajo,de_k1,huerfanos",
    [
        (-0.20, ["4#3", "E#2@15"], ["6#4"]),  # la de arriba está más cerca (0.05 contra 0.10)
        (-0.15, ["4#3", "E#2@15"], ["6#4"]),  # empate: gana la de arriba (la costumbre de Marina)
        (-0.13, ["6#4"], ["4#3", "E#2@15"]),  # la de abajo está más cerca (0.03 contra 0.05)
    ],
)
def test_a_label_owns_one_stack_the_nearer_one(tmp_path, y_abajo, de_k1, huerfanos):
    ents = _stacks(
        tmp_path,
        [("K-1", (0.0, 0.0), [("4#3", -0.1, 0.36), ("E#2@15", -0.2, 0.18)])],
        loose=[("6#4", -0.2, y_abajo)],
    )
    asoc, rech = asociar(ents, _one_frame(ents), TextPatternConfig())
    assert {a.marca: a.textos for a in asoc} == {"K-1": de_k1}
    assert _huerfanos(rech) == huerfanos and len(rech) == len(huerfanos)


def test_stack_below_its_label(tmp_path):
    # Otra costumbre (y la de K-10 en Marina): la etiqueta arriba, los renglones debajo.
    abajo = [
        ("6#6+4#4", -0.355, -0.257),
        ("2E+1G#3EXT@10", -0.593, -0.441),
        ("CENTRO@15", -0.465, -0.608),
    ]
    ents = _stacks(tmp_path, [("K-10", (0.0, 0.0), abajo)])
    asoc, rech = asociar(ents, _one_frame(ents), TextPatternConfig())
    assert asoc[0].textos == ["6#6+4#4", "2E+1G#3EXT@10", "CENTRO@15"] and rech == []


def test_a_label_floating_above_a_stack_makes_it_ambiguous(tmp_path):
    # K-2 alcanza por arriba la pila que K-1 alcanza por abajo, y no alcanza otra: la columna
    # está entre dos etiquetas y puede ser de cualquiera; no se decide por cuál está más pegada
    # (0.05 contra 0.10).
    ents = _stacks(
        tmp_path,
        [
            ("K-1", (0.0, 0.0), [("4#3", -0.2, 0.36), ("E#2@15", -0.2, 0.18)]),
            ("K-2", (0.0, 0.56), []),
        ],
    )
    asoc, rech = asociar(ents, _one_frame(ents), TextPatternConfig())
    assert asoc == []
    assert sorted((r.motivo, r.texto, tuple(r.marcas)) for r in rech) == [
        ("ambigua", "4#3", ("K-1", "K-2")),
        ("ambigua", "E#2@15", ("K-1", "K-2")),
    ]


def test_a_label_left_without_a_stack_makes_the_winners_ambiguous(tmp_path):
    """R55: K-1 y K-2 debajo de la misma pila, las dos enfrente de ella; K-1 está más pegada
    (0.03 contra 0.13), pero darle la pila deja a K-2 sin ninguna. Es la imagen en espejo de la
    etiqueta que tiene encima, más pegada, la pila de su vecina (la suya queda lejos): la
    geometría sola no distingue los dos casos, así que la pila se rechaza entera."""
    ents = _stacks(
        tmp_path,
        [
            ("K-1", (0.0, 0.0), [("4#3", -0.2, 0.33), ("E#2@15", -0.2, 0.16)]),
            ("K-2", (0.25, -0.10), []),
        ],
    )
    asoc, rech = asociar(ents, _one_frame(ents), TextPatternConfig())
    assert asoc == []
    assert sorted((r.motivo, r.texto, tuple(r.marcas)) for r in rech) == [
        ("ambigua", "4#3", ("K-1", "K-2")),
        ("ambigua", "E#2@15", ("K-1", "K-2")),
    ]


def test_the_stack_ends_at_a_wide_gap(tmp_path):
    # 0.17 de hueco (1.7 altos de renglón) ya no es la misma pila.
    ents = _stacks(tmp_path, [("K-1", (0.0, 0.0), [("4#3", -0.2, 0.45), ("E#2@15", -0.2, 0.18)])])
    asoc, rech = asociar(ents, _one_frame(ents), TextPatternConfig())
    assert asoc[0].textos == ["E#2@15"] and _huerfanos(rech) == ["4#3"]


def test_the_first_line_must_be_close_to_the_label(tmp_path):
    # El primer renglón empieza a lo más a 1.5 altos de etiqueta (0.195): a 0.25 no es suyo.
    ents = _stacks(tmp_path, [("K-1", (0.0, 0.0), [("E#2@15", -0.2, 0.38)])])
    asoc, rech = asociar(ents, _one_frame(ents), TextPatternConfig())
    assert asoc == [] and _huerfanos(rech) == ["E#2@15"]


def test_the_stack_must_overlap_the_label_horizontally(tmp_path):
    # A casi 0.5 de la orilla de la etiqueta (más de 3 altos de renglón) no es de su columna.
    ents = _stacks(tmp_path, [("K-1", (0.0, 0.0), [("E#2@15", 0.65, 0.18)])])
    asoc, rech = asociar(ents, _one_frame(ents), TextPatternConfig())
    assert asoc == [] and _huerfanos(rech) == ["E#2@15"]


@pytest.mark.parametrize(
    "x_k2,asociaciones,rechazos",
    [
        # Una etiqueta chica (K-2) metida entre dos renglones de la columna de K-1: la pila de
        # K-1 no pasa sobre ella, y como K-2 tiene enfrente el renglón largo apenas fuera de su
        # alcance (0.08 contra 0.075), ése puede ser suyo: nada se pega, todo se dice. El «4#4»
        # de más allá del corte sigue siendo un reclamo de K-1 (R55): ambiguo, no huérfano.
        (
            0.3,
            {},
            [
                ("ambigua", "2E#3EXT@10 CENTRO@20", ("K-1", "K-2")),
                ("ambigua", "4#4", ("K-1", "K-2")),
            ],
        ),
        # Sobre la punta del renglón largo, fuera de la columna de K-1, K-2 no la corta, pero
        # sigue teniendo ese renglón enfrente: la pila de K-1 queda en duda entera.
        (
            1.5,
            {},
            [
                ("ambigua", "2E#3EXT@10 CENTRO@20", ("K-1", "K-2")),
                ("ambigua", "4#4", ("K-1", "K-2")),
            ],
        ),
    ],
)
def test_a_stack_never_passes_over_another_label(tmp_path, x_k2, asociaciones, rechazos):
    def build(doc):
        msp = doc.modelspace()
        k1 = msp.add_text("K-1", height=0.13)
        k1.set_placement((0.0, 0.0), align=TextEntityAlignment.BOTTOM_CENTER)
        msp.add_text("2E#3EXT@10 CENTRO@20", height=0.10).set_placement((-0.2, 0.18))
        k2 = msp.add_text("K-2", height=0.05)
        k2.set_placement((x_k2, 0.36), align=TextEntityAlignment.BOTTOM_CENTER)
        msp.add_text("4#4", height=0.10).set_placement((-0.2, 0.42))

    ents = _dxf(tmp_path, build)
    asoc, rech = asociar(ents, _one_frame(ents), TextPatternConfig())
    assert {a.marca: a.textos for a in asoc} == asociaciones
    assert sorted((r.motivo, r.texto, tuple(r.marcas)) for r in rech) == rechazos


def test_a_stack_cut_by_another_label_is_never_read_in_part(tmp_path):
    # Una lista donde los renglones se meten a la altura de las etiquetas vecinas: la pila de K-4
    # topa con la etiqueta de K-3 y su «4#5» sigue al lado de ella. No se lee sólo «E#3@10».
    etiquetas, renglones, de_quien, y = [], [], {}, 0.0
    for marca, lineas in LISTA:
        yy = y
        for texto in reversed(lineas):
            renglones.append((texto, -0.2, yy))
            de_quien[(texto, -0.2, round(yy, 3))] = marca
            yy += 0.17
        base = y - 0.05 - 0.13
        etiquetas.append((marca, 0.0, base))
        y = base - 0.05 - 0.10
    ents = _pilas_libres(tmp_path, etiquetas, renglones)
    asoc, rech = asociar(ents, _one_frame(ents), TextPatternConfig())
    _ni_ajenas_ni_a_medias(ents, asoc, rech, de_quien)
    assert "K-4" not in {a.marca for a in asoc}


def test_another_familys_text_stops_the_stack_and_is_not_an_orphan(tmp_path):
    ents = _stacks(
        tmp_path,
        [("K-4", (0.0, 0.0), [("EYG#3@15", -0.37, 0.234)])],
        loose=[("LOSA H=20 #4@20 A/S", -0.37, 0.418), ("6#4", -0.13, 0.602)],
    )
    asoc, rech = asociar(ents, _one_frame(ents), TextPatternConfig())
    assert {a.marca: a.textos for a in asoc} == {"K-4": ["EYG#3@15"]}
    motivos = sorted((r.motivo, r.texto, tuple(r.marcas)) for r in rech)
    assert motivos == [("otra_familia", "LOSA H=20 #4@20 A/S", ("K-4",)), ("sin_dueno", "6#4", ())]


@pytest.mark.parametrize("con_lider", [True, False])
def test_a_callout_with_a_leader_is_not_a_stack_line(tmp_path, con_lider):
    """El detalle de T2-1 en Marina: «2#4» va junto al título, pero de él sale una directriz a
    las varillas del corte. Es de lo que señala, no de la pila de T2-1."""

    def build(doc):
        msp = doc.modelspace()
        msp.add_text("T2-1", height=0.14).set_placement((0.0, 0.0))
        t = msp.add_text("2#4", height=0.11)
        t.set_placement((0.8629, -0.2393), align=TextEntityAlignment.BOTTOM_CENTER)
        t.dxf.insert = (0.7215, -0.2393)
        if con_lider:
            msp.add_lwpolyline([(0.484, -0.631), (0.807, -0.271), (0.129, -0.631)])

    ents = _dxf(tmp_path, build)
    asoc, rech = asociar(ents, _one_frame(ents), TextPatternConfig())
    if con_lider:
        assert asoc == [] and _huerfanos(rech) == ["2#4"]
    else:
        assert [(a.marca, a.textos) for a in asoc] == [("T2-1", ["2#4"])] and rech == []


def test_numbered_notes_are_not_orphans(tmp_path):
    def build(doc):
        msp = doc.modelspace()
        msp.add_text("REFUERZO :", height=0.18).set_placement((0.0, 0.5))
        msp.add_text("4. SE PERMITE TRASLAPAR VARILLA HASTA EL", height=0.1).set_placement((0, 0))
        msp.add_text("#6 EN UNA MISMA SECCION.", height=0.1).set_placement((0.3, -0.17))
        msp.add_text("5.- ESTRIBOS #3@20 SALVO INDICACION", height=0.1).set_placement((0, -0.34))

    ents = _dxf(tmp_path, build)
    asoc, rech = asociar(ents, _one_frame(ents), TextPatternConfig())
    assert asoc == [] and rech == []


def test_cuadro_rows_are_owned_by_their_mark(tmp_path):
    # Un cuadro apretado: sin leer la fila, la marca de abajo tomaría el armado de la de arriba.
    def build(doc):
        msp = doc.modelspace()
        for x, titulo in ((0.0, "MARCA"), (0.5, "ARMADO"), (1.2, "ESTRIBOS")):
            msp.add_text(titulo, height=0.1).set_placement((x, 0.18))
        for y, fila in ((0.0, ("K-1", "4#3", "E#2@20")), (-0.18, ("K-2", "6#4", "E#3@15"))):
            for x, texto in zip((0.0, 0.5, 1.2), fila, strict=True):
                msp.add_text(texto, height=0.1).set_placement((x, y))

    ents = _dxf(tmp_path, build)
    asoc, rech = asociar(ents, _one_frame(ents), TextPatternConfig())
    assert {a.marca: (a.via, a.textos) for a in asoc} == {
        "K-1": ("fila", ["4#3", "E#2@20"]),
        "K-2": ("fila", ["6#4", "E#3@15"]),
    }
    assert rech == []


def test_a_cuadro_row_with_only_its_section_is_a_row_too(tmp_path):
    # Task 7: una fila con sólo su sección («K-2 | 20X30») también define su marca; antes sólo se
    # daban las filas con armado y la sección de K-2 no la leía nadie.
    def build(doc):
        msp = doc.modelspace()
        for x, titulo in ((0.0, "MARCA"), (0.5, "SECCION"), (1.2, "ARMADO")):
            msp.add_text(titulo, height=0.1).set_placement((x, 0.18))
        for y, fila in ((0.0, ("K-1", "15X20", "4#3")), (-0.18, ("K-2", "20X30", None))):
            for x, texto in zip((0.0, 0.5, 1.2), fila, strict=True):
                if texto:
                    msp.add_text(texto, height=0.1).set_placement((x, y))

    ents = _dxf(tmp_path, build)
    asoc, rech = asociar(ents, _one_frame(ents), TextPatternConfig())
    assert {a.marca: (a.via, a.textos) for a in asoc} == {
        "K-1": ("fila", ["15X20", "4#3"]),
        "K-2": ("fila", ["20X30"]),
    }
    assert rech == []


def test_a_row_of_legends_is_not_a_cuadro(tmp_path):
    # PRUEBA-1: las leyendas «K-0 / CASTILLO AHOGADO», «K-1 / CASTILLO»… a una misma altura a lo
    # largo de la hoja no son los títulos de un cuadro, ni lo de abajo sus filas.
    def build(doc):
        msp = doc.modelspace()
        for x, texto in (
            (3.1, "K-0\\PCASTILLO AHOGADO"),
            (18.4, "K-1\\PCASTILLO"),
            (21.2, "K-2\\PCASTILLO"),
        ):
            msp.add_mtext(texto, dxfattribs={"insert": (x, 0.0), "char_height": 0.1})
        msp.add_text("K-1", height=0.1).set_placement((18.3, -0.4))
        msp.add_text("2#4", height=0.1).set_placement((21.2, -0.4))

    ents = _dxf(tmp_path, build)
    asoc, rech = asociar(ents, _one_frame(ents), TextPatternConfig())
    assert asoc == [] and _huerfanos(rech) == ["2#4"]


def test_titles_far_apart_on_one_line_are_not_a_cuadro(tmp_path):
    # «MARCA», «ARMADO» y «ESTRIBOS» a la misma altura pero en tres vistas de la hoja (a 40 de
    # distancia) no son un encabezado: lo de abajo no son filas de un cuadro.
    def build(doc):
        msp = doc.modelspace()
        for x, titulo in ((0.0, "MARCA"), (40.0, "ARMADO"), (80.0, "ESTRIBOS")):
            msp.add_text(titulo, height=0.1).set_placement((x, 0.18))
        msp.add_text("K-1", height=0.1).set_placement((0.0, 0.0))
        msp.add_text("4#3", height=0.1).set_placement((40.0, 0.0))

    ents = _dxf(tmp_path, build)
    asoc, rech = asociar(ents, _one_frame(ents), TextPatternConfig())
    assert asoc == [] and _huerfanos(rech) == ["4#3"]


def test_a_text_beside_the_label_is_not_its_stack(tmp_path):
    # «4#3» se mete 0.03 en la altura de la etiqueta: está a su lado, no encima.
    ents = _stacks(tmp_path, [("K-1", (0.0, 0.0), [("4#3", 0.25, 0.10)])])
    asoc, rech = asociar(ents, _one_frame(ents), TextPatternConfig())
    assert asoc == [] and _huerfanos(rech) == ["4#3"]


def test_a_label_or_a_line_drawn_twice_is_read_once(tmp_path):
    # La misma etiqueta dos veces en el mismo lugar no es una ambigüedad; el renglón repetido
    # no se lee dos veces (8#6 + 8#6 serían 16 varillas) ni queda sin dueño.
    ents = _stacks(
        tmp_path,
        [("K-11", (0.0, 0.0), K11), ("K-11", (0.0, 0.0), [])],
        loose=[("8#6", 0.14, 0.54)],  # la copia, corrida unas milésimas
    )
    asoc, rech = asociar(ents, _one_frame(ents), TextPatternConfig())
    assert [(a.marca, a.textos) for a in asoc] == [("K-11", ["8#6", "2E#3EXT@10", "CENTRO@20"])]
    assert rech == []


def test_a_rotated_cuadro_reads_the_same(tmp_path):
    ents = _stacks(tmp_path, [("K-11", (0.0, 0.0), K11), ("K-12", (1.0, 0.0), K12)], rotacion=90.0)
    asoc, rech = asociar(ents, _one_frame(ents), TextPatternConfig())
    assert {a.marca: a.textos for a in asoc} == {
        "K-11": ["8#6", "2E#3EXT@10", "CENTRO@20"],
        "K-12": ["4#6+4#4", "2E#3EXT@10", "CENTRO@15"],
    }
    assert rech == []


@pytest.mark.parametrize(
    "texto,marca",
    [
        ("K-15A.1", "K-15A.1"),  # nunca K-15A: es otra marca
        ("K15A.1", "K-15A.1"),
        ("K-15A", "K-15A"),
        ("P-4", "P-4"),
        ("MC-1", "MC-1"),
        ("CE-1", "CE-1"),
        ("CR-2", "CR-2"),
        ("ZCM-3", "ZCM-3"),
        ("D-4B", "D-4B"),
        ("D-X", "D-X"),  # el tipo «X» (Marina: el dado D-X, el castillo K-X)
        ("DADO D-X", "D-X"),
        ("D-XX", None),
        ("CASTILLO K-3 15x15", "K-3"),
        ("K-1.", "K-1"),
        ("LOSA MACIZA H=20", None),
        ("MC-A", None),
    ],
)
def test_marca_en_texto(texto, marca):
    assert marca_en_texto(texto, TextPatternConfig()) == marca


@pytest.mark.parametrize(
    "texto,es_armado",
    [
        ("8#6", True),
        ("2E#3EXT@10", True),
        ("CENTRO@20", True),
        ("EXT@10", True),
        ("@20", True),
        ("# 4 @ 20", True),
        ("REFUERZO 12#6", True),
        ("4#8 + 12#6\n3E#3 VER CORTE", True),
        ("K-11", False),
        ("VER CORTE", False),
        ("15X20", False),
        ("2E", False),
        ("italohdez@gmail.com", False),
        ("CENTRO DE CARGA", False),
        ("EXTREMOS", False),
        ("CENTRO @ 20", True),
        ("EXT @10", True),
    ],
)
def test_armado_shaped_text(texto, es_armado):
    assert (ARMADO_RE.search(texto) is not None) is es_armado


# ------------------------------------------------- exclusividad: nunca la pila de otra marca

K4 = [("6#4", 0.134, 0.537), ("EYG#3@15", -0.179, 0.353), ("CENTRO@15", -0.179, 0.186)]


def _pilas_libres(tmp_path, etiquetas, renglones):
    """``etiquetas``: (marca, x, y) centradas abajo, alto 0.13; ``renglones``: (texto, x, y)."""

    def build(doc):
        msp = doc.modelspace()
        for marca, x, y in etiquetas:
            t = msp.add_text(marca, height=0.13)
            t.set_placement((x, y), align=TextEntityAlignment.BOTTOM_CENTER)
        for texto, x, y in renglones:
            msp.add_text(texto, height=0.10).set_placement((x, y))

    return _dxf(tmp_path, build)


def _con(marca, x, y, offsets):
    return [(marca, x, y)], [(t, x + dx, y + dy) for t, dx, dy in offsets]


def _ni_ajenas_ni_a_medias(ents, asoc, rech, de_quien):
    """Ninguna pila lleva un renglón de otra marca ni se queda con parte de la suya, y todo
    renglón que no se leyó se rechaza."""
    propios = _ids(ents, de_quien)
    _ninguna_ajena(asoc, propios)
    for a in asoc:
        assert set(a.entidades) == propios.get(a.marca, set()), (a.marca, a.textos)
    leidos = {e for a in asoc for e in a.entidades}
    rechazados = {r.entidad_id for r in rech}
    assert {i for ids in propios.values() for i in ids} <= leidos | rechazados


def _ninguna_ajena(asoc, propios):
    """Ninguna pila tiene un renglón que no sea de su marca."""
    for a in asoc:
        assert all(e in propios.get(a.marca, ()) for e in a.entidades), (a.marca, a.textos)


def _ids(ents, marca_de_texto):
    """{marca: ids de sus renglones} a partir de {(texto, x redondeada): marca}."""
    propios: dict[str, set[str]] = {}
    for e in ents:
        if e.is_textual:
            clave = (e.text, round(ancla_texto(e)[0], 3), round(ancla_texto(e)[1], 3))
            if clave in marca_de_texto:
                propios.setdefault(marca_de_texto[clave], set()).add(e.entity_id)
    return propios


@pytest.mark.parametrize(
    "x,y,leidas",
    [
        (0.85, 0.50, True),
        (0.85, 0.45, True),
        (0.9, 0.5, True),
        # R57: el primer renglón de la otra pila cae en la etiqueta ensanchada a 0.08 (0.03) del
        # tope de ésta y se encima con él en menos de la mitad del más angosto: puede ser el que
        # sigue en una pila con renglones alineados distinto. La pila no acaba limpia ahí.
        (-0.5, 0.5, False),
        (0.7, 0.55, False),
    ],
)
def test_staggered_neighbours_keep_their_own_stacks(tmp_path, x, y, leidas):
    # K-12 (primer hueco 0.025) y K-11 (0.056) escalonados: la pila de K-12 no sube por la
    # columna de K-11 ni K-11 toma la mitad de la de K-12 desde un lado.
    e1, r1 = _con("K-12", 0.0, 0.0, K12)
    e2, r2 = _con("K-11", x, y, K11)
    ents = _pilas_libres(tmp_path, e1 + e2, r1 + r2)
    asoc, rech = asociar(ents, _one_frame(ents), TextPatternConfig())
    if leidas:
        assert {a.marca: a.textos for a in asoc} == {
            "K-11": ["8#6", "2E#3EXT@10", "CENTRO@20"],
            "K-12": ["4#6+4#4", "2E#3EXT@10", "CENTRO@15"],
        }
        assert rech == []
    else:
        assert asoc == []
        assert sorted((r.texto, r.motivo, tuple(r.marcas)) for r in rech) == sorted(
            (t, "ambigua", ("K-11", "K-12")) for t, _, _ in K11 + K12
        )


@pytest.mark.parametrize("dx,dy", [(0.6, 0.0), (0.6, 0.02), (0.55, 0.03), (0.7, 0.03)])
def test_the_line_over_the_label_itself_goes_first(tmp_path, dx, dy):
    # Dos etiquetas a 0.6: el renglón de K-2 entra al ensanche de K-1 y está más pegado que el
    # de K-1, pero el que cae sobre la etiqueta misma va primero.
    e1, r1 = _con("K-1", 0.0, 0.0, [("4#3", -0.15, 0.36), ("E#2@15", -0.15, 0.18)])
    e2, r2 = _con("K-2", dx, dy, [("6#4", -0.15, 0.33), ("E#3@15", -0.15, 0.155)])
    ents = _pilas_libres(tmp_path, e1 + e2, r1 + r2)
    asoc, rech = asociar(ents, _one_frame(ents), TextPatternConfig())
    assert {a.marca: a.textos for a in asoc} == {"K-1": ["4#3", "E#2@15"], "K-2": ["6#4", "E#3@15"]}
    assert rech == []


@pytest.mark.parametrize("dy", [0.0, 0.03, 0.05, 0.08])
def test_a_long_line_does_not_bridge_into_the_next_column(tmp_path, dy):
    # El renglón largo de K-10 («2E+1G#3EXT@10») llega 0.02 a la columna de K-9: ni K-10 toma
    # el estribo de K-9 ni K-9 sube por el renglón de K-10.
    k10 = [("6#6+4#4", -0.20, 0.56), ("2E+1G#3EXT@10", -0.45, 0.33), ("CENTRO@15", -0.45, 0.16)]
    k9 = [("8#6", -0.15, 0.55 + dy), ("2E#3@15", -0.30, 0.37 + dy), ("E#2@20", -0.30, 0.19 + dy)]
    e1, r1 = _con("K-10", 0.0, 0.0, k10)
    e2, r2 = _con("K-9", 1.0, 0.0, k9)
    ents = _pilas_libres(tmp_path, e1 + e2, r1 + r2)
    asoc, rech = asociar(ents, _one_frame(ents), TextPatternConfig())
    assert {a.marca: a.textos for a in asoc} == {
        "K-10": ["6#6+4#4", "2E+1G#3EXT@10", "CENTRO@15"],
        "K-9": ["8#6", "2E#3@15", "E#2@20"],
    }
    assert rech == []


LISTA = [
    ("K-1", ["4#3", "E#2@15"]),
    ("K-2", ["6#4", "E#3@15"]),
    ("K-3", ["8#4", "E#3@20"]),
    ("K-4", ["4#5", "E#3@10"]),
]


def _lista(tmp_path, etiqueta_arriba, propio, al_siguiente, paso=0.17):
    """Una lista vertical de marcas: cada etiqueta a ``propio`` de su pila (debajo de ella si
    ``etiqueta_arriba``, encima si no) y a ``al_siguiente`` de la pila del grupo vecino."""
    etiquetas, renglones, de_quien = [], [], {}
    y = 0.0
    for marca, lineas in LISTA:
        if etiqueta_arriba:
            etiquetas.append((marca, 0.0, y))
            yy = y - propio - 0.10
            for texto in lineas:
                renglones.append((texto, -0.2, yy))
                de_quien[(texto, -0.2, round(yy, 3))] = marca
                yy -= paso
            y = yy + paso - al_siguiente - 0.13
        else:
            yy = y - 0.10
            for texto in lineas:
                renglones.append((texto, -0.2, yy))
                de_quien[(texto, -0.2, round(yy, 3))] = marca
                yy -= paso
            base = yy + paso - propio - 0.13
            etiquetas.append((marca, 0.0, base))
            y = base - al_siguiente
    return _pilas_libres(tmp_path, etiquetas, renglones), de_quien


@pytest.mark.parametrize(
    "etiqueta_arriba,propio,al_siguiente",
    [
        (True, 0.05, 0.05),  # todo a 0.05: cada pila está igual de cerca de dos etiquetas
        (True, 0.05, 0.045),
        (True, 0.06, 0.05),  # la etiqueta, más pegada a la pila de arriba que a la suya
        (False, 0.06, 0.05),  # lo mismo en la costumbre de Marina
        (False, 0.07, 0.05),
    ],
)
def test_a_vertical_list_never_shifts_definitions(tmp_path, etiqueta_arriba, propio, al_siguiente):
    ents, de_quien = _lista(tmp_path, etiqueta_arriba, propio, al_siguiente)
    asoc, rech = asociar(ents, _one_frame(ents), TextPatternConfig())
    _ni_ajenas_ni_a_medias(ents, asoc, rech, de_quien)
    assert any(r.motivo == "ambigua" for r in rech)


@pytest.mark.parametrize(
    "etiqueta_arriba,propio,al_siguiente",
    [(True, 0.05, 0.07), (False, 0.05, 0.08)],
)
def test_a_vertical_list_with_clear_gaps_reads_every_mark(
    tmp_path, etiqueta_arriba, propio, al_siguiente
):
    ents, _ = _lista(tmp_path, etiqueta_arriba, propio, al_siguiente)
    asoc, rech = asociar(ents, _one_frame(ents), TextPatternConfig())
    assert {a.marca: a.textos for a in asoc} == dict(LISTA) and rech == []


def _espejo(offsets):
    """Los mismos renglones, debajo de la etiqueta (la costumbre de otras oficinas)."""
    return [(t, dx, 0.13 - dy - 0.10) for t, dx, dy in offsets]


def _dos_filas(tmp_path, hueco, marina, al_reves=False):
    """K-4 con su pila y, en la fila de al lado, la etiqueta de K-11 a ``hueco`` de esa pila
    (encima de su tope en la costumbre de Marina; debajo de su pie en la otra)."""
    k4, k11 = (K4, K11) if marina else (_espejo(K4), _espejo(K11))
    if marina:
        y11 = max(dy for _, _, dy in k4) + 0.10 + hueco
    else:
        y11 = min(dy for _, _, dy in k4) - hueco - 0.13
    e1, r1 = _con("K-4", 0.0, 0.0, k4)
    e2, r2 = _con("K-11", 0.0, y11, k11)
    etiquetas, renglones = (e2 + e1, r2 + r1) if al_reves else (e1 + e2, r1 + r2)
    ents = _pilas_libres(tmp_path, etiquetas, renglones)
    de_quien = {
        (t, round(x, 3), round(y, 3)): m for m, rs in (("K-4", r1), ("K-11", r2)) for t, x, y in rs
    }
    return ents, de_quien


@pytest.mark.parametrize("hueco", [0.02, 0.03, 0.04, 0.045, 0.06])
@pytest.mark.parametrize("marina", [True, False])
@pytest.mark.parametrize("al_reves", [False, True])
def test_tight_rows_are_ambiguous_never_shifted(tmp_path, hueco, marina, al_reves):
    """R54: dos filas apretadas — la etiqueta de K-11 a ``hueco`` de la pila de K-4 y a 0.056 de
    la suya. Nunca se lleva el armado de K-4: o se rechaza todo, o cada una lee la suya."""
    ents, de_quien = _dos_filas(tmp_path, hueco, marina, al_reves)
    asoc, rech = asociar(ents, _one_frame(ents), TextPatternConfig())
    _ni_ajenas_ni_a_medias(ents, asoc, rech, de_quien)
    ambiguos = {r.entidad_id for r in rech if r.motivo == "ambigua"}
    if hueco <= 0.045:  # K-11 queda más pegada a la pila de K-4 que a la suya
        assert "K-4" not in {a.marca for a in asoc}
        assert _ids(ents, de_quien)["K-4"] <= ambiguos


@pytest.mark.parametrize("hueco", [0.045, 0.05, 0.06, 0.07])
def test_r54_opposite_sides_within_25_percent_are_ambiguous(tmp_path, hueco):
    # Una etiqueta sola (sin pila propia) a ``hueco`` encima de la pila de K-4, que está a 0.056
    # de la suya: desde lados opuestos, a menos de 25 % es ambiguo.
    e1, r1 = _con("K-4", 0.0, 0.0, K4)
    ents = _pilas_libres(tmp_path, e1 + [("K-11", 0.0, 0.637 + hueco)], r1)
    asoc, rech = asociar(ents, _one_frame(ents), TextPatternConfig())
    assert asoc == []
    assert sorted((r.motivo, r.texto, tuple(r.marcas)) for r in rech) == [
        ("ambigua", t, ("K-11", "K-4")) for t in sorted(t for t, _, _ in K4)
    ]


@pytest.mark.parametrize("marina", [True, False])
def test_rows_far_enough_apart_read_both(tmp_path, marina):
    # La etiqueta de la otra fila a 0.15 de la pila: K-4 la tiene más cerca (0.056), así que
    # el alcance de K-11 hacia ella muere y K-11 se queda con la suya.
    ents, _ = _dos_filas(tmp_path, 0.15, marina)
    asoc, rech = asociar(ents, _one_frame(ents), TextPatternConfig())
    orden = (lambda xs: xs) if marina else (lambda xs: xs[::-1])
    assert {a.marca: a.textos for a in asoc} == {
        "K-4": orden(["6#4", "EYG#3@15", "CENTRO@15"]),
        "K-11": orden(["8#6", "2E#3EXT@10", "CENTRO@20"]),
    }
    assert rech == []


def test_texts_that_name_a_mark_are_read_or_reported(tmp_path):
    def build(doc):
        msp = doc.modelspace()
        k1 = msp.add_text("K-1", height=0.13)
        k1.set_placement((0.0, 0.0), align=TextEntityAlignment.BOTTOM_CENTER)
        # «VER CORTE C-2» remite a otra parte: no reclama C-2, el renglón es de la pila de K-1.
        msp.add_text("E#2@15 VER CORTE C-2", height=0.10).set_placement((-0.2, 0.18))
        msp.add_text("4#3", height=0.10).set_placement((-0.2, 0.36))
        for x, texto in [
            # Sólo estribos: desde Task 7 (ronda 1) la nota los lee, con espacio también.
            (10, "K-7 E#3@20"),
            (15, "K-8 E #3@20"),
            (17, "K-9 E#3@1S"),  # unos estribos que nadie lee: sin lector, con su marca
            (20, "CASTILLOS E#2@20 EN TODOS"),
            (30, "COLUMNAS: ESTRIBOS #3@15"),  # la nota lo lee como malla (y avisa)
            (35, "K-3 #4@20"),  # una malla con su marca: la nota la lee
            (40, "2E#3@15 VER P-1"),  # un renglón suelto que remite a P-1
            (50, "K-1 15x20 4#3 E#2@20"),  # lo lee la nota: sección y varillas
            (60, "CASTILLOS 15X15 4#3 E#2@20"),  # nota de familia leída
        ]:
            msp.add_text(texto, height=0.10).set_placement((x, 5.0))

    ents = _dxf(tmp_path, build)
    asoc, rech = asociar(ents, _one_frame(ents), TextPatternConfig())
    assert {a.marca: a.textos for a in asoc} == {"K-1": ["4#3", "E#2@15 VER CORTE C-2"]}
    assert sorted((r.motivo, r.texto, tuple(r.marcas)) for r in rech) == [
        ("sin_dueno", "2E#3@15 VER P-1", ()),
        ("sin_lector", "CASTILLOS E#2@20 EN TODOS", ()),
        ("sin_lector", "K-9 E#3@1S", ("K-9",)),
    ]


def test_another_family_in_the_first_position_blocks_that_side(tmp_path):
    # La etiqueta de losa justo encima de K-4 tapa ese lado: K-4 no salta sobre ella, lo de
    # arriba queda sin dueño y la losa no es huérfana (es de la losa).
    ents = _stacks(
        tmp_path,
        [("K-4", (0.0, 0.0), [])],
        loose=[("LOSA H=20 #4@20 A/S", -0.37, 0.18), ("6#4", -0.13, 0.36)],
    )
    asoc, rech = asociar(ents, _one_frame(ents), TextPatternConfig())
    assert asoc == [] and [(r.motivo, r.texto) for r in rech] == [("sin_dueno", "6#4")]


def test_lines_rotated_a_fraction_of_a_degree_read_with_their_label(tmp_path):
    def build(doc):
        msp = doc.modelspace()
        t = msp.add_text("K-11", height=0.13)
        t.set_placement((0.0, 0.0), align=TextEntityAlignment.BOTTOM_CENTER)
        for texto, dx, dy in K11:
            msp.add_text(texto, height=0.10, rotation=0.6).set_placement((dx, dy))

    ents = _dxf(tmp_path, build)
    asoc, rech = asociar(ents, _one_frame(ents), TextPatternConfig())
    assert [a.textos for a in asoc] == [["8#6", "2E#3EXT@10", "CENTRO@20"]] and rech == []


def test_ancla_texto_lives_in_textos_and_is_re_exported():
    from klave_engine.estructura import asociacion, textos

    assert asociacion.ancla_texto is textos.ancla_texto


# ------------------------------------------- cuadros al azar que antes se leían mal (regresión)

PLANTILLAS = [
    K11,
    K12,
    [("6#4", 0.065, 0.451), ("EYG#3@15", -0.174, 0.268)],
    [("4#3", -0.1, 0.36), ("E#2@15", -0.2, 0.18)],
]


def _cuadro_al_azar(tmp_path, semilla, mezcla):
    """Un cuadro de 2 a 18 marcas apretado al azar (la etiqueta debajo de su pila o, en ``mezcla``
    al azar por marca, encima); devuelve las entidades y de qué marca es cada renglón."""
    rnd = random.Random(semilla)
    abajo = rnd.random() < 0.3
    etiquetas, renglones, de_quien, n = [], [], {}, 0
    for i in range(rnd.randint(2, 6)):
        for j in range(rnd.randint(1, 3)):
            n += 1
            marca = f"K-{n}"
            x = i * rnd.uniform(0.45, 1.4) + rnd.uniform(-0.25, 0.25)
            y = j * rnd.uniform(0.45, 1.2) + rnd.uniform(-0.25, 0.25)
            etiquetas.append((marca, x, y))
            escala = rnd.uniform(0.8, 1.3)
            if mezcla:
                abajo = rnd.random() < 0.3
            for texto, dx, dy in rnd.choice(PLANTILLAS):
                yy = (0.13 - dy * escala - 0.10) if abajo else dy * escala
                xx = x + dx + rnd.uniform(-0.05, 0.05)
                renglones.append((texto, xx, y + yy))
                de_quien[(texto, round(xx, 3), round(y + yy, 3))] = marca
    return _pilas_libres(tmp_path, etiquetas, renglones), de_quien


@pytest.mark.parametrize(
    "semilla,mezcla",
    [(s, False) for s in (849, 1276, 3184, 3255, 3325, 3745, 3839, 8512, 9236, 9396, 13492, 15040)]
    + [(s, True) for s in (307, 636, 1927, 2375, 2718, 3404, 3549, 7660, 8651, 9860, 10547)],
)
def test_crowded_random_cuadros_never_read_a_foreign_or_partial_stack(tmp_path, semilla, mezcla):
    """Cuadros apretados al azar que en el desarrollo daban la pila de otra marca o una a medias:
    lo que se lee es entero y de su marca; lo demás se rechaza."""
    ents, de_quien = _cuadro_al_azar(tmp_path, semilla, mezcla)
    asoc, rech = asociar(ents, _one_frame(ents), TextPatternConfig())
    _ni_ajenas_ni_a_medias(ents, asoc, rech, de_quien)


# ------------------------------------- R55: lo que se disputa se rechaza, nunca se adivina dueño


def _con_dueno(etiquetas, renglones_por_marca):
    """Etiquetas (marca, x, y) y {marca: [(texto, x, y)]}: los renglones y de quién es cada uno."""
    renglones = [r for rs in renglones_por_marca.values() for r in rs]
    de_quien = {
        (t, round(x, 3), round(y, 3)): m for m, rs in renglones_por_marca.items() for t, x, y in rs
    }
    return etiquetas, renglones, de_quien


@pytest.mark.parametrize("x3", [0.05, 0.075])
@pytest.mark.parametrize("y6", [0.70, 0.72, 0.76, 0.80])
@pytest.mark.parametrize("alto", [0.08, 0.10])
def test_lines_beyond_a_cut_stay_claimed_by_their_columns_owner(tmp_path, x3, y6, alto):
    """R55 (la semilla 10805 del revisor): la columna de K-2 topa con la etiqueta de K-3 y sigue
    en «8#6», que K-3 no alcanza. K-6, encima de «8#6» y sin pila propia, lo alcanza. «8#6» sigue
    siendo un reclamo de K-2: K-6 no se lo lleva sin oposición.

    Con «8#6» de 0.08 la columna de K-6 acaba en él (el hueco a «2E#3EXT@10» pasa de 1.5 altos
    suyos): sólo el reclamo de K-2 más allá del corte lo separa de leer un renglón ajeno. Con 0.10
    sigue hacia abajo y K-3 sólo le queda enfrente de lado: un corte que no es limpio (R56), y lo de
    abajo también es un reclamo de K-6."""

    def build(doc):
        msp = doc.modelspace()
        for marca, x, y in [("K-2", 0.45, 0.0), ("K-3", x3, 0.47), ("K-6", 0.765, y6)]:
            t = msp.add_text(marca, height=0.13)
            t.set_placement((x, y), align=TextEntityAlignment.BOTTOM_CENTER)
        msp.add_text("CENTRO@20", height=0.10).set_placement((0.0, 0.18))
        msp.add_text("2E#3EXT@10", height=0.10).set_placement((0.0, 0.35))
        msp.add_text("8#6", height=alto).set_placement((0.63, 0.58))

    ents = _dxf(tmp_path, build)
    de_quien = {
        (t, x, y): "K-2"
        for t, x, y in [("CENTRO@20", 0.0, 0.18), ("2E#3EXT@10", 0.0, 0.35), ("8#6", 0.63, 0.58)]
    }
    asoc, rech = asociar(ents, _one_frame(ents), TextPatternConfig())
    _ni_ajenas_ni_a_medias(ents, asoc, rech, de_quien)
    assert asoc == []
    abajo = ("K-2", "K-3") if alto == 0.08 else ("K-2", "K-3", "K-6")
    assert sorted((r.motivo, r.texto, tuple(r.marcas)) for r in rech) == [
        ("ambigua", "2E#3EXT@10", abajo),
        ("ambigua", "8#6", ("K-2", "K-3", "K-6")),
        ("ambigua", "CENTRO@20", abajo),
    ]


def _bajo_una_pila_ajena(dy, g2, limpias=False):
    """K-2 justo debajo del tope de la pila de K-1 («EYG#3@15» le queda enfrente) y su propia
    pila a ``g2`` encima; con ``limpias``, tres marcas lejos con su pila debajo de la etiqueta
    (la costumbre del cuadro)."""
    etiquetas = [("K-1", 0.0, 0.0), ("K-2", 0.5, dy)]
    base = dy + 0.13 + g2
    renglones = {
        "K-1": [("EYG#3@15", -0.2, 0.25), ("6#4", 0.0, 0.42)],
        "K-2": [("E#2@20", 0.33, base), ("4#3", 0.40, base + 0.17)],
    }
    if limpias:
        for n, x in ((3, 5.0), (4, 7.0), (5, 9.0)):
            etiquetas.append((f"K-{n}", x, 0.0))
            renglones[f"K-{n}"] = [("E#2@15", x - 0.2, 0.18), ("4#3", x - 0.1, 0.36)]
    return _con_dueno(etiquetas, renglones)


@pytest.mark.parametrize(
    "dy,g2,limpias",
    [(dy, g2, False) for dy in (0.08, 0.10) for g2 in (0.15, 0.20, 0.35)]  # min2 del revisor
    + [(dy, 0.35, False) for dy in (0.0, 0.02, 0.06)]  # min3
    + [(dy, 0.35, True) for dy in (0.02, 0.06, 0.10)],  # min3 con la costumbre del cuadro
)
def test_a_label_facing_a_foreign_stack_top_takes_nothing(tmp_path, dy, g2, limpias):
    etiquetas, renglones, de_quien = _bajo_una_pila_ajena(dy, g2, limpias)
    ents = _pilas_libres(tmp_path, etiquetas, renglones)
    asoc, rech = asociar(ents, _one_frame(ents), TextPatternConfig())
    _ni_ajenas_ni_a_medias(ents, asoc, rech, de_quien)
    assert {a.marca for a in asoc} == ({"K-3", "K-4", "K-5"} if limpias else set())
    # R57: «4#3» de K-2 cae en la etiqueta ensanchada de K-1 justo encima de su tope «6#4» sin
    # encimarse con él: la pila de K-1 no acaba limpia ahí y «4#3» sigue siendo un reclamo suyo.
    # «E#2@20» también: si la pila de K-2 empieza más arriba que «6#4», por R57; si no, va a su
    # lado y le queda más lejos del centro de K-1 que «6#4», pero K-2 no lo alcanza por su columna
    # (su primer renglón es «EYG#3@15», el de K-1), así que no es de la columna de al lado (R60):
    # antes de R60 nadie lo reclamaba (sin dueño); ahora lo reclaman las dos.
    k1k2 = ("K-1", "K-2")
    assert sorted((r.motivo, r.texto, tuple(r.marcas)) for r in rech) == sorted(
        [
            ("ambigua", "6#4", k1k2),
            ("ambigua", "EYG#3@15", k1k2),
            ("ambigua", "4#3", k1k2),
            ("ambigua", "E#2@20", k1k2),
        ]
    )


def _columna_de_tres(k2gap, junta, con_k1=True):
    """minC del revisor: tres pilas en una columna; K-1 y K-2 debajo de su pila, K-3 encima de
    la suya. K-2 casi pegada al tope de la de K-1; la de K-3 casi toca el tope de la de K-2."""
    etiquetas, renglones = [], {}
    if con_k1:
        etiquetas.append(("K-1", 0.0, 0.0))
        renglones["K-1"] = [
            ("CENTRO@15", -0.2, 0.17),
            ("2E#3EXT@10", -0.2, 0.35),
            ("4#6+4#4", -0.1, 0.53),
        ]
    y2 = 0.63 + k2gap
    etiquetas.append(("K-2", 0.0, y2))
    renglones["K-2"] = [
        ("CENTRO@20", -0.2, y2 + 0.23),
        ("2E#3EXT@10", -0.2, y2 + 0.41),
        ("8#6", 0.1, y2 + 0.59),
    ]
    y3 = y2 + 0.69 + junta
    renglones["K-3"] = [
        ("4#6+4#4", -0.1, y3),
        ("2E#3EXT@10", -0.2, y3 + 0.18),
        ("CENTRO@15", -0.2, y3 + 0.36),
    ]
    etiquetas.append(("K-3", 0.0, y3 + 0.50))
    return _con_dueno(etiquetas, renglones)


@pytest.mark.parametrize(
    "k2gap,junta,con_k1",
    [(g, j, True) for g in (0.045, 0.05, 0.055) for j in (0.08, 0.14)] + [(0.05, 0.10, False)],
)
def test_a_column_of_stacks_with_mixed_sides_is_rejected_whole(tmp_path, k2gap, junta, con_k1):
    etiquetas, renglones, de_quien = _columna_de_tres(k2gap, junta, con_k1)
    ents = _pilas_libres(tmp_path, etiquetas, renglones)
    asoc, rech = asociar(ents, _one_frame(ents), TextPatternConfig())
    _ni_ajenas_ni_a_medias(ents, asoc, rech, de_quien)
    assert asoc == []
    assert {r.motivo for r in rech} == {"ambigua"} and len(rech) == len(renglones)


@pytest.mark.parametrize("x2", [0.60, 0.68, 0.75])
@pytest.mark.parametrize("y2", [-0.115, -0.09])
@pytest.mark.parametrize("propia", [True, False])
def test_a_label_beside_a_stack_never_takes_part_of_it(tmp_path, x2, y2, propia):
    """minP del revisor: K-1 encima de su pila; K-2 (debajo de la suya) al lado de K-1, sobre la
    punta de su primer renglón y con el segundo, el largo, a su alcance. La pila de K-1 nunca se
    lee a medias ni la toma K-2; K-2 lee la suya entera o nada."""
    renglones = {
        "K-1": [("CENTRO@20", -0.17, -0.21), ("2E#3EXT@10", -0.16, -0.37), ("8#6", 0.15, -0.55)]
    }
    if propia:
        renglones["K-2"] = [
            ("CENTRO@15", x2 - 0.15, y2 + 0.27),
            ("2E#3EXT@10", x2 - 0.2, y2 + 0.45),
            ("4#6+4#4", x2 - 0.1, y2 + 0.63),
        ]
    etiquetas, renglones_, de_quien = _con_dueno([("K-1", 0.0, 0.0), ("K-2", x2, y2)], renglones)
    ents = _pilas_libres(tmp_path, etiquetas, renglones_)
    asoc, rech = asociar(ents, _one_frame(ents), TextPatternConfig())
    _ni_ajenas_ni_a_medias(ents, asoc, rech, de_quien)
    assert "K-1" not in {a.marca for a in asoc}
    de_k1 = _ids(ents, de_quien)["K-1"]
    assert {(r.entidad_id, r.motivo, tuple(r.marcas)) for r in rech if r.entidad_id in de_k1} == {
        (i, "ambigua", ("K-1", "K-2")) for i in de_k1
    }


@pytest.mark.parametrize(
    "etiqueta,marcas",
    [
        ("K-1, K-2", ("K-1", "K-2")),
        ("K-1 Y K-2", ("K-1", "K-2")),
        ("K-1=K-2", ("K-1", "K-2")),
        ("K-1/K-2", ("K-1", "K-2")),
        # Un rango se reporta como está escrito: no se adivinan las marcas de en medio.
        ("K-1 A K-4", ("K-1 A K-4",)),
        ("K-1 AL K-4", ("K-1 AL K-4",)),
        ("K-1 Y K-5 A K-7", ("K-1", "K-5 A K-7")),
        ("K-1 – K-4", ("K-1 – K-4",)),
        ("K-1 A 4", ("K-1 A 4",)),
        ("DE K-1 A K-4", ("DE K-1 A K-4",)),
        ("K-1 HASTA K-4", ("K-1 HASTA K-4",)),
        ("K-1 A K-2 A K-3", ("K-1 A K-2 A K-3",)),
    ],
)
@pytest.mark.parametrize("hueco", [0.02, 0.04])
@pytest.mark.parametrize("limpias", [False, True])
def test_a_label_with_several_marks_claims_its_stack_and_reports_it(
    tmp_path, etiqueta, marcas, hueco, limpias
):
    """multi2 del revisor: una etiqueta con varias marcas reclama su pila como cualquier otra (la
    de K-3, encima, no se la lleva) y esa pila se reporta con las marcas, nunca se le da a una."""
    etiquetas = [(etiqueta, 0.0, 0.0), ("K-3", 0.0, 0.606 + hueco)]
    renglones = {
        etiqueta: [(t, dx, dy) for t, dx, dy in K12],
        "K-3": [(t, dx, 0.606 + hueco + dy) for t, dx, dy in K11],
    }
    if limpias:
        for n, x in ((8, 5.0), (9, 7.0), (10, 9.0)):
            etiquetas.append((f"K-{n}", x, 0.0))
            renglones[f"K-{n}"] = [(t, x + dx, dy) for t, dx, dy in K11]
    etiquetas, renglones_, de_quien = _con_dueno(etiquetas, renglones)
    ents = _pilas_libres(tmp_path, etiquetas, renglones_)
    asoc, rech = asociar(ents, _one_frame(ents), TextPatternConfig())
    _ni_ajenas_ni_a_medias(ents, asoc, rech, de_quien)
    leidas = {a.marca for a in asoc} - {"K-8", "K-9", "K-10"}
    motivos = {(r.motivo, tuple(r.marcas)) for r in rech}
    if hueco == 0.02:  # K-3 más pegada a la pila de abajo que a la suya: todo en duda
        assert leidas == set() and motivos == {("ambigua", tuple(sorted({*marcas, "K-3"})))}
    else:
        assert leidas == {"K-3"} and motivos == {("varias_marcas", marcas)}
        assert len(rech) == len(K12)


# ------------------------------------------- los cuadros al azar del revisor (prueba por semillas)

REVISOR = [*PLANTILLAS, [("12#8", -0.12, 0.36), ("E#4@10", -0.2, 0.18)]]


def _cuadro_del_revisor(tmp_path, semilla, mezcla, sin_pila):
    """El generador del revisor (R55), con su mismo orden de sorteos: 2 a 4 columnas de 1 a 3
    marcas a 0.4–1.0 por 0.5–1.1, cada pila a 0.02–0.16 de su etiqueta, encima o debajo (40 %,
    por cuadro o, en ``mezcla``, por marca), a escala 0.85–1.2; en ``sin_pila`` una de cada cinco
    etiquetas no tiene pila. ``None`` si dos textos quedan a menos de 0.02 (no se lee ni a ojo)."""
    rnd = random.Random(semilla)
    de_quien: dict[tuple[str, float, float], str] = {}

    def build(doc):
        msp = doc.modelspace()
        abajo = rnd.random() < 0.4
        sx, sy = rnd.uniform(0.4, 1.0), rnd.uniform(0.5, 1.1)
        n = 0
        for i in range(rnd.randint(2, 4)):
            for j in range(rnd.randint(1, 3)):
                n += 1
                x = i * sx + rnd.uniform(-0.2, 0.2)
                y = j * sy + rnd.uniform(-0.15, 0.15)
                t = msp.add_text(f"K-{n}", height=0.13)
                t.set_placement((x, y), align=TextEntityAlignment.BOTTOM_CENTER)
                if mezcla:
                    abajo = rnd.random() < 0.4
                hueco, escala = rnd.uniform(0.02, 0.16), rnd.uniform(0.85, 1.2)
                pila = rnd.choice(REVISOR)
                if sin_pila and rnd.random() < 0.2:
                    pila = []
                dy0 = min((dy for _, _, dy in pila), default=0.0)
                for texto, dx, dy in pila:
                    rel = (dy - dy0) * escala
                    yy = y + ((-hueco - 0.10 - rel) if abajo else (0.13 + hueco + rel))
                    xx = x + dx + rnd.uniform(-0.05, 0.05)
                    msp.add_text(texto, height=0.10).set_placement((xx, yy))
                    de_quien[(texto, round(xx, 3), round(yy, 3))] = f"K-{n}"

    ents = _dxf(tmp_path, build)
    cajas = []
    for e in ents:
        if e.is_textual:
            (ax, ay), (dx0, dx1, dy0, dy1, _) = ancla_texto(e), caja_de_texto(e, 0.0)
            cajas.append((ax + dx0, ax + dx1, ay + dy0, ay + dy1))
    for i, a in enumerate(cajas):
        for b in cajas[i + 1 :]:
            if (
                a[0] < b[1] + 0.02
                and b[0] < a[1] + 0.02
                and a[2] < b[3] + 0.02
                and b[2] < a[3] + 0.02
            ):
                return None
    return ents, de_quien


# Las semillas que el revisor encontró con una pila ajena o a medias antes de R55.
SEMILLAS_DEL_REVISOR = (
    [(s, True, True) for s in (48, 147, 491, 600, 734, 4436, 4685, 4769, 5234, 6188, 6217)]
    + [(s, True, True) for s in (6900, 6933, 7105, 7137, 9763, 9817, 10566, 10647, 10805)]
    + [(s, True, True) for s in (11164, 11318, 11416, 11601, 11901, 12507, 12568, 13231)]
    + [(s, True, True) for s in (14919, 16680, 16964, 17293, 18359, 18455, 18504, 18562)]
    + [(s, True, True) for s in (18929, 19274)]
    + [(s, False, True) for s in (510, 1079, 1235, 1283, 2133, 2142, 2838, 2868, 3053, 4247)]
    + [(s, False, True) for s in (4858, 4975, 5027, 5121, 5892, 5995, 6978, 7215, 7766, 7934)]
    + [(s, False, True) for s in (8177, 8453, 8921, 9360, 10147, 10812, 11551, 12969, 13245)]
    + [(s, False, True) for s in (14598, 14769, 15218, 15553, 15665, 16486, 17202, 18405)]
    + [(s, False, True) for s in (19088, 19103)]
    + [(s, True, False) for s in (5160, 5357, 7864, 8975, 9944, 11221, 11375, 11726, 13180)]
    + [(s, True, False) for s in (15266, 16165, 16832)]
)


@pytest.mark.parametrize("semilla,mezcla,sin_pila", SEMILLAS_DEL_REVISOR)
def test_the_reviewers_random_cuadros_never_read_a_foreign_or_partial_stack(
    tmp_path, semilla, mezcla, sin_pila
):
    cuadro = _cuadro_del_revisor(tmp_path, semilla, mezcla, sin_pila)
    assert cuadro is not None  # todas eran legibles
    ents, de_quien = cuadro
    asoc, rech = asociar(ents, _one_frame(ents), TextPatternConfig())
    _ni_ajenas_ni_a_medias(ents, asoc, rech, de_quien)


_BARRIDA = 240  # semillas por familia: unos 30 cuadros legibles, poco más de un segundo


@pytest.mark.parametrize("mezcla", [False, True])
@pytest.mark.parametrize("sin_pila", [False, True])
def test_a_sweep_of_the_reviewers_random_cuadros(tmp_path, mezcla, sin_pila):
    """Una barrida acotada de semillas de cada familia del revisor: en ninguna se lee una pila
    ajena ni una a medias, y se lee algo (la prueba no se vacía sola)."""
    legibles = leidos = 0
    for semilla in range(_BARRIDA):
        cuadro = _cuadro_del_revisor(tmp_path, semilla, mezcla, sin_pila)
        if cuadro is None:
            continue
        ents, de_quien = cuadro
        asoc, rech = asociar(ents, _one_frame(ents), TextPatternConfig())
        _ni_ajenas_ni_a_medias(ents, asoc, rech, de_quien)
        legibles += 1
        leidos += len(asoc)
    assert legibles >= _BARRIDA // 8 and leidos >= legibles


# ------------------------------- R56: renglones largos que llegan a la columna de al lado (revisor)

LARGOS = [
    [
        ("4#6+4#4+2#5 CORR.", -0.3, 0.537),
        ("2E#3EXT@10 EN EXTREMOS", -0.4, 0.353),
        ("CENTRO@20", -0.179, 0.186),
    ],
    [("12#8+8#6 EN 2 LECHOS", -0.5, 0.36), ("E#4@10 Y E#3@20", -0.3, 0.18)],
    [("6#4", 0.065, 0.451), ("EYG#3@15 EN TODA LA ALTURA", -0.6, 0.268)],
]


def _cuadro_largo(tmp_path, semilla):
    """La familia «largo» del revisor, con su mismo orden de sorteos: filas de 2 a 4 marcas y, en
    siete de cada diez cuadros, pilas con renglones largos que llegan a la columna de al lado (y
    las filas desparejas ±0.3); una de cada cinco etiquetas sin pila. ``None`` si dos textos
    quedan a menos de 0.02."""
    rnd = random.Random(semilla)
    plantillas = LARGOS if rnd.random() < 0.7 else REVISOR
    de_quien: dict[tuple[str, float, float], str] = {}

    def build(doc):
        msp = doc.modelspace()
        mezcla = rnd.random() < 0.5
        abajo_siempre = rnd.random() < 0.4
        sx, sy = rnd.uniform(0.4, 1.0), rnd.uniform(0.5, 1.1)
        n = 0
        for j in range(rnd.randint(1, 3)):
            columnas = rnd.randint(2, 4)
            rnd.random()  # el lado de la fila, que sólo usa otra familia
            for i in range(columnas):
                n += 1
                x = i * sx + rnd.uniform(-0.2, 0.2)
                y = j * sy + rnd.uniform(-0.15, 0.15)
                if plantillas is LARGOS:
                    y += rnd.uniform(-0.3, 0.3)
                t = msp.add_text(f"K-{n}", height=0.13)
                t.set_placement((x, y), align=TextEntityAlignment.BOTTOM_CENTER)
                abajo = (rnd.random() < 0.4) if mezcla else abajo_siempre
                hueco, escala = rnd.uniform(0.02, 0.16), rnd.uniform(0.85, 1.2)
                pila = rnd.choice(plantillas)
                if rnd.random() < 0.2:
                    continue
                dy0 = min(dy for _, _, dy in pila)
                for texto, dx, dy in pila:
                    rel = (dy - dy0) * escala
                    yy = y + ((-hueco - 0.10 - rel) if abajo else (0.13 + hueco + rel))
                    xx = x + dx + rnd.uniform(-0.05, 0.05)
                    msp.add_text(texto, height=0.10).set_placement((xx, yy))
                    de_quien[(texto, round(xx, 3), round(yy, 3))] = f"K-{n}"

    ents = _dxf(tmp_path, build)
    return (None if _se_tocan(ents) else ents), de_quien


def _se_tocan(ents):
    """Si dos textos quedan a menos de 0.02 (el filtro de legibilidad del revisor)."""
    cajas = []
    for e in ents:
        if e.is_textual:
            (ax, ay), (dx0, dx1, dy0, dy1, _) = ancla_texto(e), caja_de_texto(e, 0.0)
            cajas.append((ax + dx0, ax + dx1, ay + dy0, ay + dy1))
    return any(
        a[0] < b[1] + 0.02 and b[0] < a[1] + 0.02 and a[2] < b[3] + 0.02 and b[2] < a[3] + 0.02
        for i, a in enumerate(cajas)
        for b in cajas[i + 1 :]
    )


@pytest.mark.parametrize("semilla", [794, 1231, 1981, 5889, 6863, 10316, 13460, 16611])
def test_a_long_line_into_the_next_column_never_splits_or_swaps_stacks(tmp_path, semilla):
    """R56: un renglón largo que llega a la columna de al lado. Si el siguiente renglón de una
    pila también sigue a uno de la otra columna, más pegado (794: «6#4» a 0.078 del renglón largo
    y «CENTRO@20» a 0.090), la pila no acaba ahí sin más: queda en duda y lo que sigue sigue siendo
    reclamo suyo. Dos etiquetas que se toman cada una la pila que la otra alcanza (5889, 13460: los
    «EYG…» cruzados) son una rueda: cambiarlas es igual de coherente. Una etiqueta que sólo tiene
    enfrente de lado el renglón largo de otra pila (10316) no la corta limpio. Nunca una pila ajena
    ni una a medias."""
    ents, de_quien = _cuadro_largo(tmp_path, semilla)
    assert ents is not None  # todas eran legibles
    asoc, rech = asociar(ents, _one_frame(ents), TextPatternConfig())
    _ni_ajenas_ni_a_medias(ents, asoc, rech, de_quien)


# ------------------------- R57: pilas con renglones alineados distinto (izquierda/derecha/centro)


def _con_alineacion(tmp_path, textos):
    """Textos (texto, x, y, alto, alineación), en ese orden."""

    def build(doc):
        msp = doc.modelspace()
        for texto, x, y, alto, alineacion in textos:
            msp.add_text(texto, height=alto).set_placement((x, y), align=alineacion)

    return _dxf(tmp_path, build)


_IZQ, _DER, _CEN = (
    TextEntityAlignment.BOTTOM_LEFT,
    TextEntityAlignment.BOTTOM_RIGHT,
    TextEntityAlignment.BOTTOM_CENTER,
)
# Las reproducciones mínimas del revisor (R57): la pila de K-1, un renglón alineado a la derecha y
# el siguiente a la izquierda (se enciman 0.50 de 1.53, menos de la mitad del más angosto), con K-2
# sin pila encima de la punta del segundo; y la de K-3, renglones al centro y a la izquierda, con
# K-1 sin pila debajo.
MEZCLADA_A = [
    ("K-1", 0.0, 0.0, 0.13, _CEN),
    ("4#6+4#4+2#5 CORR.", 0.25, -0.22, 0.10, _DER),
    ("E#4@10 Y E#3@20 EN NUDOS", -0.25, -0.40, 0.10, _IZQ),
    ("K-2", 1.3, -0.12, 0.13, _CEN),
]
MEZCLADA_B = [
    ("K-3", 0.0, 1.0, 0.13, _CEN),
    ("EYG#3@15", 0.0, 0.78, 0.10, _CEN),
    ("6#4", 0.15, 0.60, 0.10, _CEN),
    ("4#3", -0.17, 0.42, 0.10, _IZQ),
    ("CENTRO@15 RESTO", -0.17, 0.24, 0.10, _IZQ),
    ("K-1", -0.1, 0.0, 0.13, _CEN),
]


@pytest.mark.parametrize(
    "textos,marcas",
    [(MEZCLADA_A, ("K-1", "K-2")), (MEZCLADA_B, ("K-1", "K-3"))],
    ids=["der-izq", "centro-izq"],
)
def test_a_stack_with_mixed_alignment_is_never_split(tmp_path, textos, marcas):
    """R57: el siguiente renglón de una pila cae en la etiqueta ensanchada a la altura de seguirla
    pero se encima con el anterior en menos de la mitad del más angosto. Antes la columna acababa
    ahí sin duda y el resto era el primer renglón limpio de la etiqueta vecina (A: K-1 ← sólo
    «4#6+4#4+2#5 CORR.», K-2 ← «E#4@10…»; B: K-3 y K-1 se partían la pila de K-3). Ahora la pila
    queda en duda y lo que sigue es reclamo suyo: todo ambiguo, nada a medias ni ajeno."""
    ents = _con_alineacion(tmp_path, textos)
    asoc, rech = asociar(ents, _one_frame(ents), TextPatternConfig())
    assert asoc == []
    assert sorted((r.texto, r.motivo, tuple(r.marcas)) for r in rech) == sorted(
        (t, "ambigua", marcas) for t, *_ in textos if not t.startswith("K-")
    )


@pytest.mark.parametrize("con_k1", [True, False])
def test_a_label_beside_the_first_line_does_not_hide_it(tmp_path, con_k1):
    """R57 (zigzag a ±0.48, semilla 64970): la pila de K-2 baja con «6#4» a la derecha y «8#6» a
    la izquierda (no se enciman). K-1, sin pila, queda junto a «6#4» y más pegada a K-2 que él,
    pero no enfrente de él (no se le encima de lado): no lo tapa. Antes K-2 no alcanzaba nada y K-1
    tomaba «8#6» limpio; sin K-1, K-2 leía sólo «6#4». Ahora la pila de K-2 queda en duda y es
    reclamo suyo: nada se lee y lo que K-1 también alcanza es ambiguo."""
    textos = [
        ("K-2", 0.5475, 0.012, 0.13, _CEN),
        ("6#4", 1.087, -0.214, 0.10, _DER),
        ("8#6", 0.067, -0.39, 0.10, _IZQ),
    ]
    if con_k1:
        textos.append(("K-1", 0.0185, -0.23, 0.13, _CEN))
    ents = _con_alineacion(tmp_path, textos)
    asoc, rech = asociar(ents, _one_frame(ents), TextPatternConfig())
    assert asoc == []
    motivo, marcas = ("ambigua", ("K-1", "K-2")) if con_k1 else ("sin_dueno", ())
    assert sorted((r.texto, r.motivo, tuple(r.marcas)) for r in rech) == [
        ("6#4", motivo, marcas),
        ("8#6", motivo, marcas),
    ]


def test_the_same_stack_with_one_alignment_reads_whole(tmp_path):
    """El caso A del revisor con los dos renglones alineados a la derecha: se siguen limpio y K-1
    lee su pila entera; K-2 no alcanza nada que sea de una pila en duda."""
    textos = [MEZCLADA_A[0], MEZCLADA_A[1], (*MEZCLADA_A[2][:1], 0.25, -0.40, 0.10, _DER)]
    ents = _con_alineacion(tmp_path, [*textos, MEZCLADA_A[3]])
    asoc, rech = asociar(ents, _one_frame(ents), TextPatternConfig())
    assert {a.marca: a.textos for a in asoc} == {
        "K-1": ["4#6+4#4+2#5 CORR.", "E#4@10 Y E#3@20 EN NUDOS"]
    }
    assert rech == []


_CORTOS = ["4#3", "6#4", "8#6", "12#8", "E#2@15", "E#4@10", "EYG#3@15", "CENTRO@20"]
_MEDIOS = ["2E#3EXT@10", "4#6+4#4", "E#3@20 Y E#2@15", "CENTRO@15 RESTO"]
_LARGOS = [
    "4#6+4#4+2#5 CORR.",
    "2E#3EXT@10 EN EXTREMOS",
    "12#8+8#6 EN 2 LECHOS",
    "EYG#3@15 EN TODA LA ALTURA",
    "E#4@10 Y E#3@20 EN NUDOS",
]
_ALINEACIONES = {"izq": _IZQ, "der": _DER, "cen": _CEN}


def _cuadro_mezclado(tmp_path, semilla, familia, desplazamiento=0.25, fija=False):
    """Las familias del revisor para R57, con su mismo orden de sorteos. «zigzag»: una rejilla de
    marcas, cada pila con renglones cortos, medios y largos alineados a la izquierda, a la derecha
    o al centro de su etiqueta (± ``desplazamiento``), alternados o al azar; «ambos»: escaleras de
    etiqueta y pila (encima o debajo) con escaleras vecinas cerca, así que una etiqueta tiene
    renglones largos, suyos o ajenos, de los dos lados. Una de cada cinco etiquetas sin pila. Con
    ``fija``, una sola alineación por pila. ``(None, …)`` si dos textos quedan a menos de 0.02."""
    rnd = random.Random(semilla)

    def renglones(n):
        salida = []
        for _ in range(n):
            u = rnd.random()
            salida.append(rnd.choice(_LARGOS if u < 0.35 else _MEDIOS if u < 0.65 else _CORTOS))
        return salida

    def pila(marca, x, y_etiqueta, abajo, hueco, textos, alineaciones):
        salida = []
        for k, texto in enumerate(textos):
            rel = k * 0.18 * rnd.uniform(0.95, 1.05)
            yy = (y_etiqueta - hueco - 0.10 - rel) if abajo else (y_etiqueta + 0.13 + hueco + rel)
            alineacion = alineaciones[k % len(alineaciones)]
            dx = {"izq": -desplazamiento, "der": desplazamiento, "cen": 0.0}[alineacion]
            salida.append((texto, x + dx + rnd.uniform(-0.06, 0.06), yy, 0.10, alineacion, marca))
        return salida

    textos: list[tuple] = []
    n = 0
    if familia == "zigzag":
        sx, sy = rnd.uniform(0.5, 1.4), rnd.uniform(0.7, 1.4)
        mezcla = rnd.random() < 0.5
        abajo_siempre = rnd.random() < 0.5
        for j in range(rnd.randint(1, 3)):
            for i in range(rnd.randint(2, 4)):
                n += 1
                marca = f"K-{n}"
                x = i * sx + rnd.uniform(-0.15, 0.15)
                y = j * sy + rnd.uniform(-0.25, 0.25)
                textos.append((marca, x, y, 0.13, None, marca))
                abajo = (rnd.random() < 0.5) if mezcla else abajo_siempre
                if rnd.random() < 0.2:
                    continue
                suyos = renglones(rnd.randint(2, 4))
                if rnd.random() < 0.5:
                    alineaciones = ["izq", "der"] if rnd.random() < 0.5 else ["der", "izq"]
                else:
                    alineaciones = [rnd.choice(list(_ALINEACIONES)) for _ in suyos]
                if fija:
                    alineaciones = alineaciones[:1]
                hueco = rnd.uniform(0.02, 0.16)
                textos += pila(marca, x, y, abajo, hueco, suyos, alineaciones)
    else:
        sx = rnd.uniform(0.45, 1.0)
        for i in range(rnd.randint(2, 3)):
            x0 = i * sx + rnd.uniform(-0.1, 0.1)
            y = rnd.uniform(-0.2, 0.2)
            for _ in range(rnd.randint(2, 3)):
                n += 1
                marca = f"K-{n}"
                abajo = rnd.random() < 0.5
                sin_pila = rnd.random() < 0.2
                suyos = renglones(rnd.randint(2, 3))
                alineaciones = [rnd.choice(list(_ALINEACIONES)) for _ in suyos]
                if fija:
                    alineaciones = alineaciones[:1]
                hueco, separa = rnd.uniform(0.02, 0.16), rnd.uniform(0.02, 0.3)
                alto = (len(suyos) - 1) * 0.18 + 0.10
                x = x0 + rnd.uniform(-0.1, 0.1)
                if abajo:
                    y_etiqueta = y - separa - 0.13
                    textos.append((marca, x, y_etiqueta, 0.13, None, marca))
                    if not sin_pila:
                        textos += pila(marca, x, y_etiqueta, True, hueco, suyos, alineaciones)
                        y = y_etiqueta - hueco - alto
                    else:
                        y = y_etiqueta
                else:
                    if not sin_pila:
                        y_etiqueta = y - separa - alto - hueco - 0.13
                        textos += pila(marca, x, y_etiqueta, False, hueco, suyos, alineaciones)
                    else:
                        y_etiqueta = y - separa - 0.13
                    textos.append((marca, x, y_etiqueta, 0.13, None, marca))
                    y = y_etiqueta
    ents = _con_alineacion(
        tmp_path, [(t, x, y, alto, _ALINEACIONES.get(al, _CEN)) for t, x, y, alto, al, _ in textos]
    )
    de_quien = {
        (t, round(x, 3), round(y, 3)): marca for t, x, y, _, al, marca in textos if al is not None
    }
    return (None if _se_tocan(ents) else ents), de_quien


# Las semillas en que el revisor encontró una pila ajena o a medias en 398034d (0–3,000).
SEMILLAS_ZIGZAG = (
    [4, 22, 46, 68, 77, 86, 95, 138, 144, 150, 156, 168, 170, 174, 238, 301, 387, 431, 446, 475]
    + [584, 591, 633, 686, 761, 772, 795, 799, 804, 806, 824, 825, 837, 872, 879, 891, 903, 917]
    + [961, 985, 1012, 1084, 1127, 1137, 1148, 1163, 1169, 1176, 1186, 1216, 1249, 1278, 1371]
    + [1468, 1512, 1558, 1576, 1577, 1646, 1668, 1669, 1687, 1707, 1748, 1811, 1860, 1863, 1868]
    + [1875, 1924, 1940, 1986, 2025, 2060, 2088, 2090, 2091, 2120, 2148, 2149, 2156, 2203, 2217]
    + [2224, 2233, 2280, 2294, 2304, 2311, 2348, 2360, 2417, 2446, 2460, 2481, 2510, 2534, 2539]
    + [2540, 2551, 2559, 2582, 2598, 2614, 2642, 2683, 2704, 2762, 2763, 2822, 2848, 2859, 2860]
    + [2865, 2930, 2937, 2964, 2975, 2988, 2995]
)
SEMILLAS_AMBOS = [56, 78, 364, 394, 682, 702, 1814, 1896, 1924, 2083, 2197, 2450, 2601, 2796, 2977]


@pytest.mark.parametrize(
    "familia,semilla,desplazamiento",
    [("zigzag", s, 0.25) for s in SEMILLAS_ZIGZAG]
    + [("ambos", s, 0.25) for s in SEMILLAS_AMBOS]
    # Renglones a ±0.48 de su etiqueta: el más pegado a ella no queda encima de ella, así que el
    # primero que se toma es otro, y aquél queda entre los dos sin seguirlo limpio.
    + [("zigzag", 1110, 0.48)]
    # Una etiqueta sin pila junto al primer renglón de otra (no enfrente) ya no la deja sin pila
    # para luego tomarse lo de abajo (64970) ni deja que otra suba por la pila completa (61049).
    + [("zigzag", 64970, 0.48), ("ambos", 61049, 0.40)]
    # Lo que puede seguir una pila en duda sigue siendo reclamo suyo hasta donde llegue, no sólo
    # el renglón donde se perdió: si no, otra etiqueta se lleva el de más allá (60506).
    + [("zigzag", 60506, 0.25)],
)
def test_mixed_alignment_cuadros_never_read_a_foreign_or_partial_stack(
    tmp_path, familia, semilla, desplazamiento
):
    ents, de_quien = _cuadro_mezclado(tmp_path, semilla, familia, desplazamiento)
    assert ents is not None  # todas eran legibles
    asoc, rech = asociar(ents, _one_frame(ents), TextPatternConfig())
    _ni_ajenas_ni_a_medias(ents, asoc, rech, de_quien)


@pytest.mark.parametrize(
    "familia,desplazamiento,fija,desde,semillas",
    [
        ("zigzag", 0.25, False, 5000, 300),
        ("zigzag", 0.25, True, 5000, 200),
        ("zigzag", 0.48, False, 5000, 200),
        ("ambos", 0.25, False, 5000, 400),
        ("ambos", 0.48, False, 5000, 400),
    ],
)
def test_a_sweep_of_mixed_alignment_cuadros(
    tmp_path, familia, desplazamiento, fija, desde, semillas
):
    """Una barrida acotada de las familias de R57 (con una sola alineación por pila como
    control, y con los renglones más lejos de su etiqueta): ninguna pila ajena ni a medias, todo
    renglón leído o rechazado, y se lee algo."""
    legibles = leidos = 0
    for semilla in range(desde, desde + semillas):
        ents, de_quien = _cuadro_mezclado(tmp_path, semilla, familia, desplazamiento, fija)
        if ents is None:
            continue
        asoc, rech = asociar(ents, _one_frame(ents), TextPatternConfig())
        _ni_ajenas_ni_a_medias(ents, asoc, rech, de_quien)
        legibles += 1
        leidos += len(asoc)
    assert legibles >= 10 and leidos >= 1


# ------------------------------- R59: lo de al lado de la columna (revisión de la ronda 4)


def _leer_y_revisar(tmp_path, textos):
    """Textos (texto, x, y, alto, alineación, dueño); ``dueño`` es ``None`` en las etiquetas.
    Asocia y revisa que no haya pila ajena ni a medias y que todo renglón se lea o se rechace."""
    ents = _con_alineacion(tmp_path, [t[:5] for t in textos])
    de_quien = {(t, round(x, 3), round(y, 3)): m for t, x, y, _, _, m in textos if m is not None}
    asoc, rech = asociar(ents, _one_frame(ents), TextPatternConfig())
    _ni_ajenas_ni_a_medias(ents, asoc, rech, de_quien)
    return asoc, rech


def _junto_al_limpio(d2, modo, kx, g, suyo, ajeno):
    """La disposición del revisor contra ``_compite`` (R59): K-1 con «4#3» al centro y, debajo,
    su segundo renglón a la izquierda desde ``d2``, al lado de un renglón ajeno («ajeno», de K-2)
    alineado a la derecha que sí sigue limpio a «4#3» y le queda más cerca al centro de K-1. K-2
    puede no estar, estar debajo del renglón ajeno o junto a «4#3»."""
    textos = [
        ("K-1", 0.0, 0.0, 0.13, _CEN, None),
        ("4#3", 0.0, -0.22, 0.10, _CEN, "K-1"),
        (suyo, d2, -0.40, 0.10, _IZQ, "K-1"),
        (ajeno, d2 - 0.03, -0.40, 0.10, _DER, "K-2"),
    ]
    if modo == "debajo":
        textos.append(("K-2", kx, -0.40 - g - 0.13, 0.13, _CEN, None))
    elif modo == "junto":
        textos.append(("K-2", kx, -0.30 + g, 0.13, _CEN, None))
    return textos


_SUYOS = ["E#4@10 Y E#3@20 EN NUDOS", "E#2@15", "2E#3EXT@10"]
_AJENOS = ["6#4", "CENTRO@20", "12#8+8#6 EN 2 LECHOS"]


@pytest.mark.parametrize("modo", ["sin_k2", "debajo", "junto"])
def test_a_line_beside_the_clean_next_line_is_the_next_columns_only_if_another_label_has_it(
    tmp_path, modo
):
    """R59 (revoca la salvedad b de R58): un renglón al lado del que sigue limpio a la pila y más
    alejado del centro de la etiqueta sólo es de la columna de al lado si otra etiqueta, más
    cerca de él, lo tiene en su ensanche. Si no, la pila queda en duda (R57). Antes K-1 leía
    «4#3» y el renglón de K-2, y el suyo quedaba sin dueño (354 de las 648 del revisor)."""
    casos = [(d2, 0.0, 0.0) for d2 in (0.03, 0.06, 0.10, 0.15)]
    if modo != "sin_k2":
        casos = [(d2, kx, g) for d2 in (0.03, 0.15) for kx in (-0.55, -0.85) for g in (0.03, 0.08)]
    for n, (d2, kx, g) in enumerate(casos):
        for suyo in _SUYOS:
            for ajeno in _AJENOS:
                carpeta = tmp_path / f"{n}-{suyo}-{ajeno}"
                carpeta.mkdir()
                asoc, _ = _leer_y_revisar(carpeta, _junto_al_limpio(d2, modo, kx, g, suyo, ajeno))
                assert asoc == []


# La semilla 61526 del revisor (zigzag ±0.62), sin K-3 ni K-4: K-1 sigue limpio su columna
# hasta el «4#3» de K-2, que empieza junto a ella (K-2 está al lado del «4#3» de K-1).
SEMILLA_61526 = [
    ("K-1", 0.1395, -0.227, 0.13, _CEN, None),
    ("CENTRO@15 RESTO", -0.491, 0.005, 0.10, _IZQ, "K-1"),
    ("4#3", 0.704, 0.181, 0.10, _DER, "K-1"),
    ("K-2", 1.0205, 0.155, 0.13, _CEN, None),
    ("4#3", 0.346, 0.367, 0.10, _IZQ, "K-2"),
    ("E#4@10", 0.419, 0.555, 0.10, _IZQ, "K-2"),
]


@pytest.mark.parametrize("textos", [SEMILLA_61526, SEMILLA_61526[:5]], ids=["V0", "V1"])
def test_a_label_beside_a_clean_column_can_start_its_stack_there(tmp_path, textos):
    """R59: una etiqueta de otra marca junto al renglón ``previo`` de la columna, a su altura, que
    tiene ``siguiente`` en su ensanche y a su alcance: la columna puede acabar ahí y seguir como la
    pila de ella. La pila queda en duda (R57). Antes K-1 se llevaba los renglones de K-2. K-2 no
    alcanza su pila (su «4#3» sigue limpio al de K-1), así que sólo K-1 la reclama: sin dueño."""
    asoc, rech = _leer_y_revisar(tmp_path, textos)
    assert asoc == []
    assert sorted((r.texto, r.motivo) for r in rech) == sorted(
        (t, "sin_dueno") for t, *_, dueno in textos if dueno is not None
    )


def test_a_centred_label_beside_a_clean_column_leaves_it_in_doubt(tmp_path):
    """V3 del revisor, todo centrado: K-1 con «4#3» encima, K-2 junto a «4#3» y «6#4» (de K-2)
    encima de los dos. Con «6#4» en el ensanche de K-2, nada se lee mal. Sin él (``xc`` muy a la
    izquierda de K-2) es el límite del modelo: K-2 no puede tenerlo, y «6#4» sigue a K-1."""
    revisadas = 0
    for xb in (0.55, 0.65, 0.75, 0.85, 1.0):
        for xc in (0.0, 0.1, 0.2, 0.3, 0.4, 0.5):
            if xc + 0.135 < xb - 0.1755 - 0.3:
                continue  # «6#4» (0.27 de ancho) fuera del ensanche de K-2 (0.351 + 2 × 0.3)
            carpeta = tmp_path / f"{xb}-{xc}"
            carpeta.mkdir()
            textos = [
                ("K-1", 0.0, 0.0, 0.13, _CEN, None),
                ("4#3", 0.0, 0.17, 0.10, _CEN, "K-1"),
                ("K-2", xb, 0.155, 0.13, _CEN, None),
                ("6#4", xc, 0.35, 0.10, _CEN, "K-2"),
            ]
            _leer_y_revisar(carpeta, textos)
            revisadas += 1
    assert revisadas == 20


def _cuadro_de_lado(tmp_path, semilla, familia, desplazamiento=0.25):
    """Las familias del revisor para R59, con su mismo orden de sorteos. «lado»: una fila de 2 a 4
    etiquetas con sus pilas del mismo lado, renglones a la misma altura y alineados a la
    izquierda, a la derecha o al centro (± ``desplazamiento``); «lado_s»: las etiquetas
    escalonadas ±0.12; «borde»: una rejilla con cada renglón a 0.15–0.95 de su etiqueta, en el
    borde de su ensanche o más allá. ``(None, …)`` si dos textos quedan a menos de 0.02."""
    rnd = random.Random(semilla)

    def texto():
        u = rnd.random() if familia == "borde" else 0.2 + 0.8 * rnd.random()
        return rnd.choice(_LARGOS if u < 0.35 else _MEDIOS if u < 0.65 else _CORTOS)

    textos: list[tuple] = []
    if familia == "borde":
        n = 0
        sx, sy = rnd.uniform(0.6, 1.6), rnd.uniform(0.7, 1.4)
        for j in range(rnd.randint(1, 3)):
            for i in range(rnd.randint(2, 4)):
                n += 1
                marca = f"K-{n}"
                x = i * sx + rnd.uniform(-0.15, 0.15)
                y = j * sy + rnd.uniform(-0.25, 0.25)
                textos.append((marca, x, y, 0.13, None, marca))
                if rnd.random() < 0.2:
                    continue
                abajo = rnd.random() < 0.5
                hueco = rnd.uniform(0.02, 0.16)
                for k in range(rnd.randint(2, 4)):
                    alineacion = rnd.choice(list(_ALINEACIONES))
                    lejos = rnd.uniform(0.15, 0.95) if alineacion != "cen" else 0.0
                    dx = {"izq": -lejos, "der": lejos, "cen": 0.0}[alineacion]
                    dx += rnd.uniform(-0.06, 0.06)
                    rel = k * 0.18 * rnd.uniform(0.95, 1.05)
                    yy = (y - hueco - 0.10 - rel) if abajo else (y + 0.13 + hueco + rel)
                    textos.append((texto(), x + dx, yy, 0.10, alineacion, marca))
    else:
        paso = rnd.uniform(0.45, 1.2)
        abajo = rnd.random() < 0.5
        hueco = rnd.uniform(0.02, 0.12)
        renglon = rnd.uniform(0.17, 0.20)
        for i in range(rnd.randint(2, 4)):
            marca = f"K-{i + 1}"
            x = i * paso + rnd.uniform(-0.05, 0.05)
            y = rnd.uniform(-0.12, 0.12) if familia == "lado_s" else 0.0
            textos.append((marca, x, y, 0.13, None, marca))
            if rnd.random() < 0.15:
                continue
            for k in range(rnd.randint(2, 4)):
                alineacion = rnd.choice(list(_ALINEACIONES))
                dx = {"izq": -desplazamiento, "der": desplazamiento, "cen": 0.0}[alineacion]
                dx += rnd.uniform(-0.06, 0.06)
                yy = (y - hueco - 0.10 - k * renglon) if abajo else (y + 0.13 + hueco + k * renglon)
                textos.append((texto(), x + dx, yy, 0.10, alineacion, marca))
    ents = _con_alineacion(
        tmp_path, [(t, x, y, alto, _ALINEACIONES.get(al, _CEN)) for t, x, y, alto, al, _ in textos]
    )
    de_quien = {
        (t, round(x, 3), round(y, 3)): marca for t, x, y, _, al, marca in textos if al is not None
    }
    return (None if _se_tocan(ents) else ents), de_quien


def _fuera_del_ensanche(ents, de_quien):
    """Si algún renglón no toca la etiqueta de su dueño ensanchada 3 altos de renglón: fuera del
    modelo de la pila (la salvedad a de R58, aceptada como su límite)."""
    cajas = {}
    for e in ents:
        if e.is_textual:
            (ax, ay), (dx0, dx1, _, _, alto) = ancla_texto(e), caja_de_texto(e, 0.0)
            cajas[e.entity_id] = (e.text, ax, ay, ax + dx0, ax + dx1, alto)
    etiquetas = {t: (x0, x1) for t, _, _, x0, x1, _ in cajas.values() if t.startswith("K-")}
    for t, ax, ay, x0, x1, alto in cajas.values():
        marca = de_quien.get((t, round(ax, 3), round(ay, 3)))
        if marca is not None:
            e0, e1 = etiquetas[marca]
            if x1 < e0 - 3 * alto or x0 > e1 + 3 * alto:
                return True
    return False


@pytest.mark.parametrize(
    "familia,semilla,desplazamiento",
    # El primer renglón de K-2 («8#6», bajo las dos etiquetas y sobre ninguna) va al lado del
    # renglón largo de K-3, igual de pegado; K-2 tomaba el de K-3 (más cerca de su centro) y K-1
    # se llevaba «8#6» limpio.
    [("lado", 71455, 0.55)]
    # En «borde», con todos los renglones en su ensanche: la columna de K-2 seguía limpio junto a
    # K-1 hasta el «E#4@10» de K-1, que K-1 tiene a su alcance (82761; la regla de ``previo``).
    + [("borde", 82761, 0.25)],
)
def test_the_side_by_side_seeds_never_read_a_foreign_or_partial_stack(
    tmp_path, familia, semilla, desplazamiento
):
    ents, de_quien = _cuadro_de_lado(tmp_path, semilla, familia, desplazamiento)
    assert ents is not None
    asoc, rech = asociar(ents, _one_frame(ents), TextPatternConfig())
    _ni_ajenas_ni_a_medias(ents, asoc, rech, de_quien)


@pytest.mark.parametrize(
    "familia,desplazamiento,semillas",
    [
        ("lado", 0.25, 200),
        ("lado", 0.55, 200),
        ("lado_s", 0.25, 200),
        ("lado_s", 0.55, 200),
        ("borde", 0.25, 400),
    ],
)
def test_a_sweep_of_side_by_side_cuadros(tmp_path, familia, desplazamiento, semillas):
    """Barridas acotadas de las familias de R59: ninguna pila ajena ni a medias, todo renglón
    leído o rechazado. En «borde» sólo cuentan los cuadros cuyos renglones tocan la etiqueta
    ensanchada de su dueño: uno que no la toca no es de su pila en el modelo (salvedad a de R58,
    aceptada), y ahí sí puede leerse una pila a medias."""
    revisados = leidos = 0
    for semilla in range(8000, 8000 + semillas):
        ents, de_quien = _cuadro_de_lado(tmp_path, semilla, familia, desplazamiento)
        if ents is None or _fuera_del_ensanche(ents, de_quien):
            continue
        asoc, rech = asociar(ents, _one_frame(ents), TextPatternConfig())
        _ni_ajenas_ni_a_medias(ents, asoc, rech, de_quien)
        revisados += 1
        leidos += len(asoc)
    assert revisados >= 10 and leidos >= 1


# ------------------------------------------------- Task 7, paso previo B (R60, el breaker de R59)
# La salvedad de ``_compite`` (un renglón al lado del que sigue limpio es de la columna de al lado
# si otra etiqueta más cerca lo tiene en su ensanche) exige además que esa etiqueta lo alcance: que
# el renglón esté en su columna. Una etiqueta lejana que sólo lo tiene en su ensanche de lado no
# sabe nada de él (las disposiciones p2far del revisor: K-3 debajo, encima o en el renglón de K-1).


def _con_k3_lejana(d2, kx, modo, k3x, k3, suyo, ajeno):
    """La disposición del revisor (``r59rev/p2far.py``): K-1 con «4#3» al centro y, debajo, su
    renglón ``suyo`` a la izquierda desde ``d2``, junto al ``ajeno`` (de K-2) alineado a la derecha
    que sigue limpio a «4#3»; K-2 debajo del ajeno, junto a «4#3» o ausente; y K-3 a la derecha,
    con ``suyo`` en su ensanche y más cerca de su centro que del de K-1, pero sin alcanzarlo: en
    otro renglón (debajo o encima, con su pila) o en el de K-1 (sin pila o con la pila hacia
    arriba)."""
    textos = [
        ("K-1", 0.0, 0.0, 0.13, _CEN, None),
        ("4#3", 0.0, -0.22, 0.10, _CEN, "K-1"),
        (suyo, d2, -0.40, 0.10, _IZQ, "K-1"),
        (ajeno, d2 - 0.03, -0.40, 0.10, _DER, "K-2"),
    ]
    if modo == "debajo":
        textos.append(("K-2", kx, -0.40 - 0.05 - 0.13, 0.13, _CEN, None))
    elif modo == "junto":
        textos.append(("K-2", kx, -0.25, 0.13, _CEN, None))
    if k3 == "debajo":
        textos += [("K-3", k3x, -1.1, 0.13, _CEN, None), ("8#6", k3x, -1.32, 0.10, _CEN, "K-3")]
    elif k3 == "renglon_sin_pila":
        textos.append(("K-3", k3x, 0.0, 0.13, _CEN, None))
    elif k3 == "renglon_arriba":
        textos += [("K-3", k3x, 0.0, 0.13, _CEN, None), ("8#6", k3x, 0.18, 0.10, _CEN, "K-3")]
    else:
        textos += [("K-3", k3x, 1.0, 0.13, _CEN, None), ("8#6", k3x, 1.18, 0.10, _CEN, "K-3")]
    return textos


def test_a_far_label_that_has_the_line_only_in_its_band_does_not_end_the_column(tmp_path):
    """R60, la reproducción en banda del revisor: K-3 lejos, debajo, tiene «2E#3EXT@10» de K-1
    en su ensanche y más cerca de su centro, pero no lo alcanza. Antes K-1 leía «4#3» y el «6#4»
    de K-2 limpio, y su propio renglón quedaba sin dueño."""
    textos = [
        ("K-1", 0.0, 0.0, 0.13, _CEN, None),
        ("4#3", 0.0, -0.22, 0.10, _CEN, "K-1"),
        ("2E#3EXT@10", 0.08, -0.40, 0.10, _IZQ, "K-1"),
        ("6#4", 0.05, -0.40, 0.10, _DER, "K-2"),
        ("K-2", -0.5, -0.83, 0.13, _CEN, None),
        ("K-3", 0.7, -1.3, 0.13, _CEN, None),
        ("8#6", 0.7, -1.52, 0.10, _CEN, "K-3"),
    ]
    asoc, _ = _leer_y_revisar(tmp_path, textos)
    assert [(a.marca, a.textos) for a in asoc] == [("K-3", ["8#6"])]


@pytest.mark.parametrize("k3", ["debajo", "renglon_sin_pila", "renglon_arriba", "encima"])
def test_the_reviewer_far_label_layouts_never_read_a_foreign_or_partial_stack(tmp_path, k3):
    """R60: las 1,296 disposiciones de ``r59rev/p2far.py`` (324 por posición de K-3): 0 ajenas, 0
    a medias (antes, 600 con las dos)."""
    revisadas = 0
    for d2 in (0.03, 0.08, 0.15):
        for kx in (-0.55, -0.85):
            for modo in ("debajo", "junto", "sin_k2"):
                for k3x in (0.7, 0.9, 1.2):
                    for suyo in (
                        "2E#3EXT@10 EN EXTREMOS",
                        "2E#3EXT@10",
                        "E#4@10 Y E#3@20 EN NUDOS",
                    ):
                        for ajeno in ("6#4", "CENTRO@20"):
                            _leer_y_revisar(
                                tmp_path, _con_k3_lejana(d2, kx, modo, k3x, k3, suyo, ajeno)
                            )
                            revisadas += 1
    assert revisadas == 324


@pytest.mark.parametrize("con_k3", [False, True])
def test_the_reviewer_far_label_below_or_above_k2_never_reads_a_foreign_or_partial_stack(
    tmp_path, con_k3
):
    """R60: las 192 disposiciones de ``r59rev/p2far4.py``: K-2 debajo, con el renglón ajeno en su
    ensanche pero fuera de su alcance, y K-3 debajo o encima con su pila (antes, 48 de las 96 con
    K-3 leían una pila ajena y otra a medias)."""
    revisadas = 0
    for d2 in (0.03, 0.08, 0.15):
        for hueco in (0.22, 0.3):
            for suyo in ("2E#3EXT@10", "E#4@10 Y E#3@20 EN NUDOS"):
                for ajeno in ("6#4", "CENTRO@20"):
                    for k3x in (0.7, 0.9):
                        for k3y in (-1.3, 1.0):
                            textos = [
                                ("K-1", 0.0, 0.0, 0.13, _CEN, None),
                                ("4#3", 0.0, -0.22, 0.10, _CEN, "K-1"),
                                (suyo, d2, -0.40, 0.10, _IZQ, "K-1"),
                                (ajeno, d2 - 0.03, -0.40, 0.10, _DER, "K-2"),
                                ("K-2", -0.5, -0.40 - hueco - 0.13, 0.13, _CEN, None),
                            ]
                            if con_k3:
                                y8 = k3y - 0.22 if k3y < 0 else k3y + 0.18
                                textos += [
                                    ("K-3", k3x, k3y, 0.13, _CEN, None),
                                    ("8#6", k3x, y8, 0.10, _CEN, "K-3"),
                                ]
                            _leer_y_revisar(tmp_path, textos)
                            revisadas += 1
    assert revisadas == 96


@pytest.mark.parametrize("k3dy", [-0.12, -0.05, 0.12])
def test_a_label_whose_first_line_would_be_the_line_does_not_end_the_column(tmp_path, k3dy):
    """R60 (más allá de p2far): K-3 junto a la columna de K-1, a la altura de su segundo renglón,
    con ese renglón a su alcance (justo debajo o justo encima de ella), con o sin pila del otro
    lado. Que lo tenga como su primer renglón no dice de quién es: la etiqueta que lee la pila
    está igual de cerca. Sólo cuenta si lo alcanza más allá de su primer renglón, como K-11 en
    Marina. Antes (f950d13) 128 de estas 288 disposiciones leían una pila ajena y otra a medias."""
    for d2 in (0.03, 0.15):
        for modo in ("debajo", "junto", "sin_k2"):
            for k3x in (0.6, 1.0):
                for pila in (False, True):
                    for suyo in ("2E#3EXT@10", "E#4@10 Y E#3@20 EN NUDOS"):
                        for ajeno in ("6#4", "CENTRO@20"):
                            textos = [
                                ("K-1", 0.0, 0.0, 0.13, _CEN, None),
                                ("4#3", 0.0, -0.22, 0.10, _CEN, "K-1"),
                                (suyo, d2, -0.40, 0.10, _IZQ, "K-1"),
                                (ajeno, d2 - 0.03, -0.40, 0.10, _DER, "K-2"),
                            ]
                            if modo == "debajo":
                                textos.append(("K-2", -0.55, -0.58, 0.13, _CEN, None))
                            elif modo == "junto":
                                textos.append(("K-2", -0.55, -0.25, 0.13, _CEN, None))
                            y3 = -0.40 + k3dy - 0.13 if k3dy < 0 else -0.30 + k3dy
                            textos.append(("K-3", k3x, y3, 0.13, _CEN, None))
                            if pila:
                                y8 = y3 - 0.22 if k3dy < 0 else y3 + 0.18
                                textos.append(("8#6", k3x, y8, 0.10, _CEN, "K-3"))
                            _leer_y_revisar(tmp_path, textos)


def test_a_label_above_the_line_with_its_own_line_below_it_does_not_end_the_column(tmp_path):
    """R60: K-3 justo encima de ``suyo`` (el segundo renglón de K-1) y su propio renglón debajo
    de él, centrado bajo K-3 y fuera del ensanche de K-1: la columna de K-3 pasa por ``suyo``
    como su primer renglón y sigue. Tampoco eso dice de quién es: contar ese primer renglón leía
    K-3 ← [suyo, el suyo] en las 96 disposiciones; así quedan todas en duda."""
    for k3dy in (0.05, 0.12):
        for modo in ("debajo", "junto", "sin_k2"):
            for k3x in (0.8, 1.0):
                for ajeno in ("6#4", "CENTRO@20"):
                    for propio in ("8#6", "E#2@15"):
                        for hueco in (0.05, 0.10):
                            textos = [
                                ("K-1", 0.0, 0.0, 0.13, _CEN, None),
                                ("4#3", 0.0, -0.22, 0.10, _CEN, "K-1"),
                                ("2E#3EXT@10 EN EXTREMOS", 0.03, -0.40, 0.10, _IZQ, "K-1"),
                                (ajeno, 0.0, -0.40, 0.10, _DER, "K-2"),
                                (propio, k3x, -0.50 - hueco, 0.10, _CEN, "K-3"),
                                ("K-3", k3x, -0.30 + k3dy, 0.13, _CEN, None),
                            ]
                            if modo == "debajo":
                                textos.append(("K-2", -0.55, -0.58, 0.13, _CEN, None))
                            elif modo == "junto":
                                textos.append(("K-2", -0.55, -0.25, 0.13, _CEN, None))
                            asoc, _ = _leer_y_revisar(tmp_path, textos)
                            assert all(a.marca != "K-3" for a in asoc)


@pytest.mark.parametrize(
    "texto,marcas",
    [
        ("K-1 15X20 4#3 E#2@20", ["K-1"]),
        ("K-1 Y K-2 15X20 4#3 E#2@20", ["K-1", "K-2"]),
        ("K-1, K-2 15X20 4#3", ["K-1", "K-2"]),
        ("K-1 A K-4 15X20 4#3", ["K-1 A K-4"]),
        ("DE K-1 A K-4 15X20 4#3", ["DE K-1 A K-4"]),
        ("K-1 A 4 15X20 4#3", ["K-1 A 4"]),
        ("K-1 HASTA K-4 4#3", ["K-1 HASTA K-4"]),
        ("K-1 15X20 4#3 IGUAL A K-2", ["K-1"]),  # una referencia no es otra marca
        ("E#2@15 VER CORTE C-2", []),
    ],
)
def test_the_marks_a_note_names(texto, marcas):
    # Task 7 (ronda 1, R63): una nota con varias marcas no se lee; se reporta como se escribió.
    assert marcas_en_nota(texto, TextPatternConfig()) == marcas


@pytest.mark.parametrize(
    "rango,marca,dentro",
    [
        ("K-1 A K-4", "K-2A", True),
        ("K-1 A K-4", "K-4", True),
        ("K-1 A K-4", "K-5", False),
        ("K-1 A 4", "K-3", True),
        ("DE K-10 A K-12", "K-11", True),
        ("K-1 A K-4", "C-2", False),
        ("K-1", "K-1", False),  # una marca sola no es un rango
    ],
)
def test_a_mark_inside_a_written_range(rango, marca, dentro):
    assert marca_en_rango(rango, marca) is dentro


def test_cuadro_rows_name_their_cuadro(tmp_path):
    def build(doc):
        msp = doc.modelspace()
        for y0 in (0.0, 5.0):
            for x, titulo in ((0.0, "MARCA"), (0.5, "SECCION"), (1.2, "ARMADO")):
                msp.add_text(titulo, height=0.1).set_placement((x, y0 + 0.18))
            for x, texto in zip((0.0, 0.5, 1.2), (f"K-{int(y0) + 1}", "15X20", "4#3"), strict=True):
                msp.add_text(texto, height=0.1).set_placement((x, y0))

    ents = _dxf(tmp_path, build)
    asoc, _ = asociar(ents, _one_frame(ents), TextPatternConfig())
    assert (
        len(asoc) == 2
        and len({a.cuadro for a in asoc}) == 2
        and None not in {a.cuadro for a in asoc}
    )


@pytest.mark.parametrize(
    "texto,lee",
    [
        ("K-7 SIN ARMADO", False),
        ("K-7 @20", False),
        ("K-7 EØ3@20", True),  # el parser lee «Ø» como «#»: el atajo no lo pierde
        ("K-7 E%%C3@20", True),
        ("K-7 15X20", True),
        ("K-7 E#3@20", True),
    ],
)
def test_the_note_shape_shortcut_never_changes_the_answer(texto, lee):
    # Task 7, ronda 2: sin «NNxNN» ni «#n» (o «Ø n», «%%C n») no se llama al parser.
    assert lo_lee_una_nota(texto) is lee


@pytest.mark.parametrize(
    "texto,marca",
    [
        ("T1-1 4#3", "T1-1"),
        ("T2-7 20X40", "T2-7"),
        ("K-15A.1 4#3", "K-15A.1"),
        ("K15A 4#3", "K15A"),
    ],
)
def test_the_longest_mark_in_a_text(texto, marca):
    # R66.c: la etiqueta más larga de la configuración («T1-1»), no lo que ve ``_MARCA_RE`` («T1»).
    # R67: con la misma llave que la etiqueta («K15A» como se escribió; antes «K-15A»).
    assert marca_en_texto(texto, TextPatternConfig()) == marca


@pytest.mark.parametrize(
    "rango,dentro,fuera",
    [("K-1-K-3", "K-2", "K-4"), ("K-1–K-3", "K-3", "C-2"), ("T-1—T-4", "T-3", "T-5")],
)
def test_an_unspaced_range(rango, dentro, fuera):
    assert marcas_en_nota(f"{rango} 4#3", TextPatternConfig()) == [rango]
    assert marca_en_rango(rango, dentro) and not marca_en_rango(rango, fuera)
