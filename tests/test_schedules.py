"""Sheet-declared specifications: tables, details, notes, and their authority."""

import ezdxf
import pytest
from ezdxf.enums import TextEntityAlignment
from klave_engine.costing.sintesis import firma
from klave_engine.detection.frames import SheetFrame
from klave_engine.detection.results import DetectionType, make_detection
from klave_engine.detection.schedules import (
    apply_schedule,
    build_schedule_inventory,
    campos_de_fragmento,
    family_of_mark,
    mark_cuadro_detections,
    merge_external_specs,
)
from klave_engine.detection.text_patterns import TextPatternConfig
from klave_engine.dxf.entities import EntityType, EvidencePacket, NormalizedEntity
from klave_engine.dxf.parser import DxfParser

C = TextPatternConfig()


def _entities(tmp_path, build):
    doc = ezdxf.new("R2010")
    build(doc.modelspace())
    path = tmp_path / "specs.dxf"
    doc.saveas(path)
    return DxfParser().parse_file(path).entities


def test_table_rows_become_specs_by_mark(tmp_path):
    def build(msp):
        header = ["MARCA", "SECCION", "ARMADO", "ESTRIBOS"]
        for col, title in enumerate(header):
            msp.add_text(title, height=0.25).set_placement((col * 3, 10))
        rows = [["K-1", "15x20", "4#3", "E#2@20"], ["K-2", "20 x 30", "6 VAR #4", "E#3@15"]]
        for r, row in enumerate(rows):
            for col, value in enumerate(row):
                msp.add_text(value, height=0.25).set_placement((col * 3, 9.5 - r * 0.5))
        msp.add_text("NOTAS GENERALES", height=0.25).set_placement((0, 2))  # far: ends the table

    inventory = build_schedule_inventory(_entities(tmp_path, build))
    assert inventory.tables_found == 1
    k1, k2 = inventory.by_mark["K-1"], inventory.by_mark["K-2"]
    assert (k1.section_cm, k1.rebar, k1.stirrups, k1.source) == (
        (15, 20),
        "4#3",
        "E#2@20",
        "cuadro",
    )
    assert (k2.section_cm, k2.rebar, k2.stirrups) == ((20, 30), "6#4", "E#3@15")
    assert k1.family == "castillo"


def test_detail_annotation_and_family_note(tmp_path):
    def build(msp):
        msp.add_text("C-1", height=0.3).set_placement((0, 0))
        msp.add_text("30x40  8#5  E#3@15", height=0.2).set_placement((1.0, -0.4))
        msp.add_text("CASTILLOS 15X30", height=0.2).set_placement((40, 40))  # a general note
        msp.add_text("DALA 15x30 4#3,E#2@20", height=0.2).set_placement((40, 38))
        msp.add_text("ZAPATA PARRILLA #4@20 AMBOS SENTIDOS", height=0.2).set_placement((40, 36))

    inventory = build_schedule_inventory(_entities(tmp_path, build))
    c1 = inventory.by_mark["C-1"]
    assert c1.source == "detalle" and c1.section_cm == (30, 40)
    assert c1.rebar == "8#5" and c1.stirrups == "E#3@15"
    assert inventory.by_family["castillo"].section_cm == (15, 30)
    assert inventory.by_family["dala"].rebar == "4#3"
    # La malla canónica lleva lo que el plano dice de ella: «AMBOS SENTIDOS» ya no se pierde.
    assert inventory.by_family["zapata"].mesh == "#4@20 A/S"
    assert "K-1" not in inventory.by_mark


def test_apply_stamps_sections_by_authority(tmp_path):
    def build(msp):
        msp.add_text("K-1 15x20 4#3 E#2@20", height=0.2).set_placement((0, 0))
        msp.add_text("CASTILLOS 15X30", height=0.2).set_placement((10, 10))

    inventory = build_schedule_inventory(_entities(tmp_path, build))
    k1 = make_detection("d1", DetectionType.column_tag, "K-1", (0, 0, 1, 1), 0.8, [], "m", [])
    k1.properties["section_area_du2"] = 0.5  # a measured marker the sheet overrules
    k1.properties["section_source"] = "marcador_poligonal"
    k7 = make_detection("d2", DetectionType.column_tag, "K-7", (0, 0, 1, 1), 0.8, [], "m", [])
    c9 = make_detection("d3", DetectionType.column_tag, "C-9", (0, 0, 1, 1), 0.8, [], "m", [])
    assert apply_schedule([k1, k7, c9], inventory, meters_factor=1.0) == 2
    assert k1.properties["section_cm"] == "15x20" and k1.properties["section_area_du2"] == 0.03
    assert k1.properties["section_marker_du2"] == 0.5  # kept as evidence, not used
    assert k7.properties["section_cm"] == "15x30"  # family-level note covers K-*
    assert "section_cm" not in c9.properties  # no spec for columnas: assumptions apply
    assert apply_schedule([k1], inventory, meters_factor=None) == 0


# ------------------------------------------------- Task 7: la lectura sin sus cinco fallas
# La geometría medida en Marina: la etiqueta (alto 0.13, centrada) DEBAJO de sus renglones de
# armado (alto 0.10, alineados a la izquierda), a 0.17 de paso; el de arriba es el primero.


def _stack_entities(tmp_path, mark, lines, loose=(), copias=((0.0, 0.0),), nombre="pila.dxf"):
    """La pila de ``mark`` (renglones de arriba abajo) en cada punto de ``copias``; ``loose``
    son textos sueltos (texto, x, y) de alto 0.10."""
    doc = ezdxf.new("R2010")
    msp = doc.modelspace()
    for cx, cy in copias:
        etiqueta = msp.add_text(mark, height=0.13)
        etiqueta.set_placement((cx, cy), align=TextEntityAlignment.BOTTOM_CENTER)
        for i, texto in enumerate(lines):
            y = cy + 0.186 + (len(lines) - 1 - i) * 0.17
            msp.add_text(texto, height=0.10).set_placement((cx - 0.179, y))
    for texto, x, y in loose:
        msp.add_text(texto, height=0.10).set_placement((x, y))
    path = tmp_path / nombre
    doc.saveas(path)
    return DxfParser().parse_file(path).entities


def _frame():
    return [SheetFrame(frame_id="f0", bbox=(-50.0, -50.0, 50.0, 50.0), code="ES-400")]


def _frames_es200_es400():
    return [
        SheetFrame(frame_id="f0", bbox=(-50.0, -50.0, 50.0, 50.0), code="ES-400"),
        SheetFrame(frame_id="f1", bbox=(50.0, -50.0, 150.0, 50.0), code="ES-200"),
    ]


def _two_frames_with(tmp_path, mark, lines, seccion_es400, seccion_es200):
    """La misma pila en dos hojas (ES-400 a la izquierda, ES-200 a la derecha), cada una con su
    sección escrita en su primer renglón."""
    doc = ezdxf.new("R2010")
    msp = doc.modelspace()
    for cx, (a, b) in ((0.0, seccion_es400), (100.0, seccion_es200)):
        etiqueta = msp.add_text(mark, height=0.13)
        etiqueta.set_placement((cx, 0.0), align=TextEntityAlignment.BOTTOM_CENTER)
        renglones = [f"{a}x{b} {lines[0]}", *lines[1:]]
        for i, texto in enumerate(renglones):
            y = 0.186 + (len(renglones) - 1 - i) * 0.17
            msp.add_text(texto, height=0.10).set_placement((cx - 0.179, y))
    path = tmp_path / "dos_hojas.dxf"
    doc.saveas(path)
    return DxfParser().parse_file(path).entities


def test_eyg_is_estribo_y_grapa_never_mesh(tmp_path):
    inv = build_schedule_inventory(
        _stack_entities(tmp_path, "K-4", ["6#4", "EYG#3@15"]), frames=_frame()
    )
    k4 = inv.by_mark["K-4"]
    assert (k4.rebar, k4.stirrups, k4.mesh) == ("6#4", "EYG#3@15", None)
    assert [(j.tipo, j.numero) for j in k4.armado.estribos] == [("estribo", "3"), ("grapa", "3")]


def test_all_bar_groups_kept(tmp_path):
    inv = build_schedule_inventory(
        _stack_entities(tmp_path, "K-6", ["4#5+2#4", "2E#3@15"]), frames=_frame()
    )
    assert inv.by_mark["K-6"].rebar == "4#5+2#4" and inv.by_mark["K-6"].stirrups == "2E#3@15"


@pytest.mark.parametrize("y", [0.9, -0.25])
def test_slab_label_is_not_k4s(tmp_path, y):
    # Encima de la pila (fuera de su alcance) o justo debajo de la etiqueta, donde el lector viejo
    # se la daba a K-4 por ser el texto con armado más cercano.
    losa = "LOSA MACIZA DOBLEMENTE ARMADA H=20 LS #4@20 A/S LI #4@20 A/S"
    inv = build_schedule_inventory(
        _stack_entities(tmp_path, "K-4", ["6#4", "EYG#3@15"], loose=[(losa, 0.0, y)]),
        frames=_frame(),
    )
    assert all("LOSA" not in s.source_text for s in inv.specs if s.mark == "K-4")
    assert inv.by_mark["K-4"].mesh is None and inv.by_mark["K-4"].rebar == "6#4"


def test_ia_never_covers_an_unreadable_text(tmp_path):
    inv = build_schedule_inventory(
        _stack_entities(tmp_path, "K-4", ["6#4", "EYG#3@1S"]), frames=_frame()
    )
    assert "estribos" in inv.by_mark["K-4"].campos_con_texto and inv.by_mark["K-4"].stirrups is None
    assert inv.by_mark["K-4"].avisos  # el texto que no se pudo leer se dice
    merge_external_specs(
        inv,
        [
            {
                "mark": "K-4",
                "family": "castillo",
                "stirrups": "EYG#2@15",
                "source": "ia",
                "source_text": "IA",
                "confidence": 0.5,
            }
        ],
        C,
    )
    assert inv.by_mark["K-4"].stirrups is None
    assert any(s.source == "ia" and s.mark == "K-4" for s in inv.specs)  # kept as a reading


def test_ia_fills_only_where_no_text(tmp_path):
    inv = build_schedule_inventory(_stack_entities(tmp_path, "K-4", ["6#4"]), frames=_frame())
    merge_external_specs(
        inv,
        [
            {
                "mark": "K-4",
                "family": "castillo",
                "stirrups": "E#2@15",
                "source": "ia",
                "source_text": "IA",
                "confidence": 0.5,
            }
        ],
        C,
    )
    assert inv.by_mark["K-4"].stirrups == "E#2@15"
    ia = next(s for s in inv.specs if s.source == "ia")
    assert ia.metodo == "ia"
    pila = next(s for s in inv.specs if s.metodo == "pila")
    assert pila.stirrups is None  # la lectura del plano no se toca: la IA llena la vista por marca


def test_conflicting_readings_are_all_kept(tmp_path):
    inv = build_schedule_inventory(
        _two_frames_with(tmp_path, "K-5", ["6#4", "EYG#3@15"], (20, 30), (20, 40)),
        frames=_frames_es200_es400(),
    )
    secs = {(s.hoja, s.section_cm) for s in inv.specs if s.mark == "K-5" and s.section_cm}
    assert secs == {("ES-200", (20, 40)), ("ES-400", (20, 30))}
    # La vista por marca usa una y dice que la otra hoja no coincide (nada se resuelve callado).
    k5 = inv.by_mark["K-5"]
    assert any("ES-200" in a and "ES-400" in a for a in k5.avisos)
    assert any("K-5" in n for n in inv.notes if "no coinciden" in n)


def test_stack_label_is_a_definition_not_a_placement(tmp_path):
    ents = _stack_entities(tmp_path, "K-11", ["8#6", "2E#3EXT@10", "CENTRO@20"])
    inv = build_schedule_inventory(ents, frames=_frame())
    label = next(e for e in ents if e.text == "K-11")
    assert label.entity_id in inv.cuadro_mark_entities
    tag = make_detection(
        "d1", DetectionType.column_tag, "K-11", (0, 0, 1, 1), 0.8, [label.entity_id], "m", []
    )
    assert mark_cuadro_detections([tag], inv) == 1 and tag.properties["role"] == "cuadro"


def test_a_stack_reading_keeps_its_source(tmp_path):
    ents = _stack_entities(tmp_path, "K-11", ["8#6", "2E#3EXT@10", "CENTRO@20"])
    inv = build_schedule_inventory(ents, frames=_frame())
    (k11,) = [s for s in inv.specs if s.mark == "K-11"]
    por_id = {e.entity_id: e.text for e in ents}
    assert (k11.source, k11.metodo, k11.hoja) == ("detalle", "pila", "ES-400")
    assert [por_id[i] for i in k11.entidades] == ["8#6", "2E#3EXT@10", "CENTRO@20"]
    assert k11.campos_con_texto == ["longitudinales", "estribos"] and k11.avisos == []
    assert (k11.rebar, k11.stirrups) == ("8#6", "2E#3 EXT@10 CENTRO@20")
    assert k11.source_text == "K-11 · 8#6 / 2E#3EXT@10 / CENTRO@20"
    assert k11.armado is not None and k11.armado.texto_original == "8#6 | 2E#3EXT@10 | CENTRO@20"


