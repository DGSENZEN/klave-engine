"""Tarea 9c, sobre el plano estructural de Marina (si está): los títulos de detalle y el armado de
sus secciones, medidos contra la verdad del dibujo (cada texto por su handle del DXF).

- R164: una caja reclamada es la sección PROPIA del título; T3-8 ya no reclama el escalón de la
  losa vecina; T2-7 (sección compuesta) recupera su caja y su armado.
- Las atribuciones «posible» equivocadas de la tarea 9 (R164, la carga de la tarea 9) nunca se
  vuelven una lectura bajo el título equivocado."""

from pathlib import Path

import pytest
from klave_engine.detection.frames import detect_frames
from klave_engine.detection.schedules import ScheduleInventory, build_schedule_inventory
from klave_engine.detection.text_patterns import TextPatternConfig
from klave_engine.dxf.harmonize import harmonize_units
from klave_engine.dxf.parser import DxfParser

C = TextPatternConfig()
_MARINA = (
    Path(__file__).resolve().parents[1]
    / "data"
    / "raw"
    / "marina-4"
    / "converted"
    / "02 ESTRUCTURAL L.04 - 26.01.15.dxf"
)


@pytest.fixture(scope="module")
def marina() -> tuple[ScheduleInventory, dict[str, str]]:
    """El inventario de Marina y, por handle del DXF, el id de su entidad."""
    if not _MARINA.exists():
        pytest.skip(f"sin el dibujo {_MARINA.name}")
    dibujo = DxfParser().parse_file(_MARINA)
    unidades, _ = harmonize_units([(dibujo.source_file, dibujo.insunits, dibujo.entities)])
    inv = build_schedule_inventory(
        dibujo.entities, C, unit_to_m=unidades.to_meters(), frames=detect_frames(dibujo.entities)
    )
    return inv, {e.raw_handle: e.entity_id for e in dibujo.entities}


def _posibles(inv: ScheduleInventory, entidad: str) -> list[str]:
    return sorted({m for r in inv.rechazos if r.entidad_id == entidad for m in r.posibles})


def _leida_por(inv: ScheduleInventory, entidad: str) -> set[str]:
    """Las marcas cuyas lecturas (no la IA) toman el texto."""
    return {s.mark for s in inv.specs if s.source != "ia" and entidad in s.entidades}


# T2-7 (ES-201), su armado propio (R164): «2#6» con su flecha al cuerpo, lo de su alzado («2#8»,
# los dos «4#8», «1@6,8@15») y sus «2E#4».
_DE_T2_7 = ["A9E0B", "A99A3", "A99A2", "A99A8", "AEBDC", "A9AAA", "A9A22"]


@pytest.mark.parametrize("handle", _DE_T2_7)
def test_t2_7_composite_section_keeps_its_own_armado(marina, handle):
    inv, ids = marina
    entidad = ids[handle]
    assert "T2-7" in _posibles(inv, entidad)
    assert _leida_por(inv, entidad) == set()  # su caja es reclamada: nunca se lee


@pytest.mark.parametrize("handle", ["A903A", "A903B", "A903C", "A9031"])
def test_t3_8_no_longer_claims_the_slab_step(marina, handle):
    # R164: el escalón de la losa nervada junto a T3-8 (ES-301) no es su sección: lo que va en él
    # no es de T3-8.
    inv, ids = marina
    entidad = ids[handle]
    assert "T3-8" not in _posibles(inv, entidad)
    assert "T3-8" not in _leida_por(inv, entidad)


