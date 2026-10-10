"""Definiciones por marca (Tarea 8): cada campo con su fuente, los conflictos entre hojas a la
vista, la IA detrás del plano y las formas de estribo supuestas o dichas."""

import json
from pathlib import Path

import ezdxf
import pytest
from klave_engine.detection.frames import SheetFrame
from klave_engine.detection.schedules import (
    ElementSpec,
    ScheduleInventory,
    _reading,
    build_schedule_inventory,
    family_of_mark,
    merge_external_specs,
)
from klave_engine.detection.text_patterns import TextPatternConfig
from klave_engine.dxf.entities import EntityType, EvidencePacket, NormalizedEntity
from klave_engine.dxf.parser import DxfParser
from klave_engine.estructura.armado import JuegoEstribos, parsear_armado
from klave_engine.estructura.definiciones import (
    FUENTE_DE_LECTURA,
    asignar_formas,
    construir_definiciones,
    fuente_de_lectura,
    normalizar_marca,
)

C = TextPatternConfig()


def _spec(mark, source, metodo, hoja, section=None, texts=None, llave=None, **campos):
    """Una lectura como la dan los lectores: con ``texts`` se lee con el parser (como una pila o
    una nota), con sus campos con texto y sus avisos."""
    family = campos.pop("family", family_of_mark(mark))
    lectura = _reading(texts, family) if texts else {}
    if section is not None:
        lectura["section_cm"] = section
        lectura["campos_con_texto"] = ["seccion", *lectura.get("campos_con_texto", [])]
    return ElementSpec(
        mark=mark,
        family=family,
        source=source,
        metodo=metodo,
        hoja=hoja,
        hoja_llave=llave or (f"specs.dxf#{hoja}" if hoja else ""),
        source_text=f"{mark} · {' / '.join(texts or [])}",
        confidence=0.5,
        entidades=[f"{mark}-{hoja}-{metodo}"] if source != "ia" else [],
        **{**lectura, **campos},
    )


def _inv(specs):
    return ScheduleInventory(specs=specs)


@pytest.mark.parametrize(
    "raw,norm",
    [
        ("K15A.1", "K-15A.1"),
        ("k-4a", "K-4A"),
        ("C 1", "C-1"),
        ("CTA-6", "CTA-6"),
        ("K-15A", "K-15A"),
        ("P-4", "P-4"),
        ("MC-1", "MC-1"),
        ("K1", "K-1"),
        ("K 1", "K-1"),
        ("k-1", "K-1"),
        ("K–1", "K-1"),
        ("K1-A", "K-1-A"),
        ("K-07", "K-07"),  # los ceros quedan como se escribieron
        ("T1-1", "T1-1"),  # una etiqueta de la configuración que ya lleva su guion
        ("T11", "T-11"),
        ("TL1", "TL-1"),
        ("CTA-3 (SECCIÓN 1)", "CTA-3 (SECCIÓN 1)"),  # no es una marca: como se escribió
    ],
)
def test_normalizar_marca(raw, norm):
    assert normalizar_marca(raw) == norm


def test_no_prefix_joins():
    marks = {normalizar_marca(m) for m in ["K-1", "K-1A", "K1", "K-15A", "K-15A.1"]}
    assert marks == {"K-1", "K-1A", "K-15A", "K-15A.1"}
    distintas = ["K-1", "K-1A", "K-1-A", "K-15A", "K-15A.1", "T1-1", "T-11", "K-07", "K-7"]
    assert len({normalizar_marca(m) for m in distintas}) == len(distintas)


def test_conflict_between_frames():
    defs, _ = construir_definiciones(
        _inv(
            [
                _spec("K-5", "detalle", "cotas", "ES-400", section=(20, 30)),
                _spec("K-5", "detalle", "cotas", "ES-200", section=(20, 40)),
            ]
        )
    )
    s = defs["K-5"].seccion_cm
    assert s.en_conflicto and {s.valor, s.alternativas[0].valor} == {(20, 30), (20, 40)}
    assert {s.hoja, s.alternativas[0].hoja} == {"ES-200", "ES-400"}