def test_a_section_in_the_stack_is_read_with_it(tmp_path):
    # R5: la sección escrita en la pila es parte de la lectura.
    inv = build_schedule_inventory(
        _stack_entities(tmp_path, "C-1", ["30x40 8#5", "E#3@15"]), frames=_frame()
    )
    c1 = inv.by_mark["C-1"]
    assert (c1.section_cm, c1.rebar, c1.stirrups) == ((30, 40), "8#5", "E#3@15")
    assert c1.campos_con_texto == ["seccion", "longitudinales", "estribos"]


def test_an_out_of_range_section_is_reported_not_dropped(tmp_path):
    inv = build_schedule_inventory(
        _stack_entities(tmp_path, "C-1", ["15x900 8#5", "E#3@15"]), frames=_frame()
    )
    c1 = inv.by_mark["C-1"]
    assert c1.section_cm is None and "seccion" in c1.campos_con_texto
    assert any("15x900" in a.lower() for a in c1.avisos)


def test_unowned_armado_text_is_reported(tmp_path):
    inv = build_schedule_inventory(
        _stack_entities(tmp_path, "K-1", ["4#3", "E#2@15"], loose=[("6#4", 20.0, 20.0)]),
        frames=_frame(),
    )
    assert [(r.texto, r.motivo, r.hoja) for r in inv.rechazos] == [("6#4", "sin_dueno", "ES-400")]
    assert "Textos de armado que no se pegaron a una marca: 1 sin dueño." in inv.notes


def test_cuadro_rows_keep_their_source(tmp_path):
    def build(msp):
        for col, title in enumerate(["MARCA", "SECCION", "ARMADO", "ESTRIBOS"]):
            msp.add_text(title, height=0.25).set_placement((col * 3, 10))
        rows = [["K-1", "15x20", "4#3", "E#2@20"], ["K-2", "20 x 30", "", ""]]
        for r, row in enumerate(rows):
            for col, value in enumerate(row):
                if value:
                    msp.add_text(value, height=0.25).set_placement((col * 3, 9.5 - r * 0.5))

    inv = build_schedule_inventory(_entities(tmp_path, build), frames=_frame())
    k1, k2 = inv.by_mark["K-1"], inv.by_mark["K-2"]
    assert (k1.source, k1.metodo, k1.hoja) == ("cuadro", "fila", "ES-400")
    assert k1.campos_con_texto == ["seccion", "longitudinales", "estribos"]
    # Una fila con sólo la sección también es una definición del cuadro.
    assert (k2.source, k2.metodo, k2.section_cm, k2.rebar) == ("cuadro", "fila", (20, 30), None)


def test_family_notes_read_through_the_parser(tmp_path):
    def build(msp):
        msp.add_text("DALA 15x30 4#3,E#2@20", height=0.2).set_placement((40, 38))
        msp.add_text("CADENAS DE CERRAMIENTO 15X25 4#3 E#2@15", height=0.2).set_placement((0, 0))

    inv = build_schedule_inventory(_entities(tmp_path, build), frames=_frame())
    dala = [s for s in inv.specs if s.family == "dala"]
    assert {(s.metodo, s.hoja, s.stirrups) for s in dala} == {
        ("nota", "ES-400", "E#2@20"),
        ("nota", "ES-400", "E#2@15"),
    }


def test_readings_from_other_sheets_never_complete_each_other(tmp_path):
    def build(msp):
        msp.add_text("K-9 20X40", height=0.2).set_placement((0, 0))
        msp.add_text("K-9 4#3", height=0.2).set_placement((100, 0))

    inv = build_schedule_inventory(_entities(tmp_path, build), frames=_frames_es200_es400())
    k9 = inv.by_mark["K-9"]
    assert (k9.section_cm, k9.rebar, k9.hoja) == ((20, 40), None, "ES-400")
    assert any("ES-200" in a and "4#3" in a for a in k9.avisos)


def test_a_family_note_without_armado_is_not_an_armado_reading(tmp_path):
    # La nota de huecos de Marina: su sección no es la del elemento y sus únicos números son su
    # numeración; no es una lectura (antes tampoco). R83: el anclaje «2 VARILLAS #5 ANCLADA AL MURO
    # O CADENA» tampoco es la nota de una familia (antes lo era de las dalas, por «CADENA»): ninguna
    # palabra de familia es su sujeto. Las dos se dicen, nunca se pierden.
    def build(msp):
        msp.add_text(
            "1.-EL REFUERZO PARA HUECOS DE HASTA 15X20CMS 2.-COLOCAR EL PASO A LA MITAD "
            "DEL PERALTE DE LA CONTRATRABE",
            height=0.2,
        ).set_placement((0, 0))
        msp.add_text("2 VARILLAS #5 ANCLADA AL MURO O CADENA", height=0.2).set_placement((0, 9))

    inv = build_schedule_inventory(_entities(tmp_path, build), frames=_frame())
    assert inv.specs == [] and inv.by_family == {}
    assert sorted((r.motivo, r.familias) for r in inv.rechazos) == [
        ("sin_lector", ["contratrabe"]),
        ("sin_lector", ["muro", "dala"]),
    ]


def _texto(entity_id, text, x, y, height=0.1):
    bbox = (x, y, x + 0.5 * len(text) * height, y + height)
    return NormalizedEntity(
        entity_id=entity_id,
        entity_type=EntityType.text,
        source_file="a.dxf",
        layer="TEXTO",
        bbox=bbox,
        text=text,
        properties={"height": height},
        raw_handle=entity_id,
        evidence=EvidencePacket(
            source="a.dxf", method="test", entity_ids=[entity_id], bbox=bbox, confidence=1.0
        ),
    )


def test_section_callouts_of_two_sheets_are_two_readings():
    # Los cortes de CTA-16 en dos hojas de detalle (marcos «excluded»): una lectura por hoja,
    # nunca la mayor de las dos juntas.
    texts = []
    for dx, corte in ((0.0, "30X80"), (100.0, "30X100")):
        n = int(dx)
        texts += [
            _texto(f"m{n}", "CTA-16", dx + 2.0, 20.0, 0.12),
            _texto(f"l{n}", "SECCIÓN 1", dx + 21.0, 15.0),
            _texto(f"s{n}", corte, dx + 21.0, 14.8),
        ]
    frames = [
        SheetFrame(frame_id="a", bbox=(0.0, 0.0, 44.0, 29.4), code="ES-500", kind="excluded"),
        SheetFrame(frame_id="b", bbox=(100.0, 0.0, 144.0, 29.4), code="ES-501", kind="excluded"),
    ]
    inv = build_schedule_inventory(texts, unit_to_m=1.0, frames=frames)
    lecturas = {(s.hoja, s.metodo, s.section_cm) for s in inv.specs if s.mark == "CTA-16"}
    assert lecturas == {("ES-500", "llamada", (30, 80)), ("ES-501", "llamada", (30, 100))}
    assert any("no coinciden" in a for a in inv.by_mark["CTA-16"].avisos)


# ------------------------------------------------- Task 7, ronda 1


def _ia(mark, **campos):
    return {"mark": mark, "family": "castillo", "source": "ia", "source_text": "IA",
            "confidence": 0.5, **campos}  # fmt: skip


def _notas(tmp_path, textos, nombre="notas.dxf"):
    doc = ezdxf.new("R2010")
    msp = doc.modelspace()
    for i, texto in enumerate(textos):
        msp.add_text(texto, height=0.2).set_placement((0, i * 5.0))
    path = tmp_path / nombre
    doc.saveas(path)
    return DxfParser().parse_file(path).entities


def test_a_marked_stirrups_only_note_is_read(tmp_path):
    # Antes «K-7 E#3@20» era «sin lector» y la IA llenaba los estribos de K-7 con los suyos.
    inv = build_schedule_inventory(_notas(tmp_path, ["K-7 E#3@20", "K-7 20X30"]), frames=_frame())
    k7 = inv.by_mark["K-7"]
    assert (k7.section_cm, k7.stirrups) == ((20, 30), "E#3@20") and inv.rechazos == []
    merge_external_specs(inv, [_ia("K-7", stirrups="E#2@20")], C)
    assert inv.by_mark["K-7"].stirrups == "E#3@20"


def test_ia_never_covers_a_text_nobody_reads(tmp_path):
    # «sin lector»: el texto nombra a K-7 pero sus estribos no se leen; la IA no los cubre.
    inv = build_schedule_inventory(_notas(tmp_path, ["K-7 E#3@1S", "K-7 20X30"]), frames=_frame())
    assert [(r.motivo, r.marcas) for r in inv.rechazos] == [("sin_lector", ["K-7"])]
    merge_external_specs(inv, [_ia("K-7", stirrups="E#2@20", rebar="4#3")], C)
    k7 = inv.by_mark["K-7"]
    # R76: el texto sólo dice estribos; las varillas, que el plano no dice, las llena la IA.
    assert (k7.stirrups, k7.rebar) == (None, "4#3") and k7.section_cm == (20, 30)
    assert any("la lectura IA no lo llena" in a for a in k7.avisos)
    assert any(s.source == "ia" and s.mark == "K-7" for s in inv.specs)


def test_ia_never_covers_a_text_nobody_reads_for_a_mark_without_readings(tmp_path):
    inv = build_schedule_inventory(_notas(tmp_path, ["K-9 E#3@1S"]), frames=_frame())
    merge_external_specs(inv, [_ia("K-9", stirrups="E#2@20", section_cm=(15, 15))], C)
    k9 = inv.by_mark["K-9"]
    assert (k9.section_cm, k9.stirrups, k9.source) == ((15, 15), None, "ia")
    inv2 = build_schedule_inventory(_notas(tmp_path, ["K-9 E#3@1S"], "b.dxf"), frames=_frame())
    merge_external_specs(inv2, [_ia("K-9", stirrups="E#2@20")], C)
    assert "K-9" not in inv2.by_mark  # nada que la IA pueda decir de K-9


def test_ia_never_covers_an_ambiguous_text(tmp_path):
    # «6#4» a la misma distancia de K-1 (debajo) y de K-2 (encima): ambiguo entre las dos.
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
    assert [(r.motivo, sorted(r.marcas)) for r in inv.rechazos] == [("ambigua", ["K-1", "K-2"])]
    merge_external_specs(inv, [_ia("K-1", rebar="4#3", section_cm=(15, 15))], C)
    assert (inv.by_mark["K-1"].rebar, inv.by_mark["K-1"].section_cm) == (None, (15, 15))


@pytest.mark.parametrize(
    "etiqueta,marca_ia,marcas",
    [("K-1 Y K-2", "K-2", ["K-1", "K-2"]), ("K-1 A K-4", "K-3", ["K-1 A K-4"])],
)
def test_ia_never_covers_the_stack_of_several_marks(tmp_path, etiqueta, marca_ia, marcas):
    inv = build_schedule_inventory(
        _stack_entities(tmp_path, etiqueta, ["4#3", "E#2@15"]), frames=_frame()
    )
    assert {(r.motivo, tuple(r.marcas)) for r in inv.rechazos} == {("varias_marcas", tuple(marcas))}
    merge_external_specs(
        inv, [_ia(marca_ia, rebar="6#4", stirrups="E#2@20", section_cm=(15, 15))], C
    )
    k = inv.by_mark[marca_ia]
    assert (k.rebar, k.stirrups, k.section_cm) == (None, None, (15, 15))


@pytest.mark.parametrize(
    "nota,marcas",
    [
        ("K-1 Y K-2 15X20 4#3 E#2@20", ["K-1", "K-2"]),
        ("K-1, K-2 15X20 4#3", ["K-1", "K-2"]),
        ("K-1 A K-4 15X20 4#3", ["K-1 A K-4"]),
        ("DE K-1 A K-4 15X20 4#3", ["DE K-1 A K-4"]),
        ("K-1 A 4 15X20 4#3", ["K-1 A 4"]),
    ],
)
def test_a_note_naming_several_marks_is_reported_not_read(tmp_path, nota, marcas):
    # R63: como la pila de una etiqueta de varias marcas, la nota no se lee (antes se leía como
    # de K-1 sola, sin aviso) y sus marcas quedan cubiertas: la IA no llena lo que la nota dice.
    inv = build_schedule_inventory(_notas(tmp_path, [nota]), frames=_frame())
    assert not [s for s in inv.specs if s.mark.startswith("K-")]
    assert [(r.motivo, r.marcas, r.texto) for r in inv.rechazos] == [
        ("varias_marcas", marcas, nota)
    ]
    merge_external_specs(inv, [_ia("K-2", rebar="6#4", section_cm=(20, 20))], C)
    assert "K-2" not in inv.by_mark  # sección y armado: los dice la nota