# Atribuciones «posible» equivocadas de la tarea 9 (R164 y la carga de la tarea 9): bloqueos, nunca
# lecturas. Ninguna se lee bajo el título equivocado (bajo el suyo, o sin leer).
_EQUIVOCADAS = [
    ("BD465", "T1-8"),  # «3#8» del alzado de T1-7
    ("CFC1F", "CTA-14"),  # renglones de columna
    ("8F6B6", "T3-5"),
    ("8F6BA", "T3-10"),
    ("8F9F0", "T3-11"),
    ("A9A23", "T2-11"),
    ("CCE7C", "CTA-7"),
    ("D0949", "CTA-16"),
    ("8F9F2", "T3-10"),  # alzado de T3-9
    ("8F9F3", "T3-10"),
    ("8F9F4", "T3-10"),
    ("8FD34", "T3-14"),  # alzado de T3-13
    ("8FD71", "T3-14"),
    ("BAFC2", "Z1"),  # alzado de W2
    ("AC7AD", "T2-14"),  # alzado de T2-13
    ("A903A", "T3-8"),  # el escalón de la losa junto a T3-8
    ("A903B", "T3-8"),
    ("A903C", "T3-8"),
    ("A9031", "T3-8"),
    ("8F326", "T3-7"),  # «2#8» de T3-3
    ("8F328", "T3-7"),  # «@20» de T3-3
    ("8F62C", "T3-7"),  # «10@10,1@6» de T3-6
    ("BB1C6", "T1-7"),  # «1#4» de W1
    ("BB1C4", "T1-7"),  # «2#4» de W1
    ("D04F2", "CTA-13"),  # «3#8» de CTA-16
    ("4B767", "T3-3"),  # «E#4» de T3-1
    ("8F1A7", "T3-3"),  # «1@6» de T3-1
    ("B79B6", "CE-3"),  # «E#2@15» de CE-1 (ES-100)
    ("B79E7", "CE-3"),  # «E#2@15» de CE-2 (ES-100)
]


@pytest.mark.parametrize("handle,equivocada", _EQUIVOCADAS)
def test_a_wrong_posible_is_never_read_under_the_wrong_title(marina, handle, equivocada):
    inv, ids = marina
    assert equivocada not in _leida_por(inv, ids[handle])


# R168: los títulos «CI» de ES-200, ES-300 y ES-400 son las variantes por muro de 15, 20 y 30 cm
# (su subtítulo «(PARA MUROS DE nCM)»), con su sección.
_CI = {
    "A8EB3": (15.0, (15, 20)), "A8ECC": (20.0, (20, 20)), "A8EB4": (30.0, (30, 20)),
    "A8DFD": (15.0, (15, 20)), "A8E16": (20.0, (20, 20)), "A8DFE": (30.0, (30, 20)),
    "4EFEA": (15.0, (15, 20)), "4F003": (20.0, (20, 20)), "4EFEB": (30.0, (30, 20)),
}  # fmt: skip


@pytest.mark.parametrize("handle", sorted(_CI))
def test_each_ci_title_is_its_walls_variant(marina, handle):
    inv, ids = marina
    (lectura,) = [s for s in inv.specs if s.metodo == "cotas" and s.entidades == [ids[handle]]]
    assert (lectura.para_muro_cm, lectura.section_cm) == _CI[handle]