def test_a_section_is_its_two_sides_whatever_the_order():
    # Las cotas dan ancho × peralte; las notas, los lados ordenados: la misma sección.
    defs, _ = construir_definiciones(
        _inv(
            [
                _spec("K-7", "detalle", "cotas", "ES-400", section=(55, 20)),
                _spec("K-7", "nota", "nota", "ES-200", section=(20, 55)),
            ]
        )
    )
    s = defs["K-7"].seccion_cm
    assert (s.valor, s.fuente, s.en_conflicto) == ((20, 55), "detalle", False)


def test_drawing_beats_ia_and_ia_is_kept():
    defs, _ = construir_definiciones(
        _inv(
            [
                _spec("K-4", "detalle", "pila", "ES-400", texts=["6#4", "EYG#3@15"]),
                _spec("K-4", "ia", "ia", "", stirrups="EYG#2@15"),
            ]
        )
    )
    e = defs["K-4"].estribos
    assert e.fuente == "detalle" and e.valor[0].numero == "3" and e.alternativas[0].fuente == "ia"


def test_unreadable_blocks_ia():
    defs, _ = construir_definiciones(
        _inv(
            [
                _spec("K-4", "detalle", "pila", "ES-400", texts=["6#4", "EYG#3@1S"]),
                _spec("K-4", "ia", "ia", "", stirrups="EYG#2@15"),
            ]
        )
    )
    assert defs["K-4"].estribos.ilegible and defs["K-4"].estribos.valor is None
    assert defs["K-4"].estribos.fuente == "detalle"
    assert [a.fuente for a in defs["K-4"].estribos.alternativas] == ["ia"]


def test_ia_fills_only_what_nothing_in_the_drawing_says():
    defs, _ = construir_definiciones(
        _inv(
            [
                _spec("K-9", "detalle", "cotas", "ES-200", section=(15, 15)),
                _spec("K-9", "ia", "ia", "", rebar="4#3", section_cm=(20, 20)),
            ]
        )
    )
    k9 = defs["K-9"]
    assert (k9.seccion_cm.valor, k9.seccion_cm.fuente) == ((15, 15), "detalle")
    assert k9.longitudinales.fuente == "ia" and k9.longitudinales.valor[0].cantidad == 4
    assert k9.estribos is None


# ------------------------------------------------------- R69: el bloqueo de la IA sigue en pie


def _notas(tmp_path, textos, nombre="notas.dxf"):
    doc = ezdxf.new("R2010")
    msp = doc.modelspace()
    for i, texto in enumerate(textos):
        msp.add_text(texto, height=0.2).set_placement((0, i * 5.0))
    path = tmp_path / nombre
    doc.saveas(path)
    return DxfParser().parse_file(path).entities


def _frame(code="ES-400"):
    return [SheetFrame(frame_id="f0", bbox=(-50.0, -50.0, 50.0, 50.0), code=code)]


def _ia(mark, **campos):
    return {"mark": mark, "family": "castillo", "source": "ia", "source_text": "IA",
            "confidence": 0.5, **campos}  # fmt: skip


@pytest.mark.parametrize("marca_ia", ["K-7", "K7"])
def test_a_blocked_ai_value_is_never_elected(tmp_path, marca_ia):
    # «K-7 E#3@1S» no lo lee nadie (sin lector): la IA no lo cubre, tampoco en las definiciones,
    # aunque el plano no tenga ninguna lectura de K-7; y la IA «K7» se junta con K-7 (R69).
    inv = build_schedule_inventory(_notas(tmp_path, ["K-7 E#3@1S"]), frames=_frame())
    merge_external_specs(inv, [_ia(marca_ia, stirrups="E#2@20", section_cm=(15, 15))], C)
    defs, _ = construir_definiciones(inv, C)
    e = defs["K-7"].estribos
    assert e.ilegible and e.valor is None and e.fuente == "nota" and e.texto == "K-7 E#3@1S"
    assert [(a.fuente, a.valor[0].numero) for a in e.alternativas] == [("ia", "2")]
    assert defs["K-7"].seccion_cm.fuente == "ia"  # la nota no dice sección: la IA sí la llena
    assert any("alternativa" in a for a in defs["K-7"].avisos)