def test_two_frames_with_the_same_code_are_two_sheets(tmp_path):
    def build(msp):
        msp.add_text("K-9 20X40", height=0.2).set_placement((0, 0))
        msp.add_text("K-9 4#3", height=0.2).set_placement((100, 0))

    frames = [
        SheetFrame(frame_id="a", bbox=(-50.0, -50.0, 50.0, 50.0), code="ES-200"),
        SheetFrame(frame_id="b", bbox=(50.0, -50.0, 150.0, 50.0), code="ES-200"),
    ]
    inv = build_schedule_inventory(_entities(tmp_path, build), frames=frames)
    lecturas = [s for s in inv.specs if s.mark == "K-9"]
    assert {s.hoja for s in lecturas} == {"ES-200"} and len({s.hoja_llave for s in lecturas}) == 2
    assert inv.by_mark["K-9"].rebar is None  # otra hoja, aunque se llame igual: no se junta


def test_two_files_without_frames_are_two_sheets(tmp_path):
    ents = _notas(tmp_path, ["K-9 20X40"], "a.dxf") + _notas(tmp_path, ["K-9 4#3"], "b.dxf")
    inv = build_schedule_inventory(ents)
    assert len({s.hoja for s in inv.specs if s.mark == "K-9"}) == 2
    assert (inv.by_mark["K-9"].section_cm, inv.by_mark["K-9"].rebar) == ((20, 40), None)


def test_tables_found_counts_cuadros(tmp_path):
    def build(msp):
        for y0 in (0.0, 20.0):
            for col, title in enumerate(["MARCA", "SECCION", "ARMADO", "ESTRIBOS"]):
                msp.add_text(title, height=0.25).set_placement((col * 3, y0 + 10))
            marca = "K-1" if y0 == 0.0 else "K-2"
            for col, value in enumerate([marca, "15x20", "4#3", "E#2@20"]):
                msp.add_text(value, height=0.25).set_placement((col * 3, y0 + 9.5))

    inv = build_schedule_inventory(_entities(tmp_path, build), frames=_frame())
    assert inv.tables_found == 2  # dos cuadros en una sola hoja
    assert "2 cuadro(s) de elementos leído(s) del plano (2 fila(s))." in inv.notes


def test_every_bar_group_reaches_the_variant_key(tmp_path):
    # De la pila a la firma de la variante: «4#5+2#4» entero (antes llegaba «4#5»).
    ents = _stack_entities(tmp_path, "K-6", ["20x30 4#5+2#4", "2E#3@15"])
    inv = build_schedule_inventory(ents)
    tag = make_detection("d1", DetectionType.column_tag, "K-6", (0, 0, 1, 1), 0.8, [], "m", [])
    assert apply_schedule([tag], inv, meters_factor=1.0) == 1
    assert tag.properties["spec_rebar"] == "4#5+2#4"
    assert firma(tag, 1.0)["armado"] == "4#5+2#4"


# ------------------------------------------------- Task 7, ronda 2 (R64): la IA, desde el texto


@pytest.mark.parametrize("nota,marca", [("TRABE T-1 E#3@1S", "T-1"), ("3.- K-7 E#3@1S", "K-7")])
def test_ia_never_covers_a_text_that_names_its_mark_whatever_its_class(tmp_path, nota, marca):
    # Una nota de otra familia («ajena») o numerada que nombra la marca y nadie lee: antes no
    # dejaba rechazo y la IA llenaba la marca.
    inv = build_schedule_inventory(_notas(tmp_path, [nota]), frames=_frame())
    assert [(t.entidad_id != "", t.marcas) for t in inv.textos_con_marca] == [(True, [marca])]
    merge_external_specs(inv, [_ia(marca, stirrups="E#2@20", rebar="6#4")], C)
    assert inv.by_mark[marca].stirrups is None  # R76: lo que el texto dice (estribos), no más


def test_ia_never_covers_a_glued_mark(tmp_path):
    # «K-7E#3@20»: la marca pegada es K-7 (la marca conocida más larga con que empieza).
    inv = build_schedule_inventory(_notas(tmp_path, ["K-7E#3@20", "K-7 20X30"]), frames=_frame())
    merge_external_specs(inv, [_ia("K-7", stirrups="E#2@20", rebar="6#4")], C)
    k7 = inv.by_mark["K-7"]
    assert (k7.section_cm, k7.stirrups, k7.rebar) == ((20, 30), None, "6#4")  # R76
    # Sin otra lectura de K-7, la marca la conoce la propia IA.
    inv2 = build_schedule_inventory(_notas(tmp_path, ["K-7E#3@20"], "b.dxf"), frames=_frame())
    merge_external_specs(inv2, [_ia("K-7", stirrups="E#2@20")], C)
    assert "K-7" not in inv2.by_mark


def test_a_glued_form_is_never_a_shorter_mark(tmp_path):
    # «K-15AE#3@20» no es de K-1 (lo que sobra, «5AE», no empieza con letra).
    inv = build_schedule_inventory(_notas(tmp_path, ["K-15AE#3@20"]), frames=_frame())
    merge_external_specs(inv, [_ia("K-1", stirrups="E#2@20"), _ia("K-15A", stirrups="E#2@20")], C)
    assert inv.by_mark["K-1"].stirrups == "E#2@20" and "K-15A" not in inv.by_mark


def test_ia_never_covers_the_endpoints_of_a_mixed_letter_range(tmp_path):
    inv = build_schedule_inventory(_notas(tmp_path, ["K-1 A C-4 15X20 4#3"]), frames=_frame())
    merge_external_specs(
        inv, [_ia(m, rebar="6#4", section_cm=(20, 20)) for m in ("K-1", "C-4", "K-2", "C-2")], C
    )
    assert "K-1" not in inv.by_mark and "C-4" not in inv.by_mark
    # Entre letras distintas no se sabe qué hay en medio: sólo los extremos quedan cubiertos.
    assert inv.by_mark["K-2"].rebar == "6#4" and inv.by_mark["C-2"].rebar == "6#4"


def test_a_text_read_by_the_mark_does_not_block_it_nor_an_unrelated_mark(tmp_path):
    inv = build_schedule_inventory(_notas(tmp_path, ["K-7 4#3"]), frames=_frame())
    merge_external_specs(inv, [_ia("K-7", stirrups="E#2@20"), _ia("K-8", rebar="6#4")], C)
    assert inv.by_mark["K-7"].stirrups == "E#2@20"  # «K-7 4#3» lo leyó K-7 y no dice estribos
    assert inv.by_mark["K-8"].rebar == "6#4"


def test_two_sheets_sharing_a_code_are_named_apart_in_an_aviso(tmp_path):
    def build(msp):
        msp.add_text("K-9 20X40", height=0.2).set_placement((0, 0))
        msp.add_text("K-9 20X30", height=0.2).set_placement((100, 0))

    frames = [
        SheetFrame(frame_id="a", bbox=(-50.0, -50.0, 50.0, 50.0), code="ES-200"),
        SheetFrame(frame_id="b", bbox=(50.0, -50.0, 150.0, 50.0), code="ES-200"),
    ]
    inv = build_schedule_inventory(_entities(tmp_path, build), frames=frames)
    (aviso,) = [a for a in inv.by_mark["K-9"].avisos if "no coinciden" in a]
    assert "ES-200 [a de specs.dxf]" in aviso and "ES-200 [b de specs.dxf]" in aviso


# --------------------------------------- Task 7, ronda 3 (R65): un reconocedor, llave suelta


@pytest.mark.parametrize(
    "nota,marcas",
    [
        ("TRABE T 1 E#3@1S", ["T-1"]),
        ("TRABE T - 1 E#3@1S", ["T-1"]),
        ("3.- K 7 E#3@1S", ["K-7"]),
        ("TRABE:T-1 E#3@1S", ["T-1"]),
        ("TRABE T-1=T-2 E#3@1S", ["T-1", "T-2"]),
        ("TRABE T-1+T-2 E#3@1S", ["T-1", "T-2"]),
        ("TRABE T-1&T-2 E#3@1S", ["T-1", "T-2"]),
    ],
)
def test_one_recogniser_for_the_ia_block(tmp_path, nota, marcas):
    # R65.1: lo que ``marcas_en_nota`` reconoce también cubre (antes la IA llenaba esas marcas;
    # con «T-1=T-2», T-2 se resolvía pegada a T-1).
    inv = build_schedule_inventory(_notas(tmp_path, [nota]), frames=_frame())
    merge_external_specs(inv, [_ia(m, stirrups="E#2@20", rebar="6#4") for m in marcas], C)
    assert not [m for m in marcas if inv.by_mark[m].stirrups is not None]  # R76: sólo estribos


@pytest.mark.parametrize("nota,marca_ia", [("TRABE K7E#3@1S", "K7"), ("TRABE T1-1E#3@1S", "T1-1")])
def test_a_glued_mark_written_without_hyphen_is_blocked(tmp_path, nota, marca_ia):
    # R65.3 (sonda G1b): la ficha pegada se guarda tal cual y con guion, y se compara con las
    # marcas conocidas por su llave suelta.
    inv = build_schedule_inventory(_notas(tmp_path, [nota]), frames=_frame())
    merge_external_specs(inv, [_ia(marca_ia, stirrups="E#9@25")], C)
    assert marca_ia not in inv.by_mark


def test_an_ia_mark_written_differently_still_meets_the_drawing_mark(tmp_path):
    # R65.2: el plano dice «K-7», la IA «K7»: es la misma marca para el bloqueo (nunca para
    # juntar lecturas ni la vista por marca).
    inv = build_schedule_inventory(_notas(tmp_path, ["K-7 E#3@1S", "K-7 20X30"]), frames=_frame())
    merge_external_specs(inv, [_ia("K7", stirrups="E#2@20", section_cm=(15, 15))], C)
    assert "K7" not in inv.by_mark and inv.by_mark["K-7"].stirrups is None


def test_the_loose_key_never_reaches_a_different_mark(tmp_path):
    # Controles: «K-15E#3@20» no es de K-1; «K-7 4#3», leído por K-7, no le tapa sus estribos a
    # la IA de «K7»; una marca sin relación no queda cubierta.
    inv = build_schedule_inventory(_notas(tmp_path, ["K-15E#3@20", "K-7 4#3"]), frames=_frame())
    merge_external_specs(
        inv,
        [
            _ia("K-1", stirrups="E#2@20"),
            _ia("K-15", stirrups="E#2@20"),
            _ia("K7", stirrups="E#2@20"),
            _ia("K-8", rebar="6#4"),
        ],
        C,
    )
    assert inv.by_mark["K-1"].stirrups == "E#2@20" and "K-15" not in inv.by_mark
    assert inv.by_mark["K7"].stirrups == "E#2@20" and inv.by_mark["K-7"].rebar == "4#3"
    assert inv.by_mark["K-8"].rebar == "6#4"


# --------------------------------------- Task 7, ronda 4 (R66): prefijos, rangos pegados, T1-1


def test_a_glued_token_blocks_every_known_prefix(tmp_path):
    # Sonda U6d: una marca de la IA más larga («K7E») no le quita a K-7 el texto pegado; antes la
    # IA escribía 9#9 y E#9@99 en K-7.
    inv = build_schedule_inventory(_notas(tmp_path, ["K-7E#3@20", "K-7 20X30"]), frames=_frame())
    merge_external_specs(
        inv,
        [_ia("K-7", rebar="9#9", stirrups="E#9@99"), _ia("K7E", rebar="9#9", stirrups="E#9@99")],
        C,
    )
    k7 = inv.by_mark["K-7"]
    # R76: «K-7E#3@20» dice estribos; las varillas, que nadie escribió, las llena la IA.
    assert (k7.rebar, k7.stirrups, k7.section_cm) == ("9#9", None, (20, 30))
    assert inv.by_mark["K7E"].stirrups is None


def test_a_glued_token_without_hyphen_blocks_every_known_prefix(tmp_path):
    inv = build_schedule_inventory(_notas(tmp_path, ["TRABE K7E#3@1S"]), frames=_frame())
    merge_external_specs(inv, [_ia("K7", stirrups="E#9@99"), _ia("K7E", stirrups="E#9@99")], C)
    assert "K7" not in inv.by_mark and "K7E" not in inv.by_mark


@pytest.mark.parametrize(
    "nota,cubiertas,libres",
    [
        ("K-1-K-3 E#3@1S", ["K-1", "K-2", "K-3"], ["K-4"]),
        ("K-1–K-3 E#3@1S", ["K-1", "K-2", "K-3"], ["K-4"]),
        ("K-1—K-3 E#3@1S", ["K-1", "K-2", "K-3"], ["K-4"]),
        ("TRABE T-1-T-2 E#3@1S", ["T-1", "T-2"], ["T-3"]),
    ],
)
def test_a_range_written_without_spaces_is_a_range(tmp_path, nota, cubiertas, libres):
    inv = build_schedule_inventory(_notas(tmp_path, [nota]), frames=_frame())
    merge_external_specs(inv, [_ia(m, stirrups="E#9@99") for m in cubiertas + libres], C)
    assert not [m for m in cubiertas if m in inv.by_mark]
    assert all(inv.by_mark[m].stirrups == "E#9@99" for m in libres)


