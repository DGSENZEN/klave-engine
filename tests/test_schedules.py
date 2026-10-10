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
    mark_cuadro_detections,
    merge_external_specs,
)
from klave_engine.dxf.entities import EntityType, EvidencePacket, NormalizedEntity
from klave_engine.dxf.parser import DxfParser


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
        msp.add_text("ARMEX 15X30", height=0.2).set_placement((40, 40))  # a general note
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
        msp.add_text("ARMEX 15X30", height=0.2).set_placement((10, 10))

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
    # numeración; no es una lectura (antes tampoco). Una nota de familia con un armado que no se
    # pudo leer sí lo es, con su aviso.
    def build(msp):
        msp.add_text(
            "1.-EL REFUERZO PARA HUECOS DE HASTA 15X20CMS 2.-COLOCAR EL PASO A LA MITAD "
            "DEL PERALTE DE LA CONTRATRABE",
            height=0.2,
        ).set_placement((0, 0))
        msp.add_text("2 VARILLAS #5 ANCLADA AL MURO O CADENA", height=0.2).set_placement((0, 9))

    inv = build_schedule_inventory(_entities(tmp_path, build), frames=_frame())
    assert "contratrabe" not in inv.by_family
    (dala,) = [s for s in inv.specs if s.family == "dala"]
    assert dala.rebar is None and dala.avisos and "longitudinales" in dala.campos_con_texto


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
    merge_external_specs(inv, [_ia("K-7", stirrups="E#2@20")])
    assert inv.by_mark["K-7"].stirrups == "E#3@20"


def test_ia_never_covers_a_text_nobody_reads(tmp_path):
    # «sin lector»: el texto nombra a K-7 pero sus estribos no se leen; la IA no los cubre.
    inv = build_schedule_inventory(_notas(tmp_path, ["K-7 E#3@1S", "K-7 20X30"]), frames=_frame())
    assert [(r.motivo, r.marcas) for r in inv.rechazos] == [("sin_lector", ["K-7"])]
    merge_external_specs(inv, [_ia("K-7", stirrups="E#2@20", rebar="4#3")])
    k7 = inv.by_mark["K-7"]
    assert (k7.stirrups, k7.rebar) == (None, None) and k7.section_cm == (20, 30)
    assert any("la lectura IA no lo llena" in a for a in k7.avisos)
    assert any(s.source == "ia" and s.mark == "K-7" for s in inv.specs)


def test_ia_never_covers_a_text_nobody_reads_for_a_mark_without_readings(tmp_path):
    inv = build_schedule_inventory(_notas(tmp_path, ["K-9 E#3@1S"]), frames=_frame())
    merge_external_specs(inv, [_ia("K-9", stirrups="E#2@20", section_cm=(15, 15))])
    k9 = inv.by_mark["K-9"]
    assert (k9.section_cm, k9.stirrups, k9.source) == ((15, 15), None, "ia")
    inv2 = build_schedule_inventory(_notas(tmp_path, ["K-9 E#3@1S"], "b.dxf"), frames=_frame())
    merge_external_specs(inv2, [_ia("K-9", stirrups="E#2@20")])
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
    merge_external_specs(inv, [_ia("K-1", rebar="4#3", section_cm=(15, 15))])
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
    merge_external_specs(inv, [_ia(marca_ia, rebar="6#4", stirrups="E#2@20", section_cm=(15, 15))])
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
    merge_external_specs(inv, [_ia("K-2", rebar="6#4", section_cm=(20, 20))])
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