def test_a_block_by_another_marks_reading_keeps_the_ai_out(tmp_path):
    # T1-1 y T-11 se cubren entre sí en el bloqueo (R65) pero son marcas distintas: la lectura de
    # T1-1 no está en la definición de T-11 y aun así la IA de T-11 no se elige.
    inv = build_schedule_inventory(_notas(tmp_path, ["T1-1 4#3"]), frames=_frame())
    merge_external_specs(inv, [_ia("T-11", rebar="6#4", family="trabe")], C)
    defs, _ = construir_definiciones(inv, C)
    assert defs["T1-1"].longitudinales.valor[0].cantidad == 4
    t11 = defs["T-11"].longitudinales
    assert t11.ilegible and t11.fuente == "nota" and t11.alternativas[0].fuente == "ia"


def test_a_rejected_stack_line_blocks_from_the_detail(tmp_path):
    from ezdxf.enums import TextEntityAlignment

    doc = ezdxf.new("R2010")
    msp = doc.modelspace()
    for marca, y in (("K-1", 0.0), ("K-2", 0.40)):
        msp.add_text(marca, height=0.13).set_placement(
            (0.0, y), align=TextEntityAlignment.BOTTOM_CENTER
        )
    msp.add_text("6#4", height=0.10).set_placement((-0.05, 0.215))
    doc.saveas(tmp_path / "amb.dxf")
    inv = build_schedule_inventory(
        DxfParser().parse_file(tmp_path / "amb.dxf").entities, frames=_frame()
    )
    merge_external_specs(inv, [_ia("K-1", rebar="4#3")], C)
    defs, _ = construir_definiciones(inv, C)
    longitudinales = defs["K-1"].longitudinales
    assert (longitudinales.ilegible, longitudinales.fuente, longitudinales.texto) == (
        True,
        "detalle",
        "6#4",
    )


# ------------------------------------------------------------ R4: la fuente de cada lectura


def test_every_source_and_method_has_its_fuente():
    assert FUENTE_DE_LECTURA[("cuadro", "fila")] == "cuadro"
    assert FUENTE_DE_LECTURA[("detalle", "pila")] == "detalle"
    assert FUENTE_DE_LECTURA[("detalle", "cotas")] == "detalle"
    assert FUENTE_DE_LECTURA[("detalle", "llamada")] == "detalle"
    assert FUENTE_DE_LECTURA[("detalle", "geometria")] == "seccion_dibujada"
    assert FUENTE_DE_LECTURA[("cuadro", "nota")] == "cuadro"  # un lector por disciplina
    assert {f for (s, _m), f in FUENTE_DE_LECTURA.items() if s == "nota"} == {"nota"}
    assert {f for (s, _m), f in FUENTE_DE_LECTURA.items() if s == "ia"} == {"ia"}


def test_an_unmapped_pair_raises_never_defaults():
    # Ningún lector da una pila de cuadro: si alguno la diera, revienta, no se supone su fuente.
    spec = _spec("K-1", "cuadro", "pila", "ES-200", section=(15, 15))
    with pytest.raises(ValueError, match="cuadro.*pila"):
        fuente_de_lectura(spec)
    with pytest.raises(ValueError):
        construir_definiciones(_inv([spec]))


def _texto(entity_id, text, x, y, height=0.1):
    bbox = (x, y, x + 0.5 * len(text) * height, y + height)
    return NormalizedEntity(
        entity_id=entity_id, entity_type=EntityType.text, source_file="a.dxf", layer="TEXTO",
        bbox=bbox, text=text, properties={"height": height}, raw_handle=entity_id,
        evidence=EvidencePacket(source="a.dxf", method="t", entity_ids=[entity_id], bbox=bbox,
                                confidence=1.0),
    )  # fmt: skip


