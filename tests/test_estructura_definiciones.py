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
    # R90: el texto de T1-1 no nombra a T-11: no le da un dato ilegible; sólo deja fuera a la IA.
    assert defs["T-11"].longitudinales is None
    assert any("no se toma" in a and "T1-1 4#3" in a for a in defs["T-11"].avisos)


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


# ------------------------------------------------------- Tarea 8, ronda 1 (R74–R80)


def _notas_en_hojas(tmp_path, textos, nombre="hojas.dxf"):
    """Notas en hojas: ``textos`` es [(texto, hoja)] con la hoja ES-000, ES-100 o ES-200, cada una
    un marco de 100 de ancho."""
    x = {"ES-000": 0.0, "ES-100": 100.0, "ES-200": 200.0}
    doc = ezdxf.new("R2010")
    msp = doc.modelspace()
    for i, (texto, hoja) in enumerate(textos):
        msp.add_text(texto, height=0.2).set_placement((x[hoja], i * 5.0))
    doc.saveas(tmp_path / nombre)
    marcos = [
        SheetFrame(frame_id=h, bbox=(x0 - 40.0, -40.0, x0 + 40.0, 80.0), code=h)
        for h, x0 in x.items()
    ]
    return build_schedule_inventory(
        DxfParser().parse_file(tmp_path / nombre).entities, frames=marcos
    )


def _limpio(dato):
    return dato is not None and not dato.ilegible and not dato.en_conflicto


@pytest.mark.parametrize("con_ia", [False, True])
def test_a_longer_drawing_mark_never_feeds_a_shorter_one(tmp_path, con_ia):
    # C1-A (R74): «K-2A …» en dos hojas no le da datos ilegibles a K-2, ni le gana sus campos.
    inv = _notas_en_hojas(
        tmp_path,
        [
            ("K-2 15X20 4#3 E#2@15", "ES-100"),
            ("K-2A 20X20 4#4 E#2@15", "ES-100"),
            ("K-2A 20X20 4#4 E#2@15", "ES-200"),
        ],
    )
    if con_ia:
        merge_external_specs(inv, [_ia("K-2", rebar="6#6"), _ia("K-2A", rebar="6#6")], C)
    k2 = construir_definiciones(inv, C)[0]["K-2"]
    assert all(_limpio(getattr(k2, c)) for c in ("seccion_cm", "longitudinales", "estribos"))
    assert (k2.seccion_cm.valor, k2.longitudinales.valor[0].cantidad) == ((15, 20), 4)
    assert not [a for a in k2.avisos if "K-2A" in a]


@pytest.mark.parametrize("con_ia", [False, True])
def test_two_drawing_marks_with_the_same_loose_key_stay_apart(tmp_path, con_ia):
    # C1-B (R74): T-11 y T1-1 son marcas del plano distintas; la de T1-1 no es de T-11.
    inv = _notas_en_hojas(
        tmp_path,
        [("T-11 20X40 4#3", "ES-100"), ("T1-1 25X50 2#5", "ES-100"), ("T1-1 25X50 2#5", "ES-200")],
    )
    if con_ia:
        merge_external_specs(inv, [_ia("T-11", rebar="6#6", family="trabe")], C)
    defs = construir_definiciones(inv, C)[0]
    t11 = defs["T-11"]
    assert _limpio(t11.seccion_cm) and t11.seccion_cm.valor == (20, 40)
    assert _limpio(t11.longitudinales) and t11.longitudinales.fuente == "nota"
    assert defs["T1-1"].seccion_cm.valor == (25, 50)


@pytest.mark.parametrize("con_ia", [False, True])
def test_a_letter_variant_never_feeds_its_base_mark(tmp_path, con_ia):
    # C1-C (R74): «K-1-A …» no pone a K-1 en conflicto.
    inv = _notas_en_hojas(tmp_path, [("K-1 15X15 4#3", "ES-100"), ("K-1-A 15X20 4#4", "ES-100")])
    if con_ia:
        merge_external_specs(
            inv, [_ia("K-1", stirrups="E#2@15", section_cm=(20, 20), rebar="6#6")], C
        )
    k1 = construir_definiciones(inv, C)[0]["K-1"]
    assert _limpio(k1.seccion_cm) and _limpio(k1.longitudinales)
    assert (k1.estribos is None) != con_ia