# R147: cada pila bajo la sección propia de un título de Marina, contra la verdad del dibujo
# (los textos bajo su sección, de arriba abajo, sin las llamadas): sus renglones por su handle,
# su marca, su hoja y lo que se lee. T2-8 no lee sus longitudinales: un texto que puede ser suyo
# («4#8», que R140 le atribuye del alzado de T2-7) va fuera de la pila; lo cita y lo reclama.
# R196, R209: las pilas que otra sección alcanza sin que estén claramente (25 %) más pegadas a la
# suya quedan en duda (ver ``_EN_DUDA``), aunque la otra lea su propia pila (R205a, revertida: dos
# secciones así se cambiaban las pilas), y lo que dejan como «posible» veta el campo de la marca
# vecina en la hoja: CE-3 (ES-100) y CE-4 (ES-300) sus estribos, las CI de 15 y 30 cm de ES-300
# los dos (la de 20 cm, en duda, es la misma marca). R205b: una reclamada (T2-4) compite sólo por
# la distancia y nunca queda «huérfana»: T2-1 se lee (``_RECUPERADAS``).
_PILAS = [
    (["CFF58"], "CTA-13", "ES-004", None, "2E#4@15"),
    (["36E92"], "CTA-14", "ES-004", None, "E#4@20"),
    (["36BA1"], "CTA-9", "ES-004", None, "E#3@15"),
    (["B7A0C", "B7A10"], "CE-3", "ES-100", "6#4", None),
    (["B6BF4"], "T1-2", "ES-101", None, "E#3@12"),
    (["B6CD7"], "T1-3", "ES-101", None, "E#3@15"),
    (["B6EF1"], "T1-5", "ES-101", None, "E#3@15"),
    (["97FFC", "98000"], "CE-1", "ES-200", "4#3", "E#2@15"),
    (["9802D", "98031"], "CE-2", "ES-200", "6#3", "E#2@15"),
    (["98056", "9805A"], "CE-3", "ES-200", "6#4", "E#3@14"),
    (["A8E8E", "A8E8F"], "CI", "ES-200", "4#3", "E#2@15"),
    (["A8EA5", "A8EA6"], "CI", "ES-200", "6#3", "E#2@15"),
    (["A8EC0", "A8EC1"], "CI", "ES-200", "4#3", "E#2@15"),
    (["980E0", "980E1"], "CR-1", "ES-200", "4#3", "E#2@15"),
    (["980F6"], "CR-2", "ES-200", None, "E#2@15"),
    (["9810F", "98110"], "CR-3", "ES-200", "6#3", "E#2@15"),
    (["4C850"], "T2-1", "ES-201", None, "E#3@15"),
    (["A926A"], "T2-2", "ES-201", None, "E#3@15"),
    (["4CD42", "A9E5E"], "T2-8", "ES-201", None, "E#3@16"),
    (["ACA29"], "T2-14", "ES-202", None, "E#3@15"),
    (["ACAEF"], "T2-15", "ES-202", None, "E#3@15"),
    (["8A155", "8A159"], "CE-1", "ES-300", "4#3", "E#2@15"),
    (["8A1AF", "8A1B3"], "CE-3", "ES-300", "6#4", "E#3@14"),
    (["8A2C8", "8A2CC"], "CE-4", "ES-300", "4#4", None),
    (["8A2A1", "8A2A5"], "CE-5", "ES-300", "4#3", "E#3@16"),
    (["A8DD8", "A8DD9"], "CI", "ES-300", None, None),
    (["A8DEF", "A8DF0"], "CI", "ES-300", None, None),
    (["8E2DE", "8E2DF"], "CR-1", "ES-300", "4#3", "E#2@15"),
    (["8E2F4"], "CR-2", "ES-300", None, "E#2@15"),
    (["8E37D", "8E37E"], "CR-3", "ES-300", "6#3", "E#2@15"),
    (["8F540"], "T3-1A", "ES-301", None, "E#4@15"),
    (["4B94F"], "T3-4", "ES-301", None, "E#3@18"),
    (["90095"], "T3-18", "ES-302", None, "E#3@15"),
    (["4EED6", "4EEDA"], "CE-1", "ES-400", "4#3", "E#2@15"),
    (["4EF07", "4EF0B"], "CE-2", "ES-400", "6#3", "E#2@15"),
    (["72B71", "72B75"], "CE-3", "ES-400", "6#4", "E#3@14"),
    (["4EFBB", "4EFBC"], "CI", "ES-400", "4#3", "E#2@15"),
    (["4EFDC", "4EFDD"], "CI", "ES-400", "6#3", "E#2@15"),
    (["4EFF7", "4EFF8"], "CI", "ES-400", "4#3", "E#2@15"),
    (["4F0D2", "4F0D3"], "CR-1", "ES-400", "4#3", "E#2@15"),
    (["4F0E9"], "CR-2", "ES-400", None, "E#2@15"),
]


def test_every_marina_stack_under_a_section_is_the_drawings(marina):
    inv, ids = marina
    manija = {i: h for h, i in ids.items()}
    leidas = sorted(
        ([manija[i] for i in s.entidades], s.mark, s.hoja, s.rebar, s.stirrups)
        for s in inv.specs
        if s.metodo == "pila" and s.source_text.endswith("bajo su sección")
    )
    assert leidas == sorted(_PILAS)
    for s in inv.specs:  # lo que lee una pila ya no es «sin dueño»
        if s.metodo == "pila":
            assert not {r.entidad_id for r in inv.rechazos} & set(s.entidades)