def _cota(entity_id, x, y, w, h, display_cm):
    bbox = (x, y, x + w, y + h)
    return NormalizedEntity(
        entity_id=entity_id, entity_type=EntityType.dimension, source_file="a.dxf",
        layer="COTAS1", bbox=bbox, raw_handle=entity_id,
        properties={"display_value": float(display_cm), "dimlfac": 100.0,
                    "measurement": display_cm / 100.0},
        evidence=EvidencePacket(source="a.dxf", method="t", entity_ids=[entity_id], bbox=bbox,
                                confidence=1.0),
    )  # fmt: skip


def _rectangulo(entity_id, x0, y0, x1, y1):
    return NormalizedEntity(
        entity_id=entity_id, entity_type=EntityType.polyline, source_file="a.dxf",
        layer="EST-DET", bbox=(x0, y0, x1, y1),
        points=[(x0, y0), (x1, y0), (x1, y1), (x0, y1)], raw_handle=entity_id,
        properties={"closed": True},
        evidence=EvidencePacket(source="a.dxf", method="t", entity_ids=[entity_id],
                                bbox=(x0, y0, x1, y1), confidence=1.0),
    )  # fmt: skip


def _todas_las_lecturas(tmp_path):
    """Una lectura de cada lector: fila de cuadro, pila, nota de marca y de familia, cotas,
    sección dibujada, llamada, la IA y un lector por disciplina."""
    detalle = [(0.0, 0.0, 44.0, 29.4)]
    geometria = [
        _rectangulo("r1", 10.0, 10.0, 10.3, 10.6),
        _rectangulo("e1", 10.03, 10.03, 10.27, 10.57),
        _texto("m1", "T1-4", 10.05, 10.75),
    ]
    llamada = [
        _texto("m2", "CTA-16", 2.0, 20.0, 0.12),
        _texto("l1", "SECCIÓN 1", 21.0, 15.0),
        _texto("s1", "30X80", 21.0, 14.8),
    ]
    cotas = [
        _texto("m3", "CTA-3", 30.0, 25.0, 0.12),
        _cota("d1", 29.0, 23.0, 0.3, 0.8, 80),
        _cota("d2", 29.5, 23.6, 0.3, 0.2, 30),
    ]
    inv = build_schedule_inventory(geometria + llamada + cotas, C, 1.0, detalle)

    doc = ezdxf.new("R2010")
    msp = doc.modelspace()
    for col, titulo in enumerate(["MARCA", "SECCION", "ARMADO", "ESTRIBOS"]):
        msp.add_text(titulo, height=0.25).set_placement((col * 3, 10))
    for col, valor in enumerate(["K-1", "15x20", "4#3", "E#2@20"]):
        msp.add_text(valor, height=0.25).set_placement((col * 3, 9.5))
    msp.add_text("K-9 20X40 4#3", height=0.2).set_placement((60, 0))
    msp.add_text("DALA 15x30 4#3,E#2@20", height=0.2).set_placement((60, 20))
    from ezdxf.enums import TextEntityAlignment

    msp.add_text("K-4", height=0.13).set_placement(
        (100.0, 0.0), align=TextEntityAlignment.BOTTOM_CENTER
    )
    for i, renglon in enumerate(["6#4", "EYG#3@15"]):
        msp.add_text(renglon, height=0.10).set_placement((99.821, 0.186 + (1 - i) * 0.17))
    doc.saveas(tmp_path / "lectores.dxf")

    def disciplina(_entities):
        return [
            ElementSpec(
                mark="CA-1", family="canceleria", source="cuadro",
                source_text="CUADRO DE CANCELERÍA: CA-1", confidence=0.9,
            )
        ]  # fmt: skip

    otra = build_schedule_inventory(
        DxfParser().parse_file(tmp_path / "lectores.dxf").entities,
        C,
        frames=[SheetFrame(frame_id="f", bbox=(-50.0, -50.0, 150.0, 50.0), code="ES-200")],
        extra_readers=[disciplina],
    )
    merge_external_specs(otra, [_ia("K-30", rebar="4#3")], C)
    return inv.specs + otra.specs