@pytest.mark.parametrize(
    "notas,marca,campo,fuente",
    [
        (["K-9 E#3@1S"], "K-9", "estribos", "nota"),  # sin lector
        (["CORTE K-1 15X20 4#3"], "K-1", "seccion_cm", "nota"),  # título
        (["CORTE K-1 15X20 4#3"], "K-1", "longitudinales", "nota"),
        (["K-1 Y K-2 15X20 4#3"], "K-2", "longitudinales", "nota"),  # varias marcas
        (["K-1 A K-4 15X20 4#3"], "K-4", "seccion_cm", "nota"),  # extremo de un rango
        (["3.- K-7 E#3@1S"], "K-7", "estribos", "nota"),  # nota numerada
        (["TRABE-T 1 E#3@1S"], "T-1", "estribos", "nota"),  # texto de otra familia
        (["K-07 E#3@1S"], "K-07", "estribos", "nota"),
    ],
)
def test_an_unread_drawing_text_is_an_unreadable_value_without_ai(
    tmp_path, notas, marca, campo, fuente
):
    # R77: el plano dice algo de la marca y nadie lo leyó: es un dato ilegible de su campo, con
    # IA o sin ella. R85: la marca la nombra también otro texto (aquí, su etiqueta en planta).
    inv = build_schedule_inventory(_notas(tmp_path, [*notas, marca]), frames=_frame())
    dato = getattr(construir_definiciones(inv, C)[0][marca], campo)
    assert dato.ilegible and dato.valor is None and dato.fuente == fuente


@pytest.mark.parametrize(
    "nota,fantasmas",
    [
        ("K-9 E#3@1S", ["K-9"]),
        ("C-1 A 20 CM E#3@1S", ["C-20", "C-1", "C-1A"]),  # R85: «20 CM» no es el fin de un rango
        ("CASTILLOS K-1 A 3.00 M MAX 15X15 4#3 E#2@20", ["K-3", "K-1"]),
    ],
)
def test_a_mark_named_only_by_rejected_texts_has_no_definition(tmp_path, nota, fantasmas):
    inv = build_schedule_inventory(_notas(tmp_path, [nota]), frames=_frame())
    defs = construir_definiciones(inv, C)[0]
    assert not [m for m in fantasmas if m in defs]


def test_a_range_end_with_a_unit_feeds_no_mark_read_elsewhere(tmp_path):
    # R85: «K-1 A 3.00 M …» no le da copias ilegibles a una K-3 que se lee en otra parte.
    inv = build_schedule_inventory(
        _notas(tmp_path, ["CASTILLOS K-1 A 3.00 M MAX 15X15 4#3 E#2@20", "K-3 15X30 6#3"]),
        frames=_frame(),
    )
    k3 = construir_definiciones(inv, C)[0]["K-3"]
    assert all(_limpio(getattr(k3, c)) for c in ("seccion_cm", "longitudinales"))
    assert k3.estribos is None


@pytest.mark.parametrize("con_ia", [False, True])
def test_a_mark_named_only_in_a_rejected_text_is_still_a_drawing_mark(tmp_path, con_ia):
    # R84: «T1-1 E#3@1S» nombra a T1-1, marca del plano aunque nadie la lea: no es de T-11, y
    # «T-11 20X40 4#3», leída para T-11, no es de T1-1.
    inv = _notas_en_hojas(
        tmp_path,
        [("T-11 20X40 4#3", "ES-100"), ("T1-1 E#3@1S", "ES-100"), ("T1-1", "ES-200")],
    )
    if con_ia:
        merge_external_specs(inv, [_ia("T-11", stirrups="E#2@25", family="trabe")], C)
    defs = construir_definiciones(inv, C)[0]
    t11 = defs["T-11"]
    assert (t11.estribos is None) != con_ia and _limpio(t11.seccion_cm)
    assert t11.estribos is None or t11.estribos.fuente == "ia"  # «T1-1 E#3@1S» no es de T-11
    t1 = defs["T1-1"]
    assert t1.seccion_cm is None and t1.longitudinales is None and t1.estribos.ilegible


def test_an_own_value_is_not_in_conflict_with_another_marks_unread_text(tmp_path):
    inv = _notas_en_hojas(
        tmp_path,
        [("T-11 20X40 4#3 E#2@20", "ES-100"), ("T1-1 E#3@1S", "ES-100"), ("T1-1", "ES-200")],
    )
    assert _limpio(construir_definiciones(inv, C)[0]["T-11"].estribos)