@pytest.mark.parametrize("handle", ["B6B0A", "B8F9A", "A955A", "4C584", "901BC", "4B692"])
def test_claimed_or_doubtful_stacks_stay_unread(marina, handle):
    # T1-1 «2E#3@15» y T1-6 «E#3@14» (sus secciones, reclamadas: sus lados pasan sus esquinas,
    # R118), T2-4 «2E#3» (reclamada, en su esquina) y T3-17 «E#3» (junto a su esquina; su alzado
    # escribe «@12»): nadie los lee; siguen siendo bloqueos «posible» de su título. R189: T3-19
    # «E#3» y T4-4 «E#3@15» van bajo su sección pero a un lado (menos de la mitad de su texto sobre
    # ella): una sección sólo toma de enfrente; antes se leían y su campo se vetaba.
    inv, ids = marina
    assert _leida_por(inv, ids[handle]) == set()
    assert _posibles(inv, ids[handle])


def test_each_ci_variant_reads_its_own_armado(marina):
    # R168 + R147: cada variante de CI lee el armado bajo su propia sección.
    from klave_engine.estructura.definiciones import construir_definiciones

    inv, _ids = marina
    d = construir_definiciones(inv, C)[0]["CI"]
    leidas = {
        v.para_muro_cm: (
            [(g.cantidad, g.numero) for g in v.longitudinales.valor],
            [(j.cantidad, j.numero, j.zonas[0].separacion_m) for j in v.estribos.valor],
            v.longitudinales.fuente,
        )
        for v in d.variantes
    }
    assert leidas == {
        15.0: ([(4, "3")], [(1, "2", 0.15)], "detalle"),
        20.0: ([(4, "3")], [(1, "2", 0.15)], "detalle"),
        30.0: ([(6, "3")], [(1, "2", 0.15)], "detalle"),
    }


# R196, R209: las pilas en duda, con su geometría (de su sección a cada renglón, del lado que lee;
# de la otra sección, del lado de su título).
_EN_DUDA = [
    # CE-1 y CE-2 en ES-100: a 0.71 / 0.90 de su sección; CE-3, bajo ellas (su título en medio),
    # las alcanza a 0.82.
    ("B79B2", "CE-1"), ("B79B6", "CE-1"), ("B79E3", "CE-2"), ("B79E7", "CE-2"),
    # CE-2 en ES-300: 0.71 / 0.90; CE-4, debajo, a 0.95.
    ("8A186", "CE-2"), ("8A18A", "CE-2"),
    # CI de 20 cm en ES-300: «E#2@15» A8E0B a 0.569 de su sección y a 0.572 de la de 30 cm.
    ("A8E0A", "CI"), ("A8E0B", "CI"),
]  # fmt: skip


@pytest.mark.parametrize("handle,marca", _EN_DUDA)
def test_a_stack_another_section_reaches_about_as_near_is_in_doubt(marina, handle, marca):
    inv, ids = marina
    assert _leida_por(inv, ids[handle]) == set()
    assert marca in _posibles(inv, ids[handle])


# R205b: T2-1 en ES-201: «E#3@15» a 0.38 de su sección; la de T2-4 (reclamada: nunca se lee) la
# alcanza a 2.68: compite sólo por la distancia, y T2-1 está claramente más cerca.
_RECUPERADAS = [("4C850", "T2-1", None)]


@pytest.mark.parametrize("handle,marca,otra", _RECUPERADAS)
def test_a_stack_the_other_section_does_not_need_is_read(marina, handle, marca, otra):
    inv, ids = marina
    assert _leida_por(inv, ids[handle]) == {marca}
    if otra is not None:
        (pila,) = [s for s in inv.specs if s.metodo == "pila" and ids[handle] in s.entidades]
        assert (
            f"pila bajo su sección: se lee como de {marca}; antes se atribuía también a {otra}"
            in (pila.avisos)
        )