def test_every_reader_output_has_its_fuente(tmp_path):
    # R4: se recorren las lecturas que dan los lectores de verdad, no una lista escrita a mano.
    specs = _todas_las_lecturas(tmp_path)
    pares = {(s.source, s.metodo) for s in specs}
    assert pares == {
        ("cuadro", "fila"),
        ("cuadro", "nota"),
        ("detalle", "pila"),
        ("detalle", "cotas"),
        ("detalle", "geometria"),
        ("detalle", "llamada"),
        ("nota", "nota"),
        ("ia", "ia"),
    }
    assert all(fuente_de_lectura(s) for s in specs)
    defs, familias = construir_definiciones(_inv(specs), C)
    assert defs["T1-4"].seccion_cm.fuente == "seccion_dibujada"
    assert (defs["CTA-16"].seccion_cm.fuente, defs["CTA-3"].seccion_cm.fuente) == (
        "detalle",
        "detalle",
    )
    assert (defs["K-1"].seccion_cm.fuente, defs["CA-1"].familia) == ("cuadro", "canceleria")
    assert familias["dala"].longitudinales.fuente == "nota"


def test_marinas_readings_all_have_their_fuente():
    # Las lecturas del inventario real de Marina (con su lectura IA), por fuente y método.
    datos = json.loads(
        (Path(__file__).parent / "fixtures" / "marina_pares_de_lectura.json").read_text()
    )
    assert sum(datos["pares"].values()) == 476
    for par in datos["pares"]:
        source, metodo = par.split("/")
        assert FUENTE_DE_LECTURA[(source, metodo)]


# -------------------------------------------------------------------- familia y hojas


def test_a_family_disagreement_is_said_never_picked_in_silence():
    defs, _ = construir_definiciones(
        _inv(
            [
                _spec("D-1", "detalle", "pila", "ES-000", texts=["4#3"], family="dala"),
                _spec("D-1", "ia", "ia", "", rebar="4#3", family="dado"),
            ]
        )
    )
    assert defs["D-1"].familia == "dala"  # como se lee; E1 resuelve los dados
    assert any("familia" in a and "dado" in a and "dala" in a for a in defs["D-1"].avisos)


def test_family_notes_are_definitions_by_family(tmp_path):
    inv = build_schedule_inventory(
        _notas(tmp_path, ["DALA 15x30 4#3,E#2@20", "K-9 20X40"]), frames=_frame()
    )
    defs, familias = construir_definiciones(inv, C)
    dala = familias["dala"]
    assert (dala.marca, dala.seccion_cm.valor, dala.seccion_cm.fuente) == ("DALA", (15, 30), "nota")
    assert "DALA" not in defs and defs["K-9"].hojas == ["ES-400"]


def test_the_declared_pile_length_beats_the_ai():
    inv = _inv([_spec("P-4", "ia", "ia", "", length_m=8.0, family="pilote")])
    inv.pile_length_m = 12.0
    defs, _ = construir_definiciones(inv)
    assert (defs["P-4"].longitud_m.valor, defs["P-4"].longitud_m.fuente) == (12.0, "nota")
    assert defs["P-4"].longitud_m.alternativas[0].valor == 8.0


def test_the_hoja_of_a_dato_is_the_sheet_code_like_the_reglas():
    # Dato.hoja es el código de la hoja (como ``leer_reglas``): ``para_hoja`` empata
    # definiciones, reglas y colocaciones por él.
    defs, _ = construir_definiciones(
        _inv(
            [
                _spec("K-5", "detalle", "cotas", "ES-400", section=(20, 30)),
                _spec("K-5", "detalle", "cotas", "ES-200", section=(20, 40)),
            ]
        )
    )
    from klave_engine.estructura.dato import para_hoja

    assert para_hoja(defs["K-5"].seccion_cm, "ES-200").valor == (20, 40)
    assert para_hoja(defs["K-5"].seccion_cm, "ES-400").valor == (20, 30)