@pytest.mark.parametrize("con_ia", [False, True])
def test_a_longer_mark_named_only_in_a_rejected_text_never_blocks_the_shorter(tmp_path, con_ia):
    # R84: «K-2A E#3@1S» es de K-2A; K-2 no tiene estribos ilegibles y la IA se los llena.
    inv = build_schedule_inventory(
        _notas(tmp_path, ["K-2 15X20 4#3", "K-2A E#3@1S"]), frames=_frame()
    )
    if con_ia:
        merge_external_specs(inv, [_ia("K-2", stirrups="E#2@15")], C)
        assert inv.by_mark["K-2"].stirrups == "E#2@15"
    k2 = construir_definiciones(inv, C)[0]["K-2"]
    assert (k2.estribos is None) != con_ia and (k2.estribos is None or not k2.estribos.ilegible)


def test_an_ambiguous_stack_line_is_unreadable_for_both_labels(tmp_path):
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
    defs = construir_definiciones(inv, C)[0]
    for marca in ("K-1", "K-2"):
        d = defs[marca].longitudinales
        assert (d.ilegible, d.fuente, d.texto) == (True, "detalle", "6#4")
        assert defs[marca].estribos is None  # «6#4» son varillas: sólo dice longitudinales


def test_an_ambiguous_text_is_only_an_aviso_where_the_mark_has_its_own_value(tmp_path):
    # R74: «6#4» entre K-1 y K-2, y K-1 lee sus varillas en otra hoja: para K-1 es un aviso.
    from ezdxf.enums import TextEntityAlignment

    doc = ezdxf.new("R2010")
    msp = doc.modelspace()
    for marca, y in (("K-1", 0.0), ("K-2", 0.40)):
        msp.add_text(marca, height=0.13).set_placement(
            (0.0, y), align=TextEntityAlignment.BOTTOM_CENTER
        )
    msp.add_text("6#4", height=0.10).set_placement((-0.05, 0.215))
    msp.add_text("K-1 4#3", height=0.2).set_placement((100.0, 0.0))
    doc.saveas(tmp_path / "amb2.dxf")
    frames = [
        SheetFrame(frame_id="a", bbox=(-50.0, -50.0, 50.0, 50.0), code="ES-400"),
        SheetFrame(frame_id="b", bbox=(50.0, -50.0, 150.0, 50.0), code="ES-200"),
    ]
    inv = build_schedule_inventory(
        DxfParser().parse_file(tmp_path / "amb2.dxf").entities, frames=frames
    )
    defs = construir_definiciones(inv, C)[0]
    assert _limpio(defs["K-1"].longitudinales) and defs["K-1"].longitudinales.valor[0].cantidad == 4
    assert any("puede ser de esta marca o de otra" in a for a in defs["K-1"].avisos)
    assert defs["K-2"].longitudinales.ilegible


def test_a_read_value_beats_unreadable_copies(tmp_path):
    # R76: una hoja que se lee y dos que no: gana la leída, el conflicto y las ilegibles se ven;
    # lo ilegible sólo reclama los estribos (sus varillas sí se leyeron).
    inv = _notas_en_hojas(
        tmp_path,
        [
            ("K-9 15X20 4#3 E#2@15", "ES-000"),
            ("K-9 15X20 4#3 E#2@1S", "ES-100"),
            ("K-9 15X20 4#3 E#2@1S", "ES-200"),
        ],
    )
    k9 = construir_definiciones(inv, C)[0]["K-9"]
    e = k9.estribos
    assert (e.ilegible, e.en_conflicto, e.hoja) == (False, True, "ES-000")
    assert [a.ilegible for a in e.alternativas] == [True, True]
    assert _limpio(k9.longitudinales) and k9.parrillas is None


@pytest.mark.parametrize(
    "spec,valor",
    [
        (("T1-1", "detalle", "cotas", (40, 20), "trabe"), (40, 20)),  # una trabe plana: b×h
        (("K-7", "detalle", "cotas", (55, 20), "castillo"), (20, 55)),  # un castillo: ordenada
    ],
)
def test_a_beam_keeps_its_bxh(spec, valor):
    marca, source, metodo, section, family = spec
    defs, _ = construir_definiciones(
        _inv([_spec(marca, source, metodo, "ES-101", section=section, family=family)])
    )
    assert defs[marca].seccion_cm.valor == valor