@pytest.mark.parametrize(
    "nota,rango",
    [
        ("K-1-K-3 15X20 4#3", "K-1-K-3"),
        ("K-1–K-3 15X20 4#3", "K-1–K-3"),
        ("T-1-T-2 20X40 2#6", "T-1-T-2"),
    ],
)
def test_the_note_reader_reports_an_unspaced_range(tmp_path, nota, rango):
    # R66.b: nunca se lee como de K-1 (ni de una marca «K-1-K» con sufijo).
    inv = build_schedule_inventory(_notas(tmp_path, [nota]), frames=_frame())
    assert [s.mark for s in inv.specs] == []
    assert [(r.motivo, r.marcas) for r in inv.rechazos] == [("varias_marcas", [rango])]


@pytest.mark.parametrize("nota,marca", [("T1-1 4#3", "T1-1"), ("K-1-A 4#3", "K-1-A")])
def test_a_single_mark_is_never_a_range(tmp_path, nota, marca):
    # R66.c: «T1-1 4#3» es de T1-1 (antes caía en «T1»); «K-1-A» es una sola marca, la suya (R67:
    # antes se leía como de K-1).
    inv = build_schedule_inventory(_notas(tmp_path, [nota]), frames=_frame())
    assert [s.mark for s in inv.specs] == [marca] and inv.rechazos == []
    assert inv.by_mark[marca].rebar == "4#3"


def test_an_ia_mark_written_with_a_unicode_dash_meets_the_drawing_mark(tmp_path):
    inv = build_schedule_inventory(_notas(tmp_path, ["K-7 E#3@1S", "K-7 20X30"]), frames=_frame())
    merge_external_specs(inv, [_ia("K–7", stirrups="E#2@20"), _ia("K‑7", section_cm=(15, 15))], C)
    assert "K–7" not in inv.by_mark and "K‑7" not in inv.by_mark


# --------------------------------------- Task 7, ronda 5 (R67): una sola gramática de marcas


def _sin_fantasmas(inv, *fantasmas):
    return not [s for s in inv.specs if s.mark in fantasmas]


def test_a_section_glued_to_a_mark_is_not_a_phantom_mark(tmp_path):
    # «T2-20X40»: ni la marca «T2-20X» ni T2 la leen; T2 y T2-20 quedan cubiertas.
    inv = build_schedule_inventory(_notas(tmp_path, ["T2-20X40", "T2 4#3"]), frames=_frame())
    assert _sin_fantasmas(inv, "T2-20X", "T2-20")
    assert inv.by_mark["T2"].section_cm is None and inv.by_mark["T2"].rebar == "4#3"
    assert [(r.motivo, r.marcas) for r in inv.rechazos] == [("sin_lector", ["T2", "T2-20"])]
    merge_external_specs(inv, [_ia("T2", section_cm=(99, 99))], C)
    assert inv.by_mark["T2"].section_cm is None


@pytest.mark.parametrize(
    "nota,fantasma,marca",
    [
        ("T2-15E#3@15 20X40", "T2-15E", "T2"),
        ("T1-4#3 E#2@20", "T1-4", "T1"),
        ("K-7E#3@20 15X20", "K-7E", "K-7"),
        ("T1-1E#3@20 20X40", "T1-1E", "T1-1"),
    ],
)
def test_a_glued_mark_is_never_read(tmp_path, nota, fantasma, marca):
    inv = build_schedule_inventory(_notas(tmp_path, [nota]), frames=_frame())
    assert _sin_fantasmas(inv, fantasma, marca)
    assert inv.rechazos[0].motivo == "sin_lector" and marca in inv.rechazos[0].marcas
    merge_external_specs(inv, [_ia(marca, stirrups="E#9@99", section_cm=(99, 99))], C)
    k = inv.by_mark.get(marca)
    # Lo que la nota dice (armado y, si la trae, la sección) no lo llena la IA.
    assert k is None or (k.stirrups is None and ("X" in nota) == (k.section_cm is None))


def test_a_mark_followed_by_a_number_is_a_range_candidate(tmp_path):
    # «K-1-3 4#3»: ni de K-1 ni de nadie; K-1, K-2 y K-3 quedan cubiertas.
    inv = build_schedule_inventory(_notas(tmp_path, ["K-1-3 4#3"]), frames=_frame())
    assert inv.specs == []
    merge_external_specs(inv, [_ia(m, rebar="9#9") for m in ("K-1", "K-2", "K-3", "K-4")], C)
    assert [m for m in ("K-1", "K-2", "K-3") if m in inv.by_mark] == []
    assert inv.by_mark["K-4"].rebar == "9#9"


def test_a_letter_variant_then_a_mark_is_a_range(tmp_path):
    inv = build_schedule_inventory(_notas(tmp_path, ["K-1-A-K-3 4#3"]), frames=_frame())
    assert inv.specs == [] and [(r.motivo, r.marcas) for r in inv.rechazos] == [
        ("varias_marcas", ["K-1-A-K-3"])
    ]
    merge_external_specs(inv, [_ia("K-2", rebar="9#9")], C)
    assert "K-2" not in inv.by_mark


@pytest.mark.parametrize(
    "nota,cubierta",
    [("T1-1 A T1-3 4#3", "T1-2"), ("T1-1-T1-3 4#3", "T1-2"), ("T1-1 A 3 4#3", "T1-3")],
)
def test_ranges_of_compound_marks(tmp_path, nota, cubierta):
    inv = build_schedule_inventory(_notas(tmp_path, [nota]), frames=_frame())
    merge_external_specs(inv, [_ia(cubierta, rebar="9#9"), _ia("T-3", rebar="9#9")], C)
    assert cubierta not in inv.by_mark
    assert inv.by_mark["T-3"].rebar == "9#9"  # «T1-1 A 3» es T1-3, nunca T-3


@pytest.mark.parametrize(
    "nota,cubierta,cuenta",
    [
        ("P-5-P 4#3", "P-5", "P-4"),
        ("T-1-T 4#3", "T-1", "T-4"),
        ("C-1-P 4#3", "C-1", "P-4"),
        ("K-1-CE 4#3", "K-1", "CE-4"),
    ],
)
def test_a_bar_count_is_never_a_mark(tmp_path, nota, cubierta, cuenta):
    inv = build_schedule_inventory(_notas(tmp_path, [nota]), frames=_frame())
    assert inv.specs == []
    merge_external_specs(inv, [_ia(cubierta, rebar="9#9"), _ia(cuenta, rebar="9#9")], C)
    assert cubierta not in inv.by_mark and inv.by_mark[cuenta].rebar == "9#9"


def test_a_note_reaches_the_element_of_its_label(tmp_path):
    # Misma llave que la etiqueta: «K15A» como se escribe; la lectura llega a su elemento.
    inv = build_schedule_inventory(_notas(tmp_path, ["K15A 15X15 4#3"]), frames=_frame())
    tag = make_detection("d1", DetectionType.column_tag, "K15A", (0, 0, 1, 1), 0.8, [], "m", [])
    assert apply_schedule([tag], inv, meters_factor=1.0) == 1
    assert (tag.properties["section_cm"], tag.properties["spec_rebar"]) == ("15x15", "4#3")


# ------------------------------------- Tarea 8, paso A (R68): la gramática cerrada y el respaldo


def _ia_lleno(inv, marca):
    """Lo que la IA llenó de ``marca`` en la vista por marca (vacío si nada)."""
    k = inv.by_mark.get(marca)
    if k is None:
        return {}
    campos = ("section_cm", "rebar", "stirrups")
    return {c: getattr(k, c) for c in campos if getattr(k, c) is not None and k.source == "ia"}


@pytest.mark.parametrize(
    "nota,marca_ia",
    [
        ("K-7 E#3@1S", "K-07"),  # ceros a la izquierda: K-07 es K-7 para el bloqueo
        ("TRABE V 1 E#3@1S", "V-1"),  # una etiqueta escrita con espacio, que la gramática no ve
        ("TRABE TL 1 E#3@1S", "TL-1"),
        ("CORTE K-1 15X20 4#3", "K-1"),  # R68.8: la referencia se traga su única marca
        ("DET. K-1 4#3", "K-1"),
    ],
)
def test_the_backstop_blocks_what_the_grammar_misses(tmp_path, nota, marca_ia):
    # R68.1: el respaldo no depende de la gramática; todo hueco de ésta queda «bloqueado y
    # avisado», nunca lo llena la IA. Lo que el texto dice, campo por campo (R76).
    inv = build_schedule_inventory(_notas(tmp_path, [nota]), frames=_frame())
    merge_external_specs(
        inv, [_ia(marca_ia, rebar="9#9", stirrups="E#9@99", section_cm=(99, 99))], C
    )
    k = inv.by_mark.get(marca_ia)
    dice = {"rebar": "4#3" in nota, "stirrups": "E#" in nota, "section_cm": "X" in nota}
    assert k is None or all((getattr(k, c) is None) == d for c, d in dice.items())


@pytest.mark.parametrize(
    "nota,marca_ia",
    [
        ("K-70 4#3", "K-7"),  # otra marca, más larga
        ("K-15E#3@20", "K-1"),
        ("K-15AE#3@20", "K-1"),
        ("K-1.1 4#3", "K-1"),
        ("TE ARMADO #4@20", "TE-A"),  # una palabra, no la marca TE-A
        ("P 4#3", "P-4"),  # una cuenta de varillas
        ("K 7#3", "K-7"),
        ("K-7 4#3 15X20", "K-1"),
    ],
)
def test_the_backstop_never_reaches_a_different_mark(tmp_path, nota, marca_ia):
    inv = build_schedule_inventory(_notas(tmp_path, [nota]), frames=_frame())
    merge_external_specs(inv, [_ia(marca_ia, stirrups="E#9@99")], C)
    assert inv.by_mark[marca_ia].stirrups == "E#9@99"


def test_the_backstop_spares_a_text_the_mark_itself_read(tmp_path):
    # La excepción de siempre: «K-7 4#3» lo leyó K-7 y no dice estribos; la IA los llena. K-8 no
    # tiene nada que ver.
    inv = build_schedule_inventory(_notas(tmp_path, ["K-7 4#3"]), frames=_frame())
    merge_external_specs(inv, [_ia("K-7", stirrups="E#2@20"), _ia("K-8", rebar="6#4")], C)
    assert inv.by_mark["K-7"].stirrups == "E#2@20" and inv.by_mark["K-8"].rebar == "6#4"


def test_a_bar_count_in_a_stack_stays_its_marks(tmp_path):
    # R68.2: «V4 #4» es una cuenta de varillas, no la etiqueta V4; la pila es de CR-1, como en
    # 700ffe0, y la IA no le llena las varillas.
    inv = build_schedule_inventory(
        _stack_entities(tmp_path, "CR-1", ["V4 #4", "E#3 @20CMS"]), frames=_frame()
    )
    cr1 = inv.by_mark["CR-1"]
    assert (cr1.rebar, cr1.stirrups, cr1.metodo) == ("4#4", "E#3@20", "pila")
    assert not [s for s in inv.specs if s.mark == "V4"] and inv.rechazos == []
    merge_external_specs(inv, [_ia("CR-1", rebar="9#9"), _ia("V4", stirrups="E#9@99")], C)
    assert inv.by_mark["CR-1"].rebar == "4#4"
    assert inv.by_mark["V4"].stirrups == "E#9@99"  # una cuenta nunca cubre a una marca


@pytest.mark.parametrize(
    "nota,marca,longitudinales,estribos",
    [
        ("CR-1 V4 #4 E#3 @20CMS", "CR-1", "4#4", "E#3@20"),  # no son varias marcas
        ("V-1 4#4", "V-1", "4#4", None),  # sin «#» tras el número, V-1 es la marca
    ],
)
def test_a_bar_count_is_not_a_second_mark(tmp_path, nota, marca, longitudinales, estribos):
    inv = build_schedule_inventory(_notas(tmp_path, [nota]), frames=_frame())
    assert [s.mark for s in inv.specs] == [marca] and inv.rechazos == []
    assert (inv.by_mark[marca].rebar, inv.by_mark[marca].stirrups) == (longitudinales, estribos)


@pytest.mark.parametrize("nota", ["V12 #5 E#3 @20CMS", "V4 #4", "V12 #5"])
def test_a_bar_count_alone_names_no_mark(tmp_path, nota):
    inv = build_schedule_inventory(_notas(tmp_path, [nota]), frames=_frame())
    assert [s.mark for s in inv.specs if s.mark.startswith("V")] == []


def test_a_family_note_with_a_bar_count_is_the_familys(tmp_path):
    inv = build_schedule_inventory(_notas(tmp_path, ["DALA 15X20 V4 #4 E#2@20"]), frames=_frame())
    assert [(s.mark, s.rebar, s.stirrups) for s in inv.specs] == [("DALA", "4#4", "E#2@20")]