def test_two_frames_sharing_a_code_collide_and_it_is_said(tmp_path):
    # Dos marcos distintos con el mismo código: el código no los separa. Sus lecturas quedan bajo
    # «ES-200» (``para_hoja`` no las distingue) y la definición lo dice, nunca en silencio.
    doc = ezdxf.new("R2010")
    msp = doc.modelspace()
    msp.add_text("K-9 20X40", height=0.2).set_placement((0, 0))
    msp.add_text("K-9 20X30", height=0.2).set_placement((100, 0))
    doc.saveas(tmp_path / "specs.dxf")
    frames = [
        SheetFrame(frame_id="a", bbox=(-50.0, -50.0, 50.0, 50.0), code="ES-200"),
        SheetFrame(frame_id="b", bbox=(50.0, -50.0, 150.0, 50.0), code="ES-200"),
    ]
    inv = build_schedule_inventory(
        DxfParser().parse_file(tmp_path / "specs.dxf").entities, frames=frames
    )
    defs, _ = construir_definiciones(inv, C)
    s = defs["K-9"].seccion_cm
    assert s.en_conflicto and {s.hoja, s.alternativas[0].hoja} == {"ES-200"}
    (aviso,) = [a for a in defs["K-9"].avisos if "marcos distintos" in a]
    assert "a de specs.dxf" in aviso and "b de specs.dxf" in aviso


# ------------------------------------------------------------------- formas de los estribos


@pytest.mark.parametrize(
    "long,estr,formas",
    [
        (["8#8"], "2E#3EXT@10 CENTRO@20", [["perimetral", "rombo"]]),
        (["4#3"], "E#2@15", [["perimetral"]]),
        (["6#4"], "EYG#3@15", [["perimetral"], ["grapa"]]),
        (["4#5+2#4"], "2E#3@15", [["perimetral", "interior"]]),
        (["10#8"], "3E#3EXT@10 CENTRO@20", [["perimetral", "rombo", "interior"]]),
        (["6#8+6#6"], "4E#3EXT@10 CENTRO@20", [["perimetral", "rombo", "interior", "interior"]]),
        (["8#8+4#6"], "2E+1G#3EXT@10 CENTRO@15", [["perimetral", "rombo"], ["grapa"]]),
        (["4#4"], "2G#3@15", [["grapa", "grapa"]]),
    ],
)
def test_assumed_shapes(long, estr, formas):
    a = parsear_armado(long + [estr], "castillo")
    out, avisos = asignar_formas(a.estribos, a.longitudinales)
    assert [j.formas for j in out] == formas and all(j.formas_fuente == "supuesto" for j in out)
    assert avisos == [] and all(j.formas == [] for j in a.estribos)  # no toca lo que recibe


@pytest.mark.parametrize(
    "long,estr,motivo",
    [
        (["12#6"], "5E#3@15", "5 piezas"),
        ([], "E#3@15", "no hay varillas"),
        (["4#3"], "LIGA#2@20", "ligas"),
    ],
)
def test_shapes_that_cannot_be_assumed_are_said(long, estr, motivo):
    a = parsear_armado(long + [estr], "castillo")
    out, avisos = asignar_formas(a.estribos, a.longitudinales)
    assert [j.formas for j in out] == [[]] and out[0].formas_fuente is None
    assert len(avisos) == 1 and motivo in avisos[0]


def test_shapes_the_drawing_says_are_kept():
    dichas = JuegoEstribos(
        tipo="estribo", cantidad=2, numero="3", formas=["perimetral", "perimetral"],
        formas_fuente="corte",
    )  # fmt: skip
    a = parsear_armado(["8#8"], "castillo")
    out, avisos = asignar_formas([dichas], a.longitudinales)
    assert (out[0].formas, out[0].formas_fuente, avisos) == (
        ["perimetral", "perimetral"],
        "corte",
        [],
    )


def test_a_set_that_refers_to_a_cut_gets_assumed_shapes_and_says_so():
    a = parsear_armado(["12#6", "2E#3 VER CORTE"], "pilote")
    out, avisos = asignar_formas(a.estribos, a.longitudinales)
    assert out[0].formas == ["perimetral", "rombo"] and out[0].formas_fuente == "supuesto"
    assert len(avisos) == 1 and "VER CORTE" in avisos[0]