def test_a_beam_section_is_read_as_written_and_orientations_conflict(tmp_path):
    # R75: «T-1 40X20» es 40×20 tal cual; contra unas cotas de 20×40 es un conflicto.
    inv = _notas_en_hojas(tmp_path, [("T-1 40X20 4#3", "ES-100"), ("K-1 20X15 4#3", "ES-100")])
    assert [s.section_cm for s in inv.specs if s.mark == "T-1"] == [(40, 20)]
    assert [s.section_cm for s in inv.specs if s.mark == "K-1"] == [(15, 20)]
    inv.specs.append(_spec("T-1", "nota", "nota", "ES-200", section=(20, 40), family="trabe"))
    t1 = construir_definiciones(inv, C)[0]["T-1"].seccion_cm
    assert t1.en_conflicto and {t1.valor, t1.alternativas[0].valor} == {(40, 20), (20, 40)}


def test_an_ai_mark_that_is_a_family_name_is_the_familys():
    # R80: la IA «DALA» es de la familia, no una marca fantasma.
    inv = _inv([_spec("DALA", "ia", "ia", "ES-101", family="dala", stirrups="E#2@20")])
    defs, familias = construir_definiciones(inv)
    assert "DALA" not in defs and familias["dala"].estribos.fuente == "ia"


def test_an_unknown_family_takes_the_ais_and_says_so():
    inv = _inv(
        [
            _spec("TE-A", "nota", "nota", "ES-007", section=(20, 40), family="elemento"),
            _spec("TE-A", "ia", "ia", "ES-007", family="trabe", stirrups="E#3@20"),
        ]
    )
    te = construir_definiciones(inv)[0]["TE-A"]
    assert te.familia == "trabe" and any("se toma la de la IA" in a for a in te.avisos)


def test_an_ai_string_is_read_whole():
    # R80: «4#3 E#2@15» como varillas trae también sus estribos; nada se tira callado.
    inv = _inv([_spec("K-30", "ia", "ia", "ES-200", rebar="4#3 E#2@15")])
    k = construir_definiciones(inv)[0]["K-30"]
    assert k.longitudinales.valor[0].cantidad == 4 and k.estribos.valor[0].numero == "2"
    inv = _inv([_spec("MC-1", "ia", "ia", "ES-002", rebar="#4@20", family="muro_concreto")])
    mc = construir_definiciones(inv)[0]["MC-1"]
    assert mc.parrillas.fuente == "ia" and mc.longitudinales is None


def test_an_ai_dato_carries_its_sheet():
    inv = _inv([_spec("K-30", "ia", "ia", "ES-200", rebar="4#3")])
    assert construir_definiciones(inv)[0]["K-30"].longitudinales.hoja == "ES-200"


def test_a_written_length_blocks_the_ais(tmp_path):
    # R80: la longitud es un campo; «P-4 L=8.00 M» la dice (sin leerse) y la IA no la llena.
    inv = build_schedule_inventory(_notas(tmp_path, ["P-4 L=8.00 M"]), frames=_frame())
    merge_external_specs(inv, [_ia("P-4", length_m=12.0, family="pilote")], C)
    assert "P-4" not in inv.by_mark or inv.by_mark["P-4"].length_m is None
    largo = construir_definiciones(inv, C)[0]["P-4"].longitud_m
    assert largo.ilegible and largo.alternativas[0].valor == 12.0


def test_a_cut_reference_without_a_count_has_no_assumed_shapes():
    a = parsear_armado(["12#6", "E#3 VER CORTE"], "pilote")
    out, avisos = asignar_formas(a.estribos, a.longitudinales)
    assert out[0].formas == [] and out[0].formas_fuente is None
    assert len(avisos) == 1 and "VER CORTE" in avisos[0]


def test_an_ai_family_never_reorients_a_section_read_as_written(tmp_path):
    # R88: «TE-A 40X20» se lee tal cual; con la familia «trabe» de la IA sigue siendo 40×20.
    inv = build_schedule_inventory(_notas(tmp_path, ["TE-A 40X20 4#4"]), frames=_frame())
    merge_external_specs(inv, [_ia("TE-A", stirrups="E#3@20", family="trabe")], C)
    te = construir_definiciones(inv, C)[0]["TE-A"]
    assert te.familia == "trabe" and _limpio(te.seccion_cm) and te.seccion_cm.valor == (40, 20)