@pytest.mark.parametrize(
    "nota,marca,seccion",
    [
        ("3.-K 7 15X20 4#3", "K-7", (15, 20)),  # R68.3: leída como en 700ffe0
        ("1.-K 7 15X20", "K-7", (15, 20)),
        ('"K 7" 15X20', "K-7", (15, 20)),
    ],
)
def test_a_spaced_mark_after_any_non_letter_is_read(tmp_path, nota, marca, seccion):
    inv = build_schedule_inventory(_notas(tmp_path, [nota]), frames=_frame())
    assert [(s.mark, s.section_cm) for s in inv.specs] == [(marca, seccion)]


@pytest.mark.parametrize(
    "nota,marcas",
    [
        ("1.-K 7 E#3@1S", ["K-7"]),
        ('"K 7" E#3@1S', ["K-7"]),
        ("TRABE-T 1 E#3@1S", ["T-1"]),  # de otra familia: no es rechazo, pero nombra a T-1
        ("K-1/K 7 E#3@1S", ["K-1", "K-7"]),
    ],
)
def test_a_spaced_mark_after_any_non_letter_is_blocked(tmp_path, nota, marcas):
    inv = build_schedule_inventory(_notas(tmp_path, [nota]), frames=_frame())
    assert [t.marcas for t in inv.textos_con_marca] == [marcas]
    merge_external_specs(inv, [_ia(m, stirrups="E#9@99") for m in marcas], C)
    assert not [m for m in marcas if m in inv.by_mark]


@pytest.mark.parametrize(
    "notas,marca_ia,campos",
    [
        (["TL-1E#3@20 20X40", "TL-1 4#3"], "TL-1", ("stirrups", "section_cm")),  # R68.4
        (["V-1E#3@20 20X40", "V-1 4#4"], "V-1", ("stirrups", "section_cm")),
        (["K-7-E #3@20 15X20"], "K-7", ("stirrups", "section_cm")),  # R68.5
        (["T-1-E #3@20 20X40"], "T-1", ("stirrups", "section_cm")),
        (["K-7E #3@20"], "K-7", ("stirrups",)),  # sin guion, lo mismo
    ],
)
def test_a_glued_or_headed_mark_is_ambiguous_and_blocked(tmp_path, notas, marca_ia, campos):
    inv = build_schedule_inventory(_notas(tmp_path, notas), frames=_frame())
    (rechazo,) = inv.rechazos
    assert rechazo.motivo == "sin_lector" and marca_ia in rechazo.marcas
    assert not [s for s in inv.specs if s.mark in rechazo.marcas and s.mark != marca_ia]
    merge_external_specs(
        inv, [_ia(marca_ia, stirrups="E#9@99", section_cm=(99, 99), rebar="9#9")], C
    )
    k = inv.by_mark.get(marca_ia)
    assert k is None or all(getattr(k, c) is None for c in campos)


def test_a_letter_variant_without_a_stirrup_after_it_is_its_mark(tmp_path):
    inv = build_schedule_inventory(_notas(tmp_path, ["K-1-E 4#3"]), frames=_frame())
    assert [s.mark for s in inv.specs] == ["K-1-E"] and inv.rechazos == []


@pytest.mark.parametrize(
    "nota,marcas,libre",
    [
        ("K-1, 2 Y 3 15X20 4#3", ["K-1", "K-2", "K-3"], "K-4"),  # R68.6
        ("K-1 Y 2 15X20 4#3", ["K-1", "K-2"], "K-3"),
        ("T1-1 Y 2 4#3", ["T1-1", "T1-2"], "T1-3"),
        ("K-1 Y K–2 4#3", ["K-1", "K-2"], "K-3"),  # R68.7
    ],
)
def test_a_shorthand_list_is_several_marks(tmp_path, nota, marcas, libre):
    inv = build_schedule_inventory(_notas(tmp_path, [nota]), frames=_frame())
    assert inv.specs == []
    assert [(r.motivo, r.marcas) for r in inv.rechazos] == [("varias_marcas", marcas)]
    merge_external_specs(inv, [_ia(m, rebar="9#9") for m in [*marcas, libre]], C)
    assert not [m for m in marcas if m in inv.by_mark] and inv.by_mark[libre].rebar == "9#9"


def test_a_unicode_dash_in_a_drawing_mark_is_a_hyphen(tmp_path):
    inv = build_schedule_inventory(_notas(tmp_path, ["K–7 4#3"]), frames=_frame())
    assert [(s.mark, s.rebar) for s in inv.specs] == [("K-7", "4#3")]


def test_a_title_is_not_a_stack_line_of_another_mark(tmp_path):
    # R68.8: «CORTE K-1 15X20 4#3» bajo la etiqueta de K-2 no es de K-2 (antes la pila de K-2
    # lo leía): dice de quién es y nadie lo lee.
    inv = build_schedule_inventory(
        _stack_entities(tmp_path, "K-2", ["CORTE K-1 15X20 4#3"]), frames=_frame()
    )
    assert not [s for s in inv.specs if s.mark == "K-2"]
    assert [(r.motivo, r.marcas) for r in inv.rechazos] == [("sin_lector", ["K-1"])]


def test_merge_takes_the_projects_config():
    # R68.9: sin configuración por omisión callada; las marcas se reconocen con las del proyecto.
    import inspect

    assert inspect.signature(merge_external_specs).parameters["config"].default is (
        inspect.Parameter.empty
    )


# ----------------------------------- Tarea 8, paso B (R69): el bloqueo viaja con la lectura IA


def test_the_ai_reading_carries_its_block(tmp_path):
    # «K-7 E#3@1S» (sin lector) bloquea los estribos de la IA; la lectura IA se guarda con todos
    # sus campos y dice cuál no puede elegirse y por qué texto.
    inv = build_schedule_inventory(_notas(tmp_path, ["K-7 E#3@1S"]), frames=_frame())
    merge_external_specs(inv, [_ia("K-7", stirrups="E#2@20", section_cm=(15, 15))], C)
    (ia,) = [s for s in inv.specs if s.source == "ia"]
    assert (ia.stirrups, ia.section_cm) == ("E#2@20", (15, 15))  # se guarda entera
    assert ia.campos_bloqueados == ["estribos"]
    assert {(b.campo, b.texto, b.fuente) for b in ia.bloqueos} == {
        ("estribos", "K-7 E#3@1S", "nota")
    }
    assert {b.por for b in ia.bloqueos} <= {"texto", "rechazo", "respaldo"}
    # Y viaja en schedules.json.
    otra = type(inv).model_validate_json(inv.model_dump_json())
    assert [s.campos_bloqueados for s in otra.specs if s.source == "ia"] == [["estribos"]]


def test_a_block_by_a_reading_names_the_reading(tmp_path):
    inv = build_schedule_inventory(
        _stack_entities(tmp_path, "K-4", ["6#4", "EYG#3@1S"]), frames=_frame()
    )
    merge_external_specs(inv, [_ia("K-4", stirrups="EYG#2@15", rebar="9#9")], C)
    (ia,) = [s for s in inv.specs if s.source == "ia"]
    assert ia.campos_bloqueados == ["longitudinales", "estribos"]
    assert {(b.campo, b.por, b.fuente, b.hoja) for b in ia.bloqueos} == {
        ("longitudinales", "lectura", "detalle", "ES-400"),
        ("estribos", "lectura", "detalle", "ES-400"),
    }


def test_a_stack_line_rejection_blocks_from_the_detail(tmp_path):
    # «6#4» a la misma distancia de K-1 y de K-2: un renglón de pila ambiguo, del detalle.
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
    (ia,) = [s for s in inv.specs if s.source == "ia"]
    assert [(b.campo, b.por, b.fuente, b.texto) for b in ia.bloqueos] == [
        ("longitudinales", "rechazo", "detalle", "6#4")
    ]


def test_an_unblocked_ai_reading_carries_no_block(tmp_path):
    inv = build_schedule_inventory(_notas(tmp_path, ["K-7 4#3"]), frames=_frame())
    merge_external_specs(inv, [_ia("K-7", stirrups="E#2@20"), _ia("K-8", rebar="6#4")], C)
    assert all(s.campos_bloqueados == [] and s.bloqueos == [] for s in inv.specs)
    assert all(s.campos_bloqueados == [] for s in inv.by_mark.values())


# --------------------------------------------------- Tarea 8, ronda 1 (R76–R80)


@pytest.mark.parametrize(
    "nota,marcas_ia",
    [
        ("K-15 A 4#3 E#3@20", ["K-15A", "K-15-A", "K-15"]),  # R78
        ("K-1 A 4#3 E#3@20", ["K-1A", "K-1-A", "K-1"]),
    ],
)
def test_a_spaced_suffix_is_ambiguous_and_blocks_every_reading(tmp_path, nota, marcas_ia):
    inv = build_schedule_inventory(_notas(tmp_path, [nota]), frames=_frame())
    assert inv.specs == [] and inv.rechazos[0].motivo == "sin_lector"
    merge_external_specs(inv, [_ia(m, rebar="9#9", stirrups="E#9@99") for m in marcas_ia], C)
    assert not [m for m in marcas_ia if m in inv.by_mark]


@pytest.mark.parametrize(
    "nota,marca_ia", [("K-15 ARMADO #3", "K-15A"), ("TE ARMADO #4@20", "TE-A")]
)
def test_a_word_after_a_mark_is_not_its_suffix(tmp_path, nota, marca_ia):
    inv = build_schedule_inventory(_notas(tmp_path, [nota]), frames=_frame())
    merge_external_specs(inv, [_ia(marca_ia, stirrups="E#9@99")], C)
    assert inv.by_mark[marca_ia].stirrups == "E#9@99"


@pytest.mark.parametrize(
    "nota,marca",
    [("TRABE TL 1 20X40 4#3", "TL-1"), ("TRABE TE A 20X40 E#3@20", "TE-A")],
)
def test_a_family_word_text_naming_a_spaced_tag_is_that_marks(tmp_path, nota, marca):
    # R79: antes era la nota de la familia «trabe».
    inv = build_schedule_inventory(_notas(tmp_path, [nota]), frames=_frame())
    assert [s.mark for s in inv.specs] == [marca] and "trabe" not in inv.by_family


def test_a_family_note_that_names_a_mark_is_not_the_familys(tmp_path):
    # R79: «CORTE K-1 CASTILLOS 15X20 4#3» nombra a K-1 (título): no es la nota de los castillos.
    inv = build_schedule_inventory(
        _notas(tmp_path, ["CORTE K-1 CASTILLOS 15X20 4#3", "CASTILLOS 15X15 4#3"]),
        frames=_frame(),
    )
    assert [s.source_text for s in inv.specs] == ["CASTILLOS 15X15 4#3"]
    assert [(r.motivo, r.marcas) for r in inv.rechazos] == [("sin_lector", ["K-1"])]


@pytest.mark.parametrize("nota", ["3.- K-7 E#3@1S", "TRABE-T 1 E#3@1S"])
def test_a_numbered_or_other_family_text_naming_a_mark_is_rejected(tmp_path, nota):
    # R77: antes nadie lo reportaba (nota numerada, texto de otra familia).
    inv = build_schedule_inventory(_notas(tmp_path, [nota]), frames=_frame())
    assert [r.motivo for r in inv.rechazos] == ["sin_lector"] and inv.rechazos[0].marcas


def test_an_unreadable_castillo_mesh_claims_parrillas_and_stirrups(tmp_path):
    # R95: «K-7 #3@1S» es una malla, aunque un castillo no las lleve: reclama parrillas (el campo
    # queda bloqueado y el texto avisado). Sin cabeza puede ser también sus estribos (R76): los
    # dos. Las varillas no: el texto no las dice.
    inv = build_schedule_inventory(_notas(tmp_path, ["K-7 #3@1S"]), frames=_frame())
    merge_external_specs(inv, [_ia("K-7", mesh="#4@20", stirrups="E#2@20", rebar="4#3")], C)
    k7 = inv.by_mark["K-7"]
    assert (k7.mesh, k7.stirrups, k7.rebar) == (None, None, "4#3")


def test_fragment_lines_are_kept_by_sheet_and_only_with_a_letter(tmp_path):
    # R80: un renglón sin letras no nombra marcas; la llave de la hoja se guarda una vez.
    inv = build_schedule_inventory(
        _stack_entities(tmp_path, "K-4", ["6#4", "EYG#3@15"], loose=[("@20", 9.0, 9.0)]),
        frames=_frame(),
    )
    (hoja,) = inv.textos_con_fragmento
    assert hoja.hoja == "ES-400" and [x.texto for x in hoja.lineas] == ["EYG#3@15"]
    assert hoja.lineas[0].campos == ["estribos"]


# --------------------------------------------------- Tarea 8, ronda 2 (R86–R89)


