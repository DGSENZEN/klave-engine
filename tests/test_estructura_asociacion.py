"""La asociación de la lectura estructural: dónde está de verdad cada texto."""

import json
import math
from pathlib import Path

import ezdxf
import pytest
from ezdxf.enums import TextEntityAlignment
from klave_engine.detection.frames import SheetFrame
from klave_engine.detection.text_patterns import TextPatternConfig
from klave_engine.dxf.parser import DxfParser
from klave_engine.estructura.asociacion import ARMADO_RE, ancla_texto, asociar, marca_en_texto


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
        "P-5": ["4#8 + 12#6\n3E#3 VER CORTE"],
        "D-X": ["8#6", "2E#3@10"],
    }
    assert rech == []


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


def test_a_label_above_a_finished_stack_does_not_take_it(tmp_path):
    # K-2 alcanza por abajo la pila de K-1 (a 0.10), pero K-1 la tiene más cerca (0.05).
    ents = _stacks(
        tmp_path,
        [
            ("K-1", (0.0, 0.0), [("4#3", -0.2, 0.36), ("E#2@15", -0.2, 0.18)]),
            ("K-2", (0.0, 0.56), []),
        ],
    )
    asoc, rech = asociar(ents, _one_frame(ents), TextPatternConfig())
    assert {a.marca: a.textos for a in asoc} == {"K-1": ["4#3", "E#2@15"]} and rech == []


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


def test_a_stack_never_passes_over_another_label(tmp_path):
    # Una etiqueta chica (K-2) entre dos renglones, dentro del ancho de la pila de K-1: lo que
    # queda arriba de ella ya no es de K-1 (K-2 no alcanza ninguno de los dos).
    def build(doc):
        msp = doc.modelspace()
        k1 = msp.add_text("K-1", height=0.13)
        k1.set_placement((0.0, 0.0), align=TextEntityAlignment.BOTTOM_CENTER)
        msp.add_text("2E#3EXT@10 CENTRO@20", height=0.10).set_placement((-0.2, 0.18))
        k2 = msp.add_text("K-2", height=0.05)
        k2.set_placement((1.5, 0.36), align=TextEntityAlignment.BOTTOM_CENTER)
        msp.add_text("4#4", height=0.10).set_placement((-0.2, 0.42))

    ents = _dxf(tmp_path, build)
    asoc, rech = asociar(ents, _one_frame(ents), TextPatternConfig())
    assert {a.marca: a.textos for a in asoc} == {"K-1": ["2E#3EXT@10 CENTRO@20"]}
    assert _huerfanos(rech) == ["4#4"]


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
    ],
)
def test_armado_shaped_text(texto, es_armado):
    assert (ARMADO_RE.search(texto) is not None) is es_armado