def test_the_same_blocking_text_counts_once_whatever_the_order():
    # R89: el bloqueo que trae la IA y el que se calcula para el mismo texto son uno.
    from klave_engine.detection.schedules import Bloqueo
    from klave_engine.estructura.definiciones import _sin_leer

    comun = {"campo": "estribos", "texto": "K-7 E#3@1S", "entidades": ["e1"], "fuente": "nota"}
    duda = Bloqueo(**comun, por="respaldo", inequivoco=False)
    suyo = Bloqueo(**comun, por="texto", inequivoco=True)
    for orden in ([duda, suyo], [suyo, duda]):
        datos = {
            c: [] for c in ("seccion_cm", "longitud_m", "longitudinales", "estribos", "parrillas")
        }
        avisos: list[str] = []
        _sin_leer(orden, [], datos, avisos)
        assert [d.ilegible for d in datos["estribos"]] == [True] and avisos == []


# ------------------------------------------------------- Tarea 8, ronda 3 (R90–R94)


@pytest.mark.parametrize(
    "otro",
    [
        "CORTE T1-1 E#3@1S",  # un título
        "T1-1 Y T1-2 E#3@1S",  # una lista
        "T1-1 A T1-3 30X60 4#5",  # un rango
    ],
)
@pytest.mark.parametrize("con_ia", [False, True])
def test_a_text_that_names_another_mark_never_feeds_this_one(tmp_path, otro, con_ia):
    # R90: sólo la gramática dice de quién es un texto; la llave suelta (T-11 ≈ T1-1) sólo
    # bloquea a la IA, nunca da un dato ilegible ni un conflicto en otra marca.
    inv = _notas_en_hojas(tmp_path, [("T-11 20X40 4#3", "ES-100"), (otro, "ES-100")])
    if con_ia:
        merge_external_specs(
            inv, [_ia("T-11", stirrups="E#2@20", section_cm=(25, 25), family="trabe")], C
        )
    t11 = construir_definiciones(inv, C)[0]["T-11"]
    for campo in ("seccion_cm", "longitudinales"):
        assert _limpio(getattr(t11, campo))
    assert t11.estribos is None or not t11.estribos.ilegible
    if con_ia and "E#3" in otro and not otro.startswith("CORTE"):
        assert t11.estribos is None and any("no se toma" in a for a in t11.avisos)
    if con_ia and otro.startswith("CORTE"):
        # R97: el título nombra T1-1 («unica»): T1-1 es una marca del plano, distinta de T-11
        # (R84), y su texto no le dice nada a T-11: la IA de T-11 se toma.
        assert t11.estribos is not None and t11.estribos.fuente == "ia"


def test_a_title_of_a_longer_mark_never_feeds_the_shorter(tmp_path):
    inv = build_schedule_inventory(
        _notas(tmp_path, ["K-2 15X20 4#3", "DET. K-2A E#3@1S"]), frames=_frame()
    )
    k2 = construir_definiciones(inv, C)[0]["K-2"]
    assert k2.estribos is None and _limpio(k2.seccion_cm)


@pytest.mark.parametrize(
    "nota,campo",
    [
        ("K-1 DE 15 CM 4#3 E#2@20", "seccion_cm"),  # R92: «DE 15 CM» puede ser la sección
        ("K-1 15X15 N° 3 E#2@15", "longitudinales"),  # R92: la cita es «N° 3», entera
    ],
)
def test_an_unread_residue_claims_what_it_could_be(tmp_path, nota, campo):
    inv = build_schedule_inventory(_notas(tmp_path, [nota]), frames=_frame())
    merge_external_specs(inv, [_ia("K-1", section_cm=(25, 25), rebar="6#4")], C)
    k1 = construir_definiciones(inv, C)[0]["K-1"]
    dato = getattr(k1, campo)
    assert dato.ilegible and [a.fuente for a in dato.alternativas] == ["ia"]


@pytest.mark.parametrize(
    "nota,marca,familia",
    [
        ("T-1 30X60 E#3@15 LS V 3", "T-1", "trabe"),
        ("K-1 15X15 E#2@20 CON V 4", "K-1", "castillo"),
        ("T-1 20X40 V 4 LS V 3 LI E#3@15", "T-1", "trabe"),  # rechazado: nombra T-1 y V-4
    ],
)
def test_an_unread_bar_count_keeps_the_ai_bars_out(tmp_path, nota, marca, familia):
    # R96: «V 3», «V 4» son varillas sin leer en el texto entero: las varillas son ilegibles.
    inv = build_schedule_inventory(_notas(tmp_path, [nota]), frames=_frame())
    merge_external_specs(inv, [_ia(marca, family=familia, rebar="6#6")], C)
    d = construir_definiciones(inv, C)[0][marca].longitudinales
    assert d.ilegible and d.fuente == "nota" and [a.fuente for a in d.alternativas] == ["ia"]