@pytest.mark.parametrize(
    "nota,estribos",
    [
        ('K-1 15X15 4 VARS 5/16" E 1/4 @ 15', "E#2@15"),  # «5/16"» nadie la reconoce
        ("K-1 15X15 4 VARS DE 3 E#2@15", None),  # nada se lee: todo queda reclamado
    ],
)
def test_an_unrecognised_digit_claims_every_field_of_the_family(tmp_path, nota, estribos):
    # R86: no se estrecha lo que reclama un texto mientras quede una cifra sin reconocer: la IA
    # (6#4, E#3@10) no llena nada de lo que el texto podría decir.
    inv = build_schedule_inventory(_notas(tmp_path, [nota]), frames=_frame())
    merge_external_specs(inv, [_ia("K-1", rebar="6#4", stirrups="E#3@10")], C)
    k1 = inv.by_mark["K-1"]
    assert (k1.rebar, k1.stirrups) == (None, estribos)


@pytest.mark.parametrize(
    "nota,longitudinales,estribos",
    [
        ('K-1 15X15 4 VARS 3/8" E 1/4 @ 15', "4#3", "E#2@15"),  # R87: octavos de pulgada
        ("K-2 15X20 4 VAR. No. 3 E#2@15", "4#3", "E#2@15"),  # antes «3E#2@15», en silencio
    ],
)
def test_a_note_with_bars_in_words_or_eighths_is_read(tmp_path, nota, longitudinales, estribos):
    inv = build_schedule_inventory(_notas(tmp_path, [nota]), frames=_frame())
    (s,) = inv.specs
    assert (s.rebar, s.stirrups, s.avisos) == (longitudinales, estribos, [])
    merge_external_specs(inv, [_ia(s.mark, rebar="6#4")], C)
    assert inv.by_mark[s.mark].rebar == longitudinales


def test_a_generic_familys_section_keeps_its_written_order(tmp_path):
    # R88: TE-A es «elemento» por su prefijo; su 40×20 no se ordena al leerse.
    inv = build_schedule_inventory(_notas(tmp_path, ["TE-A 40X20 4#4"]), frames=_frame())
    assert [s.section_cm for s in inv.specs] == [(40, 20)]


@pytest.mark.parametrize("nota", ["T1-1 25X50 2#5", "K15A 15X15 4#3", "K-1-A 15X20 4#4"])
def test_a_notes_own_mark_is_never_unread_armado(tmp_path, nota):
    # El parser no conocía estas formas de marca y las avisaba «sin leer «T1-1»».
    inv = build_schedule_inventory(_notas(tmp_path, [nota]), frames=_frame())
    (s,) = inv.specs
    assert s.avisos == [] and s.armado.texto_original == nota


def test_an_ai_mark_with_a_unicode_dash_shares_the_drawings_key(tmp_path):
    inv = build_schedule_inventory(_notas(tmp_path, ["K-7 20X30"]), frames=_frame())
    merge_external_specs(inv, [_ia("K‑7", rebar="4#3")], C)
    assert set(inv.by_mark) == {"K-7"} and inv.by_mark["K-7"].rebar == "4#3"


@pytest.mark.parametrize(
    "nota,marca_ia",
    [
        ("K-15 A 20X20 4#3 E#3@20", "K-15A"),  # R85: «20X20» no cierra un rango
        ("K-1 A 15X20 4#3", "K-1A"),
        ("C-1 A 20X20 8#5", "C-1A"),
    ],
)
def test_a_spaced_suffix_before_a_section_is_ambiguous(tmp_path, nota, marca_ia):
    inv = build_schedule_inventory(_notas(tmp_path, [nota]), frames=_frame())
    assert inv.specs == [] and inv.rechazos[0].motivo == "sin_lector"
    merge_external_specs(
        inv, [_ia(marca_ia, section_cm=(25, 25), rebar="6#6", stirrups="E#2@10")], C
    )
    k = inv.by_mark.get(marca_ia)
    assert k is None or (k.section_cm, k.rebar) == (None, None)


# --------------------------------------------------- Tarea 8, ronda 3 (R91–R94)


@pytest.mark.parametrize(
    "nota,marca,longitudinales,estribos",
    [
        ("C-1, 8 PZAS #6 E#3@20", "C-1", "8#6", "E#3@20"),  # R91: no es [C-1, C-8]
        ('K-1, 4 VARS 3/8" E 1/4" @ 15', "K-1", "4#3", "E#2@15"),  # R91: no es [K-1, K-4]
        ("K-1 4 VARS. N° 3", "K-1", "4#3", None),  # R91: una nota sin «#» se lee
        ("K-1 4 VARILLAS DEL No. 3", "K-1", "4#3", None),
        ('K-1 4 VARS 3/8"', "K-1", "4#3", None),
        ("V-4 20X40 V4#4 E#3@15", "V-4", "4#4", "E#3@15"),  # R93: no se borra «V4» de «V4#4»
        ("ZA-3 4#4 E#3@20", "ZA-3", "4#4", "E#3@20"),  # R94: una marca de zapata del detector
        ("Z-100A 4#3", "Z-100A", "4#3", None),
    ],
)
def test_a_note_in_the_parsers_vocabulary_is_read(tmp_path, nota, marca, longitudinales, estribos):
    inv = build_schedule_inventory(_notas(tmp_path, [nota]), frames=_frame())
    assert [(s.mark, s.rebar, s.stirrups) for s in inv.specs] == [(marca, longitudinales, estribos)]
    assert inv.rechazos == []
    merge_external_specs(inv, [_ia(marca, rebar="6#6")], C)
    assert inv.by_mark[marca].rebar == longitudinales


def test_a_range_end_followed_by_a_word_is_not_a_range(tmp_path):
    # R91: «K-1 A 40 CENTIMETROS» no es el rango K-1…K-40.
    inv = build_schedule_inventory(
        _notas(tmp_path, ["K-1 A 40 CENTIMETROS E#3@1S"]), frames=_frame()
    )
    assert [r.marcas for r in inv.rechazos] == [["K-1", "K-1A", "K-1-A"]]


@pytest.mark.parametrize("nota", ["K-1 4-#3", "K-1 4) #3"])
def test_a_count_with_a_dash_is_not_a_note_number(tmp_path, nota):
    # R93: en «K-1 4-#3» el «4-» es la cuenta de la varilla, no el número de una nota que se borra.
    inv = build_schedule_inventory(_notas(tmp_path, [nota]), frames=_frame())
    assert [(s.mark, s.rebar, s.avisos) for s in inv.specs] == [("K-1", "4#3", [])]
    merge_external_specs(inv, [_ia("K-1", rebar="6#6")], C)
    assert inv.by_mark["K-1"].rebar == "4#3"


@pytest.mark.parametrize("nota", ["T1-1: E#3@1S", "T1-1 (E#3@1S)"])
def test_a_compound_mark_is_consumed_by_the_grammar(tmp_path, nota):
    # R91: «T1-1» es una marca (la de la gramática, no la de ``MARCA_RE``): el texto sólo dice
    # estribos.
    inv = build_schedule_inventory(_notas(tmp_path, [nota]), frames=_frame())
    merge_external_specs(inv, [_ia("T1-1", rebar="6#6", stirrups="E#2@20", family="trabe")], C)
    k = inv.by_mark["T1-1"]
    assert (k.rebar, k.stirrups) == ("6#6", None)


def test_an_unread_eighth_is_quoted_as_written(tmp_path):
    # R92: la cita es lo que dice el plano, nunca lo que el parser se escribió («#3» por «NO. 3»).
    inv = build_schedule_inventory(_notas(tmp_path, ["K-1 15X15 NO. 3"]), frames=_frame())
    (s,) = inv.specs
    assert any("NO. 3" in a for a in s.avisos) and "longitudinales" in s.campos_con_texto


# ------------------------------------------------------------------ ronda 4 de la tarea 8


@pytest.mark.parametrize(
    "marca,familia",
    [("ZA-3", "zapata"), ("ZCM-100", "zapata"), ("Z-100A", "zapata"), ("ZC-2", "zapata"),
     ("Z-1", "zapata"), ("P-4", "pilote"), ("K-1", "castillo")],
)  # fmt: skip
def test_every_mark_a_detector_places_has_its_family(marca, familia):
    # R95: los prefijos de cimentación son los de los detectores (``text_patterns``).
    assert family_of_mark(marca) == familia


@pytest.mark.parametrize(
    "nota,marca",
    [
        ("ZA-3 120X150 #4@20", "ZA-3"),
        ("ZA-3 #4@20", "ZA-3"),
        ("ZCM-100 #4@20", "ZCM-100"),
        ("Z-1 #4@20", "Z-1"),  # una familia que ya tenía su malla la sigue leyendo
    ],
)
def test_a_footing_mesh_is_read_and_the_ai_never_wins(tmp_path, nota, marca):
    # R95: ZA-3 es una zapata: su malla se lee, y la de la IA no la cubre.
    inv = build_schedule_inventory(_notas(tmp_path, [nota]), frames=_frame())
    merge_external_specs(inv, [_ia(marca, family="zapata", mesh="#5@15")], C)
    k = inv.by_mark[marca]
    assert (k.family, k.mesh) == ("zapata", "#4@20")


@pytest.mark.parametrize(
    "texto,familia,campos",
    [
        ("#4@20", "elemento", ["estribos", "parrillas"]),  # R95: antes sólo «estribos»
        ("#4@20", "castillo", ["estribos", "parrillas"]),  # sin cabeza: malla o estribos
        ("#4@20", "zapata", ["parrillas"]),  # una familia con mallas: sólo la malla
        ("#4@20", None, ["estribos", "parrillas"]),
        ("@20", "castillo", ["estribos"]),  # una separación sola no es una malla
        ("E#3@20", "castillo", ["estribos"]),
    ],
)
def test_a_mesh_claims_parrillas_in_any_family(texto, familia, campos):
    assert campos_de_fragmento(texto, familia) == campos


def test_a_castillo_mesh_keeps_the_ai_mesh_out(tmp_path):
    # R95: «#2@20» en un castillo se avisa y reclama parrillas (y estribos): ni la malla ni los
    # estribos de la IA lo cubren.
    inv = build_schedule_inventory(_notas(tmp_path, ["K-1 15X15 4#3 #2@20"]), frames=_frame())
    merge_external_specs(inv, [_ia("K-1", mesh="#5@15", stirrups="E#2@15")], C)
    k = inv.by_mark["K-1"]
    assert (k.rebar, k.mesh, k.stirrups) == ("4#3", None, None)


@pytest.mark.parametrize(
    "nota",
    [
        "T-1 30X60 E#3@15 LS V 3",  # «V 3» es una cuenta de varillas, no la marca V-3
        "K-1 15X15 E#2@20 CON V 4",
    ],
)
def test_a_bar_word_in_the_residue_is_never_a_mark_alone(tmp_path, nota):
    # R96: lo que no se leyó tiene cifras: reclama las varillas, y la IA no las llena.
    marca = nota.split()[0]
    inv = build_schedule_inventory(_notas(tmp_path, [nota]), frames=_frame())
    (s,) = inv.specs
    assert s.avisos and "longitudinales" in s.campos_con_texto
    merge_external_specs(inv, [_ia(marca, rebar="6#6")], C)
    assert inv.by_mark[marca].rebar is None


def test_a_bar_word_glued_to_its_count_is_still_read(tmp_path):
    # R96 (y c9c2fa9): «V4#4» pegado son 4 varillas del #4.
    inv = build_schedule_inventory(_notas(tmp_path, ["K-1 15X15 V4#4 E#2@20"]), frames=_frame())
    (s,) = inv.specs
    assert (s.mark, s.rebar, s.stirrups, s.avisos) == ("K-1", "4#4", "E#2@20", [])


_ESTRIBOS_IA = {"stirrups": "E#2@25"}
_SECCION_Y_VARILLAS_IA = {"rebar": "6#6", "section_cm": (25, 25)}


@pytest.mark.parametrize(
    "nota,motivo,marcas,ia",
    [
        ("CORTE K-1 Y K-2 E#3@1S", "varias_marcas", ["K-1", "K-2"], _ESTRIBOS_IA),
        ("CORTE K-1 Y K-2 E#3@20", "varias_marcas", ["K-1", "K-2"], _ESTRIBOS_IA),  # legible
        ("CORTE K-1 15X20 4#3", "sin_lector", ["K-1"], _SECCION_Y_VARILLAS_IA),
        ("SECCION K-1 15X20 4#3", "sin_lector", ["K-1"], _SECCION_Y_VARILLAS_IA),
        ("CORTE A-A K-1 15X20 4#3", "sin_lector", ["K-1"], _SECCION_Y_VARILLAS_IA),  # R99
        ("DET. 5 K-1 4#3", "sin_lector", ["K-1"], _SECCION_Y_VARILLAS_IA),
        ("DETALLE DE K-1 15X15 4#3", "sin_lector", ["K-1"], _SECCION_Y_VARILLAS_IA),
        ("3.- CORTE K-1 Y K-2 E#3@20", "varias_marcas", ["K-1", "K-2"], _ESTRIBOS_IA),
    ],
)
def test_a_title_with_armado_names_every_mark_after_it(tmp_path, nota, motivo, marcas, ia):
    # R97, R99: el encabezado de un corte con armado nombra todas sus marcas; no se lee y la IA
    # de ninguna llena lo que dice.
    inv = build_schedule_inventory(_notas(tmp_path, [nota]), frames=_frame())
    assert inv.specs == []
    assert [(r.motivo, r.marcas) for r in inv.rechazos] == [(motivo, marcas)]
    merge_external_specs(inv, [_ia(m, **ia) for m in marcas], C)
    assert not [m for m in marcas if _ia_lleno(inv, m)]


def test_a_bare_pointer_names_no_mark(tmp_path):
    # R97: «VER CORTE C-2» sin armado no nombra a C-2: su nota se lee y nada la bloquea.
    inv = build_schedule_inventory(
        _notas(tmp_path, ["VER CORTE C-2", "C-2 30X30 8#6 E#3@20"]), frames=_frame()
    )
    assert inv.rechazos == []
    merge_external_specs(inv, [_ia("C-2", family="columna", section_cm=(40, 40))], C)
    k = inv.by_mark["C-2"]
    assert (k.rebar, k.stirrups, k.section_cm) == ("8#6", "E#3@20", (30, 30))


@pytest.mark.parametrize(
    "nota",
    ["C-1 PLACA BASE 35X35 CON ANCLAS 4 PZAS #6", "C-1 ANCLAS 4 VARS #6"],
)
def test_anchor_bars_are_not_the_elements_armado(tmp_path, nota):
    # R98, R100: las varillas (y la sección) de una placa o de unas anclas no son de la columna:
    # se avisan, reclaman su campo y la IA no lo llena.
    inv = build_schedule_inventory(_notas(tmp_path, [nota]), frames=_frame())
    assert not [s for s in inv.specs if s.rebar or s.section_cm]
    merge_external_specs(inv, [_ia("C-1", family="columna", rebar="8#8")], C)
    k = inv.by_mark.get("C-1")
    assert k is None or k.rebar is None


def test_bars_without_an_anchor_word_are_read(tmp_path):
    # R98: sin la palabra de un objeto, «4#6» son las varillas de la columna.
    inv = build_schedule_inventory(_notas(tmp_path, ["C-1 30X30 4#6"]), frames=_frame())
    (s,) = inv.specs
    assert (s.mark, s.section_cm, s.rebar, s.avisos) == ("C-1", (30, 30), "4#6", [])


# ------------------------------------------------------------------ ronda 5 de la tarea 8


def _pila(tmp_path, etiqueta, renglones):
    """Una pila: la etiqueta y sus renglones encima, como en un detalle."""
    doc = ezdxf.new("R2010")
    msp = doc.modelspace()
    msp.add_text(etiqueta, height=0.13).set_placement(
        (0.0, 0.0), align=TextEntityAlignment.BOTTOM_CENTER
    )
    for i, texto in enumerate(reversed(renglones)):
        msp.add_text(texto, height=0.10).set_placement((-0.2, 0.18 * (i + 1)))
    doc.saveas(tmp_path / "pila.dxf")
    return DxfParser().parse_file(tmp_path / "pila.dxf").entities


@pytest.mark.parametrize(
    "etiqueta,renglones,estribos,apuntada",
    [
        ("K-1", ["4#3", "E#2@15 VER CORTE C-2"], "E#2@15 VER CORTE", "C-2"),
        ("K-1", ["4#3", "E#2@15", "2E#3 VER CORTE C-2"], "E#2@15 2E#3 VER CORTE", "C-2"),
        ("K-2", ["4#4", "E#2@15 VER DET. K-2A"], "E#2@15 VER DETALLE", "K-2A"),
    ],
)
def test_a_trailing_pointer_reads_for_its_owner(tmp_path, etiqueta, renglones, estribos, apuntada):
    # R99: una referencia tras el armado remite: el renglón es de la pila de su dueño, que lo lee
    # con su referencia; la marca a la que apunta no queda bloqueada ni ilegible.
    inv = build_schedule_inventory(_pila(tmp_path, etiqueta, renglones), frames=_frame())
    assert inv.rechazos == []
    merge_external_specs(
        inv,
        [_ia(etiqueta, stirrups="E#2@25"), _ia(apuntada, stirrups="E#4@30", rebar="9#9")],
        C,
    )
    assert inv.by_mark[etiqueta].stirrups == estribos
    assert (inv.by_mark[apuntada].stirrups, inv.by_mark[apuntada].rebar) == ("E#4@30", "9#9")


def test_a_trailing_pointer_in_a_note_never_touches_the_pointed_mark(tmp_path):
    # R99: «… VER CORTE C-2» en la nota de K-1 no le da nada a C-2, ni lo bloquea.
    inv = build_schedule_inventory(
        _notas(tmp_path, ["K-1 15X15 4#3 E#2@15 VER CORTE C-2", "C-2 30X30 8#6 E#3@20"]),
        frames=_frame(),
    )
    k1, c2 = inv.by_mark["K-1"], inv.by_mark["C-2"]
    assert (k1.section_cm, k1.rebar, k1.stirrups) == ((15, 15), "4#3", "E#2@15 VER CORTE")
    assert (c2.section_cm, c2.rebar, c2.stirrups) == ((30, 30), "8#6", "E#3@20")
    assert inv.rechazos == []


@pytest.mark.parametrize(
    "nota,leido",
    [
        ("C-1 30X30 8#6 E#3@20 PLACA BASE 35X35", ((30, 30), "8#6", "E#3@20")),  # R100
        # «CON» entre los dos objetos no es contexto: los estribos se avisan (R18), no se pierden.
        ("C-1 30X30 8#6 E#3@20 PLACA BASE 35X35 CON ANCLAS 4 PZAS #6", ((30, 30), "8#6", None)),
        (
            "C-1 40X40 8#6 E#3@10 ANCLAJE 60 CM",
            ((40, 40), "8#6", None),
        ),  # el anclaje es de la varilla
        ("C-1 4#3 E#2@20 HASTA PLACA", (None, "4#3", None)),  # «PLACA» sin fragmento: nada suyo
    ],
)
def test_an_object_owns_only_its_fragment(tmp_path, nota, leido):
    # R100: lo de la placa o las anclas se avisa; lo demás es de la columna y se lee.
    inv = build_schedule_inventory(_notas(tmp_path, [nota]), frames=_frame())
    (s,) = inv.specs
    assert (s.section_cm, s.rebar, s.stirrups) == leido
    objeto = "PLACA BASE" in nota or "ANCLAS" in nota
    assert any("no es armado del elemento" in a for a in s.avisos) == objeto


def test_a_family_note_reports_its_plate(tmp_path):
    # R100: «COLUMNAS PLACA BASE 35X35 E#3@20»: la placa se avisa (antes se perdía sin aviso) y
    # los estribos de las columnas se leen.
    inv = build_schedule_inventory(
        _notas(tmp_path, ["COLUMNAS PLACA BASE 35X35 E#3@20"]), frames=_frame()
    )
    (s,) = inv.specs
    assert (s.mark, s.section_cm, s.stirrups) == ("COLUMNA", None, "E#3@20")
    assert "«PLACA BASE 35X35»: no es armado del elemento" in s.avisos
    assert "seccion" in s.campos_con_texto


def test_a_bar_word_mark_after_the_armado_claims_the_bars(tmp_path):
    # R101: «K-1 15X15 E#2@20 V 4» es de K-1 (no de varias marcas): su sección se lee, y «V 4»
    # queda sin leer y reclama las varillas, que la IA no llena.
    inv = build_schedule_inventory(_notas(tmp_path, ["K-1 15X15 E#2@20 V 4"]), frames=_frame())
    (s,) = inv.specs
    assert (s.mark, s.section_cm) == ("K-1", (15, 15))
    assert "longitudinales" in s.campos_con_texto and inv.rechazos == []
    merge_external_specs(inv, [_ia("K-1", rebar="6#6")], C)
    assert inv.by_mark["K-1"].rebar is None


# ------------------------------------------------------------- tarea 8b, paso A (R102–R105)


def _ias(*marcas):
    """La IA con un valor en cada campo de cada marca: lo que el plano dice nunca debe dejarla
    entrar."""
    return [
        _ia(m, section_cm=(50, 50), rebar="8#8", stirrups="E#4@30", family=family_of_mark(m))
        for m in marcas
    ]


@pytest.mark.parametrize(
    "nota",
    [
        "K-1 4#3 E#2@20 V-4: 20X40 4#5 E#3@15",
        "K-1 4#3 E#2@20, V-4: 4#5",
        "K-1 4#3 E#2@20 V-4= 4#5",
        "K-1 4#3 E#2@20 (V-4) 4#5",
        "K-1 4#3 E#2@20 V-4 - 4#5",
        "K-1 4#3 E#2@20 V-4 CON 4#5",
        "K-1 4#3 E#2@20 V-4 LECHO SUP. 2#5",
    ],
)
def test_another_bar_word_mark_with_anything_after_it_is_named(tmp_path, nota):
    # R103: «V-4» tras el armado de K-1 y con algo detrás es la marca V-4: la nota es de varias
    # marcas, nada se lee y ni K-1 ni V-4 toman nada de la IA en lo que el texto dice.
    inv = build_schedule_inventory(_notas(tmp_path, [nota]), frames=_frame())
    assert [s for s in inv.specs] == []
    assert [(r.motivo, r.marcas) for r in inv.rechazos] == [("varias_marcas", ["K-1", "V-4"])]
    merge_external_specs(inv, _ias("K-1", "V-4"), C)
    for marca in ("K-1", "V-4"):
        k = inv.by_mark.get(marca)
        assert k is None or (k.rebar, k.stirrups) == (None, None)


@pytest.mark.parametrize("nota", ["K-1 15X15 E#2@20 V-4", "K-1 15X15 E#2@20 V 4"])
def test_a_bar_word_mark_that_ends_the_text_claims_the_bars(tmp_path, nota):
    # R103: «V-4» o «V 4» al final, tras el armado de K-1: varillas sin leer, en cualquier
    # escritura (antes la de guion se perdía y la IA llenaba las varillas de K-1).
    inv = build_schedule_inventory(_notas(tmp_path, [nota]), frames=_frame())
    (s,) = inv.specs
    assert (s.mark, s.section_cm) == ("K-1", (15, 15)) and inv.rechazos == []
    assert "longitudinales" in s.campos_con_texto
    assert any("V-4" in a or "V 4" in a for a in s.avisos)
    merge_external_specs(inv, _ias("K-1"), C)
    assert inv.by_mark["K-1"].rebar is None


@pytest.mark.parametrize(
    "texto,mtext",
    [
        ("3.- 4#3 E#2@20 VER CORTE C-2", False),
        ("1. 8#6 VER CORTE C-2", False),
        ("1. 30X30 8#6", False),
        ("NOTAS:\n1.- 4#3 E#2@20 VER CORTE C-2", True),
    ],
)
def test_a_text_nobody_reads_is_always_reported(tmp_path, texto, mtext):
    # R104: un texto con armado que ninguna lectura toma ni nadie rechaza se rechaza al final:
    # sin dueño (un puntero no nombra a nadie). Antes se perdía en silencio.
    doc = ezdxf.new("R2010")
    if mtext:
        doc.modelspace().add_mtext(texto.replace("\n", "\\P"), dxfattribs={"char_height": 0.2})
    else:
        doc.modelspace().add_text(texto, height=0.2)
    doc.saveas(tmp_path / "nota.dxf")
    inv = build_schedule_inventory(
        DxfParser().parse_file(tmp_path / "nota.dxf").entities, frames=_frame()
    )
    linea = texto.split("\n")[-1]
    assert [(r.motivo, r.texto, r.marcas) for r in inv.rechazos] == [("sin_dueno", linea, [])]
    merge_external_specs(inv, _ias("C-2"), C)
    assert inv.by_mark["C-2"].rebar == "8#8"  # la marca apuntada ni se bloquea ni toma nada


def test_a_section_alone_on_a_stack_line_is_reported(tmp_path):
    # R104: «15X15» sobre la pila de K-1 no lo lee nadie: se dice (antes se perdía).
    ents = _pila(tmp_path, "K-1", ["15X15", "4#3", "E#2@20"])
    inv = build_schedule_inventory(ents, frames=_frame())
    (k1,) = inv.specs
    assert (k1.rebar, k1.stirrups) == ("4#3", "E#2@20")
    assert [(r.motivo, r.texto) for r in inv.rechazos] == [("sin_dueno", "15X15")]


def test_armado_after_a_pointed_mark_is_never_the_owners(tmp_path):
    # R102: «E#2@15 VER CORTE C-2 8#6 E#3@20» en la pila de K-1 encabeza: nombra a C-2 y no se lee
    # (antes K-1 tomaba 4#3+8#6). La pila se corta ahí: el «4#3» de arriba queda sin dueño.
    inv = build_schedule_inventory(
        _pila(tmp_path, "K-1", ["4#3", "E#2@15 VER CORTE C-2 8#6 E#3@20"]), frames=_frame()
    )
    assert not [s for s in inv.specs if s.rebar and "8#6" in s.rebar]
    assert sorted((r.motivo, r.texto, tuple(r.marcas)) for r in inv.rechazos) == [
        ("sin_dueno", "4#3", ()),
        ("sin_lector", "E#2@15 VER CORTE C-2 8#6 E#3@20", ("C-2",)),
    ]