def test_a_cut_title_of_two_marks_feeds_both(tmp_path):
    # R97: «CORTE K-1 Y K-2 E#3@1S» nombra a K-1 y a K-2: los estribos de las dos son ilegibles
    # (antes K-1, el del título, quedaba fuera y la IA lo llenaba).
    inv = build_schedule_inventory(_notas(tmp_path, ["CORTE K-1 Y K-2 E#3@1S"]), frames=_frame())
    merge_external_specs(inv, [_ia(m, stirrups="E#2@20") for m in ("K-1", "K-2")], C)
    defs, _ = construir_definiciones(inv, C)
    for m in ("K-1", "K-2"):
        e = defs[m].estribos
        assert e.ilegible and e.texto == "CORTE K-1 Y K-2 E#3@1S"


def test_a_footing_mesh_is_never_the_ais(tmp_path):
    # R95: ZA-3 es zapata: su malla es la del plano.
    inv = build_schedule_inventory(_notas(tmp_path, ["ZA-3 120X150 #4@20"]), frames=_frame())
    merge_external_specs(inv, [_ia("ZA-3", family="zapata", mesh="#5@15")], C)
    za = construir_definiciones(inv, C)[0]["ZA-3"]
    assert za.familia == "zapata" and za.parrillas.fuente == "nota"
    assert [(p.numero, p.separacion_m) for p in za.parrillas.valor] == [("4", 0.2)]


def test_anchor_bars_never_become_the_columns(tmp_path):
    # R98: ni las varillas ni la sección de la placa son de C-1; la IA tampoco las llena.
    inv = build_schedule_inventory(
        _notas(tmp_path, ["C-1 PLACA BASE 35X35 CON ANCLAS 4 PZAS #6"]), frames=_frame()
    )
    merge_external_specs(inv, [_ia("C-1", family="columna", rebar="8#8", section_cm=(40, 40))], C)
    c1 = construir_definiciones(inv, C)[0]["C-1"]
    for campo in ("seccion_cm", "longitudinales"):
        d = getattr(c1, campo)
        assert d.ilegible and d.valor is None and [a.fuente for a in d.alternativas] == ["ia"]
    assert any("no es armado del elemento" in a for a in c1.avisos)


@pytest.mark.parametrize(
    "notas,marca",
    [
        (["K-1 15X15 4#3 E#2@15 VER CORTE C-2", "C-2 30X30 8#6 E#3@20"], "C-2"),  # R99
        (["CORTE K-1 4#3 VER DET. K-2", "K-2 15X20 4#4 E#2@20"], "K-2"),
    ],
)
def test_a_pointer_never_feeds_the_pointed_mark(tmp_path, notas, marca):
    # R99: una referencia tras el armado remite: no nombra a la marca apuntada, que queda limpia.
    inv = build_schedule_inventory(_notas(tmp_path, notas), frames=_frame())
    d = construir_definiciones(inv, C)[0][marca]
    for campo in ("seccion_cm", "longitudinales", "estribos"):
        assert _limpio(getattr(d, campo)) and len(getattr(d, campo).alternativas) == 0


def test_a_heading_with_a_pointer_is_its_marks_only(tmp_path):
    # R99: «CORTE K-1 4#3 VER DET. K-2» es de K-1 (no se lee): sus varillas son ilegibles.
    inv = build_schedule_inventory(
        _notas(tmp_path, ["CORTE K-1 4#3 VER DET. K-2"]), frames=_frame()
    )
    merge_external_specs(inv, [_ia("K-1", rebar="6#6")], C)
    k1 = construir_definiciones(inv, C)[0]["K-1"].longitudinales
    assert k1.ilegible and k1.texto == "CORTE K-1 4#3 VER DET. K-2"


def test_a_bar_word_after_the_armado_keeps_the_ai_bars_out(tmp_path):
    # R101: «V 4» tras el armado de K-1 no es la marca V-4: K-1 se lee y sus varillas son ilegibles.
    inv = build_schedule_inventory(_notas(tmp_path, ["K-1 15X15 E#2@20 V 4"]), frames=_frame())
    merge_external_specs(inv, [_ia("K-1", rebar="6#6")], C)
    defs, _ = construir_definiciones(inv, C)
    assert "V-4" not in defs
    k1 = defs["K-1"]
    assert k1.seccion_cm.valor == (15, 15) and k1.seccion_cm.fuente == "nota"
    assert k1.longitudinales.ilegible and [a.fuente for a in k1.longitudinales.alternativas] == [
        "ia"
    ]