def test_a_note_with_armado_after_its_pointer_names_both_marks(tmp_path):
    # R102: la nota de K-1 con «VER CORTE C-2 30X30 8#6» detrás es de K-1 y de C-2: no se lee, y
    # la sección de C-2 la dice el plano («C-2 30X30»), nunca la IA.
    inv = build_schedule_inventory(
        _notas(tmp_path, ["K-1 15X15 4#3 E#2@15 VER CORTE C-2 30X30 8#6", "C-2 30X30"]),
        frames=_frame(),
    )
    assert [(r.motivo, r.marcas) for r in inv.rechazos] == [("varias_marcas", ["K-1", "C-2"])]
    assert not [s for s in inv.specs if s.mark == "K-1"]
    merge_external_specs(inv, _ias("K-1", "C-2"), C)
    assert inv.by_mark["C-2"].section_cm == (30, 30)
    assert (inv.by_mark["C-2"].rebar, inv.by_mark.get("K-1")) == (None, None)


@pytest.mark.parametrize("como", ["nota", "pila", "numerada"])
def test_a_leading_pointer_heads_in_every_context(tmp_path, como):
    # R102: «VER CORTE C-2 30X30 8#6 E#2@15» al principio encabeza: nombra a C-2 y no se lee, sea
    # una nota suelta, un renglón de la pila de K-1 o una nota numerada (antes, según el caso,
    # nadie lo leía, lo leía K-1 o se perdía).
    texto = "VER CORTE C-2 30X30 8#6 E#2@15"
    if como == "pila":
        ents = _pila(tmp_path, "K-1", [texto])
    else:
        ents = _notas(tmp_path, [f"1.- {texto}" if como == "numerada" else texto])
    inv = build_schedule_inventory(ents, frames=_frame())
    assert [s for s in inv.specs] == []
    assert [(r.motivo, r.marcas) for r in inv.rechazos] == [("sin_lector", ["C-2"])]
    merge_external_specs(inv, _ias("C-2"), C)
    assert inv.by_mark.get("C-2") is None  # la IA de C-2 no llena nada: el plano lo dice


@pytest.mark.parametrize(
    "renglones,varillas,estribos",
    [
        (["4#3 VER DET. K-2", "E#2@15"], "4#3 VER DETALLE", "E#2@15"),  # R102: se guarda
        (["4#3", "2E#3 VER CORTE"], "4#3", "2E#3 VER CORTE"),  # Marina
        (["4#3", "E#2@15 VER CORTE C-2"], "4#3", "E#2@15 VER CORTE"),
    ],
)
def test_a_trailing_pointer_keeps_its_reference_wherever_it_sits(
    tmp_path, renglones, varillas, estribos
):
    inv = build_schedule_inventory(_pila(tmp_path, "K-1", renglones), frames=_frame())
    (k1,) = inv.specs
    assert (k1.rebar, k1.stirrups, inv.rechazos) == (varillas, estribos, [])
    merge_external_specs(inv, _ias("K-2", "C-2"), C)
    assert inv.by_mark["K-2"].rebar == "8#8" and inv.by_mark["C-2"].rebar == "8#8"


# ------------------------------------------------------------------ tarea 8b, R83


@pytest.mark.parametrize(
    "nota,familia,familias",
    [
        # R83: la palabra de la familia es el sujeto (la primera, tras el número de la nota, o
        # seguida de «:»): es la nota de esa familia.
        ("DALA: 15X20 4#3 E#2@20", "dala", None),
        ("1.- CASTILLOS 15X15 4#3 E#2@20", "castillo", None),
        ("CADENA DE ENRASE 15x25 4#3 E#2@15", "dala", None),  # Marina, ES-101
        # En otro lugar no lo es: se rechaza con sus familias, nunca se pierde.
        (
            "2 VARILLAS #5 ANCLADA AL MURO O CADENA CON ANCHORFIX 3001 DE SIKA",
            None,
            ["muro", "dala"],
        ),
        ("ANCLAR A LA TRABE CON 2#4", None, ["trabe"]),
        # «WORD:» es sujeto sólo a la cabeza (R110).
        ("ANCLAR A LA TRABE: 2#4", None, ["trabe"]),
        ("VER PLANO DE DALAS: 4#3 E#2@20", None, ["dala"]),
        # Un número de nota con letra es un número de nota (R110).
        ("A) DALAS 15X20 4#3 E#2@20", "dala", None),
        ("a).- CASTILLOS 15X15 4#3 E#2@20", "castillo", None),
        # ARMEX es armado prefabricado, no una familia (R107): sólo la cadena, que no es sujeto.
        ("ARMEX 15X30 CADENA DE BORDE", None, ["dala"]),
        ("4V#4 E#3@20CMS CADENA DE DESPLANTE", None, ["dala"]),  # PRUEBA-1
    ],
)
def test_a_family_note_needs_its_family_word_as_the_subject(tmp_path, nota, familia, familias):
    inv = build_schedule_inventory(_notas(tmp_path, [nota]), frames=_frame())
    if familia is not None:
        (s,) = inv.specs
        assert (s.mark, s.family, s.source) == (familia.upper(), familia, "nota")
        assert inv.rechazos == []
    else:
        assert inv.specs == []
        assert [(r.motivo, r.texto, r.marcas, r.familias) for r in inv.rechazos] == [
            ("sin_lector", nota, [], familias)
        ]


# ------------------------------------------------- Tarea 8b, ronda 1: R107, R109, R110, R111


@pytest.mark.parametrize(
    "texto,seccion,rebar",
    [
        ("K-1 20.5X40 4#3", (20.5, 40), "4#3"),  # antes: la sección no se veía y la IA la llenaba
        ("K-1 20X40,5 4#3", (20, 40.5), "4#3"),  # antes: 20x40 y «5 4#3» sin leer
    ],
)
def test_a_section_with_decimals_is_read_with_them(tmp_path, texto, seccion, rebar):
    # R109: una sección con decimales (punto o coma) se lee con ellos, nunca truncada.
    inv = build_schedule_inventory(_notas(tmp_path, [texto]), frames=_frame())
    (s,) = inv.specs
    assert (s.section_cm, s.rebar, s.avisos) == (seccion, rebar, [])
    assert "seccion" in campos_de_fragmento(texto, "castillo")
    merge_external_specs(inv, [_ia("K-1", section_cm=(40, 40))], C)
    assert inv.by_mark["K-1"].section_cm == seccion


def test_a_pointer_claims_the_bars_and_the_stirrups(tmp_path):
    # R110: «K-1 15X15 VER CORTE C-2» remite el armado a un corte: las varillas y los estribos son
    # del plano (por referencia), nunca de la IA; el puntero se guarda.
    inv = build_schedule_inventory(_notas(tmp_path, ["K-1 15X15 VER CORTE C-2"]), frames=_frame())
    (s,) = inv.specs
    assert s.campos_con_texto == ["seccion", "longitudinales", "estribos"]
    assert s.avisos == ["armado remitido a otro dibujo: «VER CORTE C-2»"]
    merge_external_specs(inv, [_ia("K-1", rebar="4#4", stirrups="E#3@20")], C)
    k1 = inv.by_mark["K-1"]
    assert (k1.section_cm, k1.rebar, k1.stirrups) == ((15, 15), None, None)


@pytest.mark.parametrize(
    "renglon,estribos",
    [
        ("E#2@15 (VER CORTE C-2)", "E#2@15 VER CORTE"),
        ("E#2@15 VER CORTES C-1 Y C-2", "E#2@15 VER CORTE"),
        ("E#2@15 VER CORTE C-2.", "E#2@15 VER CORTE"),
    ],
)
def test_a_pointer_in_a_stack_keeps_its_reference(tmp_path, renglon, estribos):
    # R110: el puntero entre paréntesis, en plural o con punto se guarda como referencia; antes el
    # renglón quedaba sin leer y los estribos ilegibles.
    inv = build_schedule_inventory(_stack_entities(tmp_path, "K-1", ["4#3", renglon]), C)
    k1 = inv.by_mark["K-1"]
    assert (k1.rebar, k1.stirrups, k1.avisos) == ("4#3", estribos, [])


def test_a_letter_note_number_is_a_note_number(tmp_path):
    # R110: «a).-» es el número de la nota, no algo sin leer.
    inv = build_schedule_inventory(_notas(tmp_path, ["a).- K-1 15X20 4#3 E#2@20"]), frames=_frame())
    (s,) = inv.specs
    assert (s.mark, s.section_cm, s.rebar, s.stirrups, s.avisos) == (
        "K-1",
        (15, 20),
        "4#3",
        "E#2@20",
        [],
    )


def _mtexto(tmp_path, textos):
    doc = ezdxf.new("R2010")
    for i, texto in enumerate(textos):
        doc.modelspace().add_mtext(
            texto.replace("\n", "\\P"), dxfattribs={"char_height": 0.2}
        ).set_location((0, i * 5.0))
    doc.saveas(tmp_path / "mtexto.dxf")
    return DxfParser().parse_file(tmp_path / "mtexto.dxf").entities


def test_a_family_phrase_line_labels_its_armado(tmp_path):
    # R107 (PRUEBA-1): un renglón que es sólo el nombre de la familia, sobre o bajo renglones de
    # armado, es la etiqueta de la familia; antes era un rechazo.
    inv = build_schedule_inventory(
        _mtexto(tmp_path, ["4V#4 E#3@20CMS\nCADENA DE DESPLANTE"]), frames=_frame()
    )
    (s,) = inv.specs
    assert (s.mark, s.family, s.rebar, s.stirrups, s.avisos) == (
        "DALA",
        "dala",
        "4#4",
        "E#3@20",
        [],
    )
    assert inv.rechazos == []


def test_armex_is_prefab_armado_not_a_family(tmp_path):
    # R107: ARMEX no es una familia ni varillas que se lean: se cita y reclama varillas y estribos.
    inv = build_schedule_inventory(
        _mtexto(tmp_path, ["ARMEX 15X30\nCADENA DE BORDE"]), frames=_frame()
    )
    (s,) = inv.specs
    assert (s.family, s.section_cm, s.rebar, s.stirrups) == ("dala", (15, 30), None, None)
    assert s.avisos == ["armado prefabricado «ARMEX»: no se lee"]
    assert s.campos_con_texto == ["seccion", "longitudinales", "estribos"]
    assert campos_de_fragmento("ARMEX", "castillo") == ["longitudinales", "estribos"]
    # Sola, no es la nota de los castillos (antes: castillo 15x30).
    sola = build_schedule_inventory(_notas(tmp_path, ["ARMEX 15X30"], "sola.dxf"), frames=_frame())
    assert sola.by_family == {} and [r.motivo for r in sola.rechazos] == ["sin_dueno"]


def test_piece_sizes_under_a_family_name_are_not_armado(tmp_path):
    # R107: «MURO DE BLOCK» sobre medidas de pieza (10X20X40) no es una lectura.
    inv = build_schedule_inventory(
        _mtexto(tmp_path, ["MURO DE BLOCK\n10X20X40 Ò\n15X20X40"]), frames=_frame()
    )
    assert inv.specs == []


@pytest.mark.parametrize(
    "renglones,bloqueados",
    [
        (["4#3", "E#2@15 VER CORTE C-2 8#6 E#3@20"], ["longitudinales"]),
        (["4#3", "15X15", "E#2@20"], ["seccion", "longitudinales", "estribos"]),
        (["4#3", "E#2@20", "15X15"], ["seccion", "longitudinales", "estribos"]),
    ],
)
def test_rows_past_a_cut_in_the_column_block_the_labels_ai(tmp_path, renglones, bloqueados):
    # R111: los renglones sin dueño en la columna de una etiqueta, más allá de donde su pila se
    # cortó, pueden ser suyos: bloquean su lectura IA en lo que dicen y llevan la etiqueta como
    # «posible» en su rechazo. Nunca son un dato.
    inv = build_schedule_inventory(_stack_entities(tmp_path, "K-1", renglones), C)
    sin_dueno = [r for r in inv.rechazos if r.motivo == "sin_dueno"]
    assert sin_dueno and all(r.posibles == ["K-1"] for r in sin_dueno)
    merge_external_specs(inv, [_ia("K-1", section_cm=(40, 40), rebar="4#4", stirrups="E#3@20")], C)
    ia = next(s for s in inv.specs if s.source == "ia")
    assert ia.campos_bloqueados == bloqueados
    assert {b.por for b in ia.bloqueos if b.por == "posible"} == {"posible"}


def test_a_lettered_note_line_never_joins_a_stack(tmp_path):
    # R110: «a).- …» es una nota numerada: nunca un renglón de la pila de la etiqueta de al lado.
    inv = build_schedule_inventory(
        _stack_entities(tmp_path, "K-1", ["a).- SE PERMITE TRASLAPAR 4#3"]), C
    )
    assert "K-1" not in inv.by_mark
    assert [(r.motivo, r.posibles) for r in inv.rechazos] == [("sin_dueno", [])]
