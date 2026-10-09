"""El armado como estructura: cada `#` y cada `@` del texto queda leído o avisado, nunca perdido."""

import random
import re
from collections import Counter

import pytest
from klave_engine.costing.steel import BAR_KG_PER_M
from klave_engine.estructura.armado import (
    FAMILIAS_CON_PARRILLA,
    NUMEROS,
    Armado,
    GrupoVarillas,
    JuegoEstribos,
    Parrilla,
    Zona,
    parsear_armado,
    texto_armado,
    texto_estribos,
    texto_longitudinal,
    texto_parrillas,
)

E, G = "estribo", "grapa"


# Los casos del plan (las cadenas de Marina que la ronda nombra).
PLAN = [
    (["8#8"], "columna", [(8, "8")], []),
    (["4#4+2#3"], "castillo", [(4, "4"), (2, "3")], []),
    (["8#8+4#6"], "columna", [(8, "8"), (4, "6")], []),
    (["REFUERZO 1#3"], "castillo", [(1, "3")], []),
    (["E#2@15"], "castillo", [], [(E, 1, "2", [("todo", 0.15)])]),
    (
        ["EYG#3@15"],
        "castillo",
        [],
        [(E, 1, "3", [("todo", 0.15)]), (G, 1, "3", [("todo", 0.15)])],
    ),
    (["2E#3@20"], "castillo", [], [(E, 2, "3", [("todo", 0.20)])]),
    (
        ["2E#3EXT@10", "CENTRO@20"],
        "columna",
        [],
        [(E, 2, "3", [("extremos", 0.10), ("centro", 0.20)])],
    ),
    (
        ["4E#3EXT@10", "CENTRO@20"],
        "castillo",
        [],
        [(E, 4, "3", [("extremos", 0.10), ("centro", 0.20)])],
    ),
    (
        ["2E+1G#3EXT@10", "CENTRO@15"],
        "castillo",
        [],
        [
            (E, 2, "3", [("extremos", 0.10), ("centro", 0.15)]),
            (G, 1, "3", [("extremos", 0.10), ("centro", 0.15)]),
        ],
    ),
    (["E#3"], "castillo", [], [(E, 1, "3", [])]),
    (["G#3@14"], "castillo", [], [(G, 1, "3", [("todo", 0.14)])]),
    (["DALA 15x30 4#3,E#2@20"], "dala", [(4, "3")], [(E, 1, "2", [("todo", 0.20)])]),
    (["4#8 + 12#6 3E#3 VER CORTE"], "pilote", [(4, "8"), (12, "6")], [(E, 3, "3", [])]),
]


@pytest.mark.parametrize("textos,familia,long,estr", PLAN)
def test_marina_strings(textos, familia, long, estr):
    a = parsear_armado(textos, familia)
    assert [(g.cantidad, g.numero) for g in a.longitudinales] == long
    assert [
        (j.tipo, j.cantidad, j.numero, [(z.tramo, z.separacion_m) for z in j.zonas])
        for j in a.estribos
    ] == estr
    assert a.avisos == []


def test_ver_corte_is_a_reference():
    a = parsear_armado(["2E#3 VER CORTE"], "pilote")
    assert a.estribos[0].referencia == "VER CORTE" and a.estribos[0].zonas == []


def test_mesh_only_where_meshes_belong():
    muro = parsear_armado(["#4@20"], "muro_concreto")
    assert [(p.numero, p.separacion_m, p.lecho, p.sentidos) for p in muro.parrillas] == [
        ("4", 0.20, "unico", None)
    ]
    k = parsear_armado(["#4@20"], "castillo")
    assert k.parrillas == [] and k.avisos and "#4@20" in k.avisos[0]


def test_slab_layers():
    a = parsear_armado(["LOSA MACIZA DOBLEMENTE ARMADA H=20 LS #4@20 A/S LI #4@20 A/S"], "losa")
    assert [(p.lecho, p.sentidos) for p in a.parrillas] == [("sup", "ambos"), ("inf", "ambos")]


def test_two_digit_bars():
    assert parsear_armado(["6#10+2#12"], "columna").longitudinales[1].numero == "12"


def test_nothing_lost_silently():
    a = parsear_armado(["6#4 E#3@1S"], "castillo")
    assert a.longitudinales[0].cantidad == 6 and any("@1S" in w for w in a.avisos)
    b = parsear_armado(["8#9"], "columna")  # #9 is not a Mexican bar number
    assert b.longitudinales == [] and b.avisos


@pytest.mark.parametrize(
    "textos,familia",
    [
        (["4#5+2#4", "2E#3@15"], "castillo"),
        (["2E+1G#3EXT@10", "CENTRO@15"], "castillo"),
        (["EYG#3@20"], "castillo"),
        (["LS #4@20 A/S LI #4@20 A/S"], "losa"),
        (["4#8 + 12#6 3E#3 VER CORTE"], "pilote"),
    ],
)
def test_round_trip(textos, familia):
    a = parsear_armado(textos, familia)
    assert parsear_armado([texto_armado(a)], familia).model_dump(
        exclude={"texto_original"}
    ) == a.model_dump(exclude={"texto_original"})


def test_canonical_texts():
    a = parsear_armado(["4#5+2#4", "2E+1G#3EXT@10", "CENTRO@15"], "castillo")
    assert texto_longitudinal(a) == "4#5+2#4"
    assert texto_estribos(a) == "2E+1G#3 EXT@10 CENTRO@15"
    assert texto_estribos(parsear_armado(["EYG#3@15"], "castillo")) == "EYG#3@15"


# ------------------------------------------------------------------ más allá del plan


def test_numeros_are_the_steel_table_keys_in_order():
    # El parser no importa costing.steel (costing.steel lo importará a él): la tupla no
    # puede separarse de la tabla de pesos.
    assert NUMEROS == tuple(BAR_KG_PER_M)


def test_familias_con_parrilla():
    assert FAMILIAS_CON_PARRILLA == frozenset(
        {"losa", "muro", "muro_concreto", "zapata", "dado", "losa_cimentacion"}
    )


# El resto de lo que Marina escribe (verificado contra el DXF crudo), cada uno con su estructura.
MARINA = [
    (["10#8"], "columna", [(10, "8")], []),
    (["4#5+2#4"], "castillo", [(4, "5"), (2, "4")], []),
    (["6#8+6#6"], "castillo", [(6, "8"), (6, "6")], []),
    (["1#4+1#3"], "castillo", [(1, "4"), (1, "3")], []),
    (["REFUERZO 12#6"], "pilote", [(12, "6")], []),
    (["REFUERZO 4#8+4#4"], "pilote", [(4, "8"), (4, "4")], []),
    (["2 VARILLAS #5"], "castillo", [(2, "5")], []),
    (["EYG#2@15"], "castillo", [], [(E, 1, "2", [("todo", 0.15)]), (G, 1, "2", [("todo", 0.15)])]),
    (["EYG#3@20"], "castillo", [], [(E, 1, "3", [("todo", 0.20)]), (G, 1, "3", [("todo", 0.20)])]),
    (["2E#3@15"], "castillo", [], [(E, 2, "3", [("todo", 0.15)])]),
    (["3E#3@20"], "castillo", [], [(E, 3, "3", [("todo", 0.20)])]),
    (["2E#2@15"], "castillo", [], [(E, 2, "2", [("todo", 0.15)])]),
    (
        ["3E#3EXT@10", "CENTRO@20"],
        "castillo",
        [],
        [(E, 3, "3", [("extremos", 0.10), ("centro", 0.20)])],
    ),
    (["E#4"], "columna", [], [(E, 1, "4", [])]),
    (["2E#4"], "columna", [], [(E, 2, "4", [])]),
    (["G#3"], "castillo", [], [(G, 1, "3", [])]),
    (["CADENA DE ENRASE 15x25 4#3 E#2@15"], "dala", [(4, "3")], [(E, 1, "2", [("todo", 0.15)])]),
    # Un MTEXT con su salto de línea adentro: el mismo armado del pilote.
    (["4#8 + 12#6\n3E#3 VER CORTE"], "pilote", [(4, "8"), (12, "6")], [(E, 3, "3", [])]),
    # Una pila completa de un castillo: longitudinales arriba, estribos abajo.
    (
        ["6#8+6#6", "4E#3EXT@10", "CENTRO@20"],
        "castillo",
        [(6, "8"), (6, "6")],
        [(E, 4, "3", [("extremos", 0.10), ("centro", 0.20)])],
    ),
]


# Cada texto de Marina con «#», «@» o «Ø» (modelo y bloques) que se lee sin aviso;
# barrido del DXF crudo, 2026-10-08. Las mallas sueltas van como losa.
MARINA_BARRIDO = [
    ("#3@12", "losa"),
    ("#3@13", "losa"),
    ("#3@15", "losa"),
    ("#3@20", "losa"),
    ("#4@10", "losa"),
    ("#4@13", "losa"),
    ("#4@15", "losa"),
    ("#4@18", "losa"),
    ("#4@20", "losa"),
    ("#6@20", "losa"),
    ("1#3", "castillo"),
    ("1#4", "castillo"),
    ("1#4+1#3", "castillo"),
    ("1#5", "castillo"),
    ("1#6", "castillo"),
    ("1#8", "castillo"),
    ("10#6", "castillo"),
    ("10#8", "castillo"),
    ("2#3", "castillo"),
    ("2#4", "castillo"),
    ("2#6", "castillo"),
    ("2#6+1#4", "castillo"),
    ("2#6+2#4", "castillo"),
    ("2#8", "castillo"),
    ("2#8+2#6", "castillo"),
    ("2E#2@15", "castillo"),
    ("2E#3", "castillo"),
    ("2E#3 VER CORTE", "castillo"),
    ("2E#3@10", "castillo"),
    ("2E#3@15", "castillo"),
    ("2E#3@20", "castillo"),
    ("2E#3EXT@10", "castillo"),
    ("2E#4", "castillo"),
    ("2E#4@15", "castillo"),
    ("2E+1G#3EXT@10", "castillo"),
    ("3#3", "castillo"),
    ("3#4", "castillo"),
    ("3#6", "castillo"),
    ("3#8", "castillo"),
    ("3E#3", "castillo"),
    ("3E#3@20", "castillo"),
    ("3E#3EXT@10", "castillo"),
    ("4#3", "castillo"),
    ("4#4", "castillo"),
    ("4#4+2#3", "castillo"),
    ("4#5", "castillo"),
    ("4#5+2#4", "castillo"),
    ("4#5+4#4", "castillo"),
    ("4#6", "castillo"),
    ("4#6+2#4", "castillo"),
    ("4#6+4#4", "castillo"),
    ("4#8", "castillo"),
    ("4#8 + 12#6\n3E#3 VER CORTE", "castillo"),
    ("4#8+4#6", "castillo"),
    ("4E#3EXT@10", "castillo"),
    ("5#6", "castillo"),
    ("5#8", "castillo"),
    ("6#3", "castillo"),
    ("6#4", "castillo"),
    ("6#5+4#4", "castillo"),
    ("6#6+4#4", "castillo"),
    ("6#8", "castillo"),
    ("6#8+6#6", "castillo"),
    ("7#8", "castillo"),
    ("8#3", "castillo"),
    ("8#4", "castillo"),
    ("8#6", "castillo"),
    ("8#8", "castillo"),
    ("8#8+4#6", "castillo"),
    ("CADENA DE ENRASE 15x25 4#3 E#2@15", "castillo"),
    ("E#2@15", "castillo"),
    ("E#3", "castillo"),
    ("E#3@12", "castillo"),
    ("E#3@14", "castillo"),
    ("E#3@15", "castillo"),
    ("E#3@16", "castillo"),
    ("E#3@18", "castillo"),
    ("E#3@20", "castillo"),
    ("E#4", "castillo"),
    ("E#4@15", "castillo"),
    ("E#4@20", "castillo"),
    ("EYG#2@15", "castillo"),
    ("EYG#3@15", "castillo"),
    ("EYG#3@20", "castillo"),
    ("G#3", "castillo"),
    ("G#3@14", "castillo"),
    ("LOSA MACIZA DOBLEMENTE ARMADA H=20\nLS #4@20 A/S\nLI #4@20 A/S", "losa"),
    ("REFUERZO 1#3", "castillo"),
    ("REFUERZO 1#4", "castillo"),
    ("REFUERZO 12#6", "castillo"),
    ("REFUERZO 4#5+4#4", "castillo"),
    ("REFUERZO 4#6+4#4", "castillo"),
    ("REFUERZO 4#8+4#4", "castillo"),
]


@pytest.mark.parametrize("textos,familia,long,estr", MARINA)
def test_the_rest_of_marina(textos, familia, long, estr):
    a = parsear_armado(textos, familia)
    assert [(g.cantidad, g.numero) for g in a.longitudinales] == long
    assert [
        (j.tipo, j.cantidad, j.numero, [(z.tramo, z.separacion_m) for z in j.zonas])
        for j in a.estribos
    ] == estr
    assert a.parrillas == [] and a.avisos == []


@pytest.mark.parametrize("textos,familia", [(t, f) for t, f, _, _ in MARINA])
def test_round_trip_of_every_marina_string(textos, familia):
    a = parsear_armado(textos, familia)
    b = parsear_armado([texto_armado(a)], familia)
    assert b.model_dump(exclude={"texto_original"}) == a.model_dump(exclude={"texto_original"})


def test_a_bar_number_before_a_stirrup_is_never_taken_as_its_count():
    # «4#3 E#2@15»: el 3 es el número de la varilla, no «3 estribos».
    a = parsear_armado(["4#3 E#2@15"], "dala")
    assert [(g.cantidad, g.numero) for g in a.longitudinales] == [(4, "3")]
    assert [(j.cantidad, j.numero) for j in a.estribos] == [(1, "2")]
    # Ni la medida de una sección: «15X30 E#2@20» no son 0 estribos.
    b = parsear_armado(["15X30 E#2@20"], "dala")
    assert [(j.cantidad, j.numero) for j in b.estribos] == [(1, "2")] and b.avisos == []


def test_stirrup_and_grapa_spellings():
    for texto in ("EYG#3@15", "E Y G #3@15", "E+G#3@15", "ESTRIBOS Y GRAPAS #3@15", "eyg#3@15"):
        a = parsear_armado([texto], "castillo")
        assert [(j.tipo, j.cantidad) for j in a.estribos] == [(E, 1), (G, 1)], texto
        assert a.parrillas == [] and a.avisos == [], texto
    assert [j.tipo for j in parsear_armado(["EST. #3@20"], "castillo").estribos] == [E]
    a = parsear_armado(["E#3@15 G#2@20"], "castillo")
    assert [(j.tipo, j.numero, j.zonas[0].separacion_m) for j in a.estribos] == [
        (E, "3", 0.15),
        (G, "2", 0.20),
    ]


def test_diameter_and_percent_codes_are_normalized():
    a = parsear_armado(["4%%C5+2Ø4 E%%c3@20"], "castillo")
    assert [(g.cantidad, g.numero) for g in a.longitudinales] == [(4, "5"), (2, "4")]
    assert [(j.numero, j.zonas[0].separacion_m) for j in a.estribos] == [("3", 0.20)]
    assert a.avisos == []
    # «%%%» es «%»; una cifra que nadie leyó se avisa aunque esté en otra línea.
    c = parsear_armado(["TRASLAPE AL 50%%%", "4%%C5"], "castillo")
    assert len(c.longitudinales) == 1 and c.avisos == ["sin leer: «50%»"]
    # Lo que sigue a una pieza y no es contexto la deja sin leer, y el aviso cita el plano.
    b = parsear_armado(["E%%c3@20 100%%%"], "castillo")
    assert b.estribos == [] and b.avisos == ["sin leer: «EØ3@20 100%»"]


def test_mtext_paragraph_break_is_a_line_boundary():
    a = parsear_armado(["2E#3EXT@10\\PCENTRO@20"], "castillo")
    assert [(z.tramo, z.separacion_m) for z in a.estribos[0].zonas] == [
        ("extremos", 0.10),
        ("centro", 0.20),
    ]
    assert a.avisos == []


def test_a_bare_spacing_on_the_next_line_belongs_to_the_stirrup_above():
    a = parsear_armado(["E#3", "@20"], "castillo")
    assert [(z.tramo, z.separacion_m) for z in a.estribos[0].zonas] == [("todo", 0.20)]
    assert a.avisos == []


def test_zones_and_reference_together():
    a = parsear_armado(["2E#3@15 VER CORTE"], "pilote")
    j = a.estribos[0]
    assert [(z.tramo, z.separacion_m) for z in j.zonas] == [
        ("todo", 0.15)
    ] and j.referencia == "VER CORTE"
    assert texto_estribos(a) == "2E#3@15 VER CORTE"
    assert parsear_armado(["E#3", "VER DETALLE"], "trabe").estribos[0].referencia == "VER DETALLE"


def test_ends_without_centre_keep_only_the_ends():
    a = parsear_armado(["2E#3EXT@10"], "castillo")
    assert [(z.tramo, z.separacion_m) for z in a.estribos[0].zonas] == [("extremos", 0.10)]
    assert a.avisos == [] and texto_estribos(a) == "2E#3 EXT@10"


def test_a_centre_with_no_stirrup_is_reported():
    a = parsear_armado(["CENTRO@20"], "castillo")
    assert a.estribos == [] and a.avisos == ["sin leer: «CENTRO@20»"]


def test_unknown_bar_numbers_are_reported_never_rounded():
    for texto, simbolo in (("8#9", "#9"), ("4#1", "#1"), ("4#11", "#11"), ("2#25", "#25")):
        a = parsear_armado([texto], "columna")
        assert a.longitudinales == [] and len(a.avisos) == 1, texto
        assert texto in a.avisos[0] and f"no hay varilla del {simbolo}" in a.avisos[0], texto
    # Pulgadas no se convierten: «3/8» no es el #3 sin más.
    c = parsear_armado(['4Ø3/8"'], "castillo")
    assert c.longitudinales == [] and c.avisos == ['sin leer: «4Ø3/8"»']
    # Un decimal que no es 2.5 tampoco: «#3.5» no se lee como #3.
    d = parsear_armado(["4#3.5"], "castillo")
    assert d.longitudinales == [] and d.avisos


def test_half_bar():
    a = parsear_armado(["4#2.5 E#2@20"], "castillo")
    assert [(g.cantidad, g.numero) for g in a.longitudinales] == [(4, "2.5")]
    assert [(j.cantidad, j.numero) for j in a.estribos] == [(1, "2")] and a.avisos == []


def test_spacing_with_decimals_and_units():
    a = parsear_armado(["E#3@12.5"], "castillo")
    assert a.estribos[0].zonas[0].separacion_m == 0.125 and texto_estribos(a) == "E#3@12.5"
    b = parsear_armado(["E#3@20 CM"], "castillo")
    assert b.estribos[0].zonas[0].separacion_m == 0.20 and b.avisos == []
    c = parsear_armado(["E#3@0"], "castillo")  # una separación nula no es separación
    assert c.estribos == [] and c.avisos == ["sin leer: «E#3@0»"]


def test_a_count_with_a_spacing_is_neither_bars_nor_mesh():
    # «4#4@20» no dice qué es: se avisa entero, no se toma la malla dejando el 4 suelto.
    for familia in ("castillo", "muro"):
        a = parsear_armado(["4#4@20"], familia)
        assert a.longitudinales == [] and a.parrillas == [], familia
        assert a.avisos == ["sin leer: «4#4@20»"], familia


def test_a_bar_glued_to_more_text_is_reported_not_trimmed():
    # Marina: «2#5X150 SUPERIOR E» (dos varillas de 150 cm, refuerzo de un hueco): leer sólo
    # «2#5» callaría la longitud y haría pasar el refuerzo por longitudinales del elemento.
    a = parsear_armado(["2#5X150 SUPERIOR E"], "castillo")
    assert a.longitudinales == [] and a.avisos == ["sin leer: «2#5X150 SUPERIOR E»"]


def test_a_bar_note_with_prose_after_it_is_reported_whole():
    # Marina: dos varillas ancladas con epóxico son una nota de anclaje, no el refuerzo
    # longitudinal de un elemento; lo que sigue al «#5» no es contexto.
    texto = "2 VARILLAS #5 ANCLADA AL MURO O CADENA CON ANCHORFIX 3001 DE SIKA"
    a = parsear_armado([texto], "castillo")
    assert a.vacio() and a.avisos == [f"sin leer: «{texto}»"]


def test_trabe_distributions_are_reported_whole():
    # Marina escribe la distribución de estribos de una trabe como «1@6,8@10,10@15»: no es
    # gramática de esta ronda; se avisa completa, una vez.
    a = parsear_armado(["1@6,8@10,10@15"], "trabe")
    assert a.vacio() and a.avisos == ["sin leer: «1@6,8@10,10@15»"]


def test_mesh_on_a_non_mesh_family_names_it_with_its_article():
    a = parsear_armado(["LS #4@20 A/S"], "columna")
    assert a.parrillas == [] and a.avisos == ["malla «LS #4@20 A/S» en una columna: no se toma"]
    assert parsear_armado(["#4@20"], "castillo").avisos == [
        "malla «#4@20» en un castillo: no se toma"
    ]


def test_mesh_layer_and_direction_spellings():
    a = parsear_armado(["#4@20 A/S L.S. Y L.I."], "losa")
    assert [(p.numero, p.lecho, p.sentidos) for p in a.parrillas] == [
        ("4", "sup", "ambos"),
        ("4", "inf", "ambos"),
    ]
    assert a.avisos == []
    b = parsear_armado(
        ["LECHO SUPERIOR #4@15 AMBOS SENTIDOS", "LECHO INFERIOR #3@20"], "losa_cimentacion"
    )
    assert [(p.numero, p.separacion_m, p.lecho, p.sentidos) for p in b.parrillas] == [
        ("4", 0.15, "sup", "ambos"),
        ("3", 0.20, "inf", None),
    ]
    c = parsear_armado(["L.S. #4@20 A/S L.I. #3@20"], "zapata")
    assert [(p.numero, p.lecho) for p in c.parrillas] == [("4", "sup"), ("3", "inf")]
    d = parsear_armado(["#3@20 EN X"], "dado")
    assert [(p.lecho, p.sentidos) for p in d.parrillas] == [("unico", "x")]


@pytest.mark.parametrize(
    "textos,familia",
    [
        (["#4@20"], "muro"),
        (["#4@20 A/S L.S. Y L.I."], "losa"),
        (["#3@20 EN Y"], "zapata"),
        (["E#3@12.5"], "castillo"),
        (["2E#3@15 VER CORTE"], "pilote"),
        (["2E#3EXT@10"], "castillo"),
        (["E#3@15 G#2@20"], "castillo"),
        (["2 LIGAS #2@20"], "columna"),
    ],
)
def test_round_trip_beyond_marina(textos, familia):
    a = parsear_armado(textos, familia)
    assert not a.vacio() and a.avisos == []
    b = parsear_armado([texto_armado(a)], familia)
    assert b.model_dump(exclude={"texto_original"}) == a.model_dump(exclude={"texto_original"})


def test_renders():
    a = Armado(
        estribos=[
            JuegoEstribos(
                tipo="estribo",
                cantidad=1,
                numero="3",
                zonas=[Zona(tramo="todo", separacion_m=0.15)],
            ),
            JuegoEstribos(
                tipo="grapa", cantidad=2, numero="3", zonas=[Zona(tramo="todo", separacion_m=0.15)]
            ),
            JuegoEstribos(tipo="grapa", cantidad=1, numero="2", referencia="VER CORTE"),
        ],
        parrillas=[
            Parrilla(numero="4", separacion_m=0.20, lecho="sup", sentidos="ambos"),
            Parrilla(numero="3", separacion_m=0.15, lecho="inf", sentidos=None),
        ],
    )
    assert texto_longitudinal(a) == ""
    assert texto_estribos(a) == "1E+2G#3@15 G#2 VER CORTE"
    assert texto_parrillas(a) == "LS #4@20 A/S LI #3@15"
    assert texto_armado(a) == "1E+2G#3@15 G#2 VER CORTE LS #4@20 A/S LI #3@15"
    unicas = Armado(
        parrillas=[Parrilla(numero="4", separacion_m=0.2, lecho="unico", sentidos=None)]
    )
    assert texto_parrillas(unicas) == "#4@20"
    assert texto_armado(Armado()) == ""


def test_texto_original_and_vacio():
    a = parsear_armado(["SECCIÓN 20x40", " 4#4 "], "castillo")
    assert a.texto_original == "SECCIÓN 20x40 | 4#4" and not a.vacio()
    vacio = parsear_armado(["SECCIÓN 20x40", "COLUMNA"], "columna")
    assert vacio.vacio() and vacio.avisos == []
    assert parsear_armado([], "castillo").vacio()


def test_formas_are_left_for_later():
    a = parsear_armado(["4#4 2E#3@15"], "castillo")
    assert a.estribos[0].formas == [] and a.estribos[0].formas_fuente is None
    assert [g.posicion for g in a.longitudinales] == [None]


# ------------------------------------------------------------------ ronda de correcciones 1
# El contrato es «leído o avisado»: nunca medio leído.

# Lo que un texto dice, contado sin el parser: grupos «n#m», números «#m» y separaciones «@s».
_BARRAS_RE = re.compile(r"(?<![\d.])(\d+)\s*(?:VARILLAS|VARS?\.?|V)?\s*#\s*(\d+(?:\.\d+)?)")
_NUMEROS_RE = re.compile(r"#\s*(\d+(?:\.\d+)?)")
_SEPARACIONES_RE = re.compile(r"@\s*(\d+(?:\.\d+)?)")


def _lo_que_dice(texto: str) -> tuple[Counter, Counter, Counter]:
    t = texto.upper().replace("%%C", "#").replace("Ø", "#")
    return (
        Counter(_BARRAS_RE.findall(t)),
        Counter(_NUMEROS_RE.findall(t)),
        Counter(float(s) for s in _SEPARACIONES_RE.findall(t)),
    )


def _casos_de_marina():
    casos = [(t, f) for t, f, _, _ in PLAN] + [(t, f) for t, f, _, _ in MARINA]
    return casos + [([t], f) for t, f in MARINA_BARRIDO]


@pytest.mark.parametrize("textos,familia", _casos_de_marina())
def test_the_render_says_the_same_bars_sizes_and_spacings_as_the_drawing(textos, familia):
    a = parsear_armado(textos, familia)
    assert a.avisos == []
    assert _lo_que_dice(texto_armado(a)) == _lo_que_dice(" ".join(textos))


@pytest.mark.parametrize(
    "textos,familia,pieza",
    [
        (["E#3@12/14/16/18"], "castillo", "E#3@12/14/16/18"),
        (["E#3@15/20"], "castillo", "E#3@15/20"),
        (["E#3@15,20"], "castillo", "E#3@15,20"),
        (["E#3@15-20"], "castillo", "E#3@15-20"),
        (["E#3@12.5/15"], "castillo", "E#3@12.5/15"),
        (["E#3@6,8@10,10@15"], "trabe", "E#3@6,8@10,10@15"),
        # Ronda 2: la unidad no abre paso, ni una palabra que empiece con E o G, ni el espacio.
        (["E#3@15 CM/20"], "castillo", "E#3@15 CM/20"),
        (["E#3@15 CM,20"], "castillo", "E#3@15 CM,20"),
        (["E#3@15 CM, 20 CM"], "castillo", "E#3@15 CM, 20 CM"),
        (["E#3@10,15 EN CENTRO"], "castillo", "E#3@10,15 EN CENTRO"),
        (["E#3@15,20 EN EXTREMOS"], "castillo", "E#3@15,20 EN EXTREMOS"),
        (["E#3@15,2 GANCHOS"], "castillo", "E#3@15,2 GANCHOS"),
        (["E#3@15 /20"], "castillo", "E#3@15 /20"),
        (["E#3@15 / 20"], "castillo", "E#3@15 / 20"),
        (["E#3@15 - 20"], "castillo", "E#3@15 - 20"),
        (["E#3@15 ,20"], "castillo", "E#3@15 ,20"),
        (["E#3@15 Y 20"], "castillo", "E#3@15 Y 20"),
        (["E#3@15, 20"], "castillo", "E#3@15, 20"),
        (["E#3@20 MMS"], "castillo", "E#3@20 MMS"),
        (["E#3@15", "/20"], "castillo", "E#3@15 | /20"),
    ],
)
def test_a_spacing_with_more_after_it_is_reported_whole(textos, familia, pieza):
    # Leído entero o avisado entero: el juego no se queda con una separación que no es la suya.
    a = parsear_armado(textos, familia)
    assert a.estribos == [] and a.avisos == [f"sin leer: «{pieza}»"]


@pytest.mark.parametrize("texto", ["#4@20/25", "#4@20 CM/25", "#4@20 /25", "#4@20,15 EN X"])
def test_a_mesh_spacing_with_more_after_it_is_reported_whole(texto):
    a = parsear_armado([texto], "losa")
    assert a.parrillas == [] and a.avisos == [f"sin leer: «{texto}»"]


@pytest.mark.parametrize("extremos", ["2E#3EXT@10/12", "2E#3EXT@10 /12"])
def test_ends_with_more_after_them_are_reported_and_so_is_the_centre(extremos):
    a = parsear_armado([extremos, "CENTRO@15"], "castillo")
    assert a.estribos == []
    assert a.avisos == [f"sin leer: «{extremos}»", "sin leer: «CENTRO@15»"]


def test_a_bar_group_after_a_spacing_and_a_comma_is_still_read():
    for texto in ("E#2@20,4#3", "E#2@20, 4 VARS #3"):
        a = parsear_armado([texto], "dala")
        assert [(g.cantidad, g.numero) for g in a.longitudinales] == [(4, "3")], texto
        assert [(j.numero, j.zonas[0].separacion_m) for j in a.estribos] == [("2", 0.20)], texto
        assert a.avisos == [], texto
    b = parsear_armado(["E#2@20,2G#3@15"], "castillo")
    assert [(j.tipo, j.cantidad, j.zonas[0].separacion_m) for j in b.estribos] == [
        (E, 1, 0.20),
        (G, 2, 0.15),
    ]
    assert b.avisos == []


@pytest.mark.parametrize(
    "texto,juegos",
    [
        ("G+E#3@15", [(E, 1), (G, 1)]),
        ("G Y E #3@15", [(E, 1), (G, 1)]),
        ("2G+1E#3@15", [(E, 1), (G, 2)]),
        ("10E#3@15", [(E, 10)]),
        ("12E+2G#3@15", [(E, 12), (G, 2)]),
        ("12LIGAS #2@20", [("liga", 12)]),
        ("E. #3@20", [(E, 1)]),
        ("ESTRIBOS DE #3@20", [(E, 1)]),
    ],
)
def test_every_stirrup_head_is_read_whole_never_rerouted_to_a_mesh(texto, juegos):
    for familia in ("castillo", "muro"):
        a = parsear_armado([texto], familia)
        assert [(j.tipo, j.cantidad) for j in a.estribos] == juegos, familia
        assert a.parrillas == [] and a.avisos == [], familia
        b = parsear_armado([texto_armado(a)], familia)
        assert b.model_dump(exclude={"texto_original"}) == a.model_dump(exclude={"texto_original"})
        assert _lo_que_dice(texto_armado(a)) == _lo_que_dice(texto)


def test_a_grapa_first_set_renders_canonically():
    assert texto_estribos(parsear_armado(["2G+1E#3@15"], "castillo")) == "1E+2G#3@15"
    assert texto_estribos(parsear_armado(["G+E#3@15"], "castillo")) == "EYG#3@15"


@pytest.mark.parametrize(
    "texto,pieza",
    [
        ("100E#3@15", "100E#3@15"),
        ("ESTRIBOS: #3@20", "ESTRIBOS: #3@20"),
        ("X#4@20", "X#4@20"),
    ],
)
def test_a_mesh_glued_to_or_after_a_stirrup_word_is_reported_whole(texto, pieza):
    for familia in ("castillo", "muro"):
        a = parsear_armado([texto], familia)
        assert a.vacio() and a.avisos == [f"sin leer: «{pieza}»"], familia


@pytest.mark.parametrize(
    "texto,pieza",
    [
        ("4 #4@20", "4 #4@20"),
        ("4 VARS #4@20", "4 VARS #4@20"),
        ("4#4@20", "4#4@20"),
        ("4#5 @ 20", "4#5 @ 20"),
    ],
)
def test_a_count_before_a_mesh_is_never_dropped(texto, pieza):
    for familia in ("losa", "castillo"):
        a = parsear_armado([texto], familia)
        assert a.vacio() and a.avisos == [f"sin leer: «{pieza}»"], familia


def test_a_count_before_a_layer_and_its_mesh_is_never_dropped():
    for texto, pieza in (("4 LS #4@20", "4 LS #4@20"), ("4LS #4@20 A/S", "4LS #4@20 A/S")):
        a = parsear_armado([texto], "losa")
        assert a.vacio() and a.avisos == [f"sin leer: «{pieza}»"], texto


def test_a_thickness_or_a_section_before_a_mesh_is_context():
    for texto in ("LOSA H=20 #4@20", "MURO 15X250 #3@20"):
        a = parsear_armado([texto], "muro" if "MURO" in texto else "losa")
        assert len(a.parrillas) == 1 and a.avisos == [], texto


def test_layers_written_after_each_mesh_on_one_line():
    a = parsear_armado(["#4@20 L.S. #3@20 L.I."], "losa")
    assert [(p.numero, p.lecho) for p in a.parrillas] == [("4", "sup"), ("3", "inf")]
    assert a.avisos == []


def test_layers_written_after_each_mesh_on_two_lines():
    a = parsear_armado(["#4@20 A/S L.S.", "#3@20 L.I."], "losa")
    assert [(p.numero, p.lecho, p.sentidos) for p in a.parrillas] == [
        ("4", "sup", "ambos"),
        ("3", "inf", None),
    ]
    assert a.avisos == []


def test_layers_written_before_each_mesh_on_one_and_two_lines():
    for textos in (["L.S. #4@20 L.I. #3@20"], ["L.S. #4@20", "L.I. #3@20"]):
        a = parsear_armado(textos, "losa")
        assert [(p.numero, p.lecho) for p in a.parrillas] == [("4", "sup"), ("3", "inf")], textos
        assert a.avisos == [], textos


def test_layers_that_disagree_are_ambiguous_and_no_mesh_is_taken():
    # Un lecho delante y otro detrás: el texto no dice a qué malla va cada uno.
    a = parsear_armado(["LS #4@20 A/S LI"], "losa")
    assert a.parrillas == [] and a.avisos == ["lecho ambiguo: «LS #4@20 A/S LI»: no se toma"]
    b = parsear_armado(["#4@20 L.S.", "L.I. #3@20"], "losa")
    assert b.parrillas == []
    assert b.avisos == [
        "lecho ambiguo: «#4@20 L.S.»: no se toma",
        "lecho ambiguo: «L.I. #3@20»: no se toma",
    ]
    # Un lecho en una línea sola, sin malla al lado, tampoco se asigna a ciegas.
    c = parsear_armado(["LS", "#4@20"], "losa")
    assert c.parrillas == [] and c.avisos == [
        "lecho «LS» sin su malla: no se toma",
        "lecho ambiguo: «#4@20»: no se toma",
    ]


def test_a_spaced_symbol_is_reported_with_its_number():
    a = parsear_armado(["E#3 @ 1S"], "castillo")
    assert a.estribos == [] and a.avisos == ["sin leer: «E#3 @ 1S»"]
    assert parsear_armado(["@ 20"], "castillo").avisos == ["sin leer: «@ 20»"]
    # Sólo se lleva un número, no la palabra siguiente (Marina: «E# SEGÚN CONTRATRABE»).
    assert parsear_armado(["E# SEGÚN CONTRATRABE"], "trabe").avisos == ["sin leer: «E#»"]


@pytest.mark.parametrize(
    "texto,pieza",
    [
        ("4Ø12 mm", "4Ø12 MM"),
        ("4Ø 12MM", "4Ø 12MM"),
        ("4 Ø 12 mm", "4 Ø 12 MM"),
        ("4%%c12 mm", "4Ø12 MM"),
        ("E#3@200 MM", "E#3@200 MM"),
        ("E#3@20 MMS", "E#3@20 MMS"),
    ],
)
def test_millimetres_are_reported_never_read_as_a_bar_number_or_a_spacing(texto, pieza):
    a = parsear_armado([texto], "columna")
    assert a.vacio() and a.avisos == [f"sin leer: «{pieza}»"]


def test_counts_of_ten_or_more_render_and_read_back():
    a = parsear_armado(["10#8+12#6 10E+2G#3@15 12LIGAS#2@20"], "columna")
    assert texto_armado(a) == "10#8+12#6 10E+2G#3@15 12LIGAS#2@20" and a.avisos == []
    b = parsear_armado([texto_armado(a)], "columna")
    assert b.model_dump(exclude={"texto_original"}) == a.model_dump(exclude={"texto_original"})


def _estribo(**campos) -> JuegoEstribos:
    return JuegoEstribos(**({"tipo": "estribo", "cantidad": 1, "numero": "3"} | campos))


def _todo(s: float | None) -> Zona:
    return Zona(tramo="todo", separacion_m=s)


@pytest.mark.parametrize(
    "armado",
    [
        Armado(estribos=[_estribo(zonas=[_todo(None)])]),
        Armado(estribos=[_estribo(cantidad=100)]),
        Armado(estribos=[_estribo(cantidad=0)]),
        Armado(estribos=[_estribo(numero="9")]),
        Armado(estribos=[_estribo(zonas=[Zona(tramo="centro", separacion_m=0.20)])]),
        Armado(estribos=[_estribo(zonas=[_todo(0.15), _todo(0.20)])]),
        Armado(estribos=[_estribo(referencia="VER CORTE A-A")]),
        Armado(estribos=[_estribo(zonas=[_todo(0.0)])]),
        Armado(estribos=[_estribo(zonas=[_todo(0.12345)])]),
        Armado(estribos=[_estribo(zonas=[_todo(10.0)])]),
        Armado(longitudinales=[GrupoVarillas(cantidad=0, numero="3")]),
        Armado(longitudinales=[GrupoVarillas(cantidad=4, numero="11")]),
        Armado(parrillas=[Parrilla(numero="4", separacion_m=-0.2, lecho="unico", sentidos=None)]),
    ],
)
def test_renders_fail_loudly_on_what_the_text_cannot_carry_back(armado):
    with pytest.raises(ValueError):
        texto_armado(armado)


def test_what_is_assigned_later_is_not_text_and_does_not_block_the_render():
    # Formas, posición y longitud de zona vienen de reglas o del dibujo, no del texto.
    a = Armado(
        longitudinales=[GrupoVarillas(cantidad=4, numero="4", posicion="esquina")],
        estribos=[
            _estribo(
                zonas=[Zona(tramo="extremos", separacion_m=0.10, longitud_m=0.60)],
                formas=["perimetral"],
                formas_fuente="supuesto",
            )
        ],
    )
    assert texto_armado(a) == "4#4 E#3 EXT@10"


# ------------------------------------------------------------------ ronda de correcciones 2
# Cada pieza leída mira lo que le sigue hasta la siguiente pieza (o el fin de la línea): si
# no es contexto conocido, la pieza no se lee y se avisa entera, con lo que la estorbó.


@pytest.mark.parametrize(
    "textos",
    [
        ["#4@20", "LS #3@20"],
        ["#4@20 A/S", "LS #3@20 A/S"],
        ["#4@20 A/S, LS #3@20 A/S"],
        ["#4@20", "LI #3@20"],
        ["LOSA H=10 #4@20 A/S", "LECHO SUPERIOR #3@20"],
        ["#4@20 LS #3@20"],
    ],
)
def test_a_mesh_without_layer_next_to_one_with_a_layer_is_ambiguous(textos):
    a = parsear_armado(textos, "losa")
    assert a.parrillas == [] and a.avisos
    assert all(w.startswith("lecho ambiguo: «") for w in a.avisos)
    juntos = " ".join(a.avisos)
    assert "#4@20" in juntos and "#3@20" in juntos


def test_the_mesh_render_never_mixes_layered_and_unlayered_meshes():
    mezcla = Armado(
        parrillas=[
            Parrilla(numero="4", separacion_m=0.20, lecho="unico", sentidos=None),
            Parrilla(numero="3", separacion_m=0.20, lecho="sup", sentidos=None),
        ]
    )
    with pytest.raises(ValueError):
        texto_parrillas(mezcla)


@pytest.mark.parametrize(
    "texto,juegos",
    [
        ("E/G#3@15", [(E, 1), (G, 1)]),
        ("2E-1G#3@15", [(E, 2), (G, 1)]),
        ("2E,1G#3@15", [(E, 2), (G, 1)]),
        ("2E & 1G#3@15", [(E, 2), (G, 1)]),
        ("(2)E#3@15", [(E, 2)]),
        ("(2) E + (1) G #3@15", [(E, 2), (G, 1)]),
    ],
)
def test_stirrup_joiners_and_counts_in_parentheses(texto, juegos):
    for familia in ("castillo", "losa"):
        a = parsear_armado([texto], familia)
        assert [(j.tipo, j.cantidad) for j in a.estribos] == juegos, familia
        assert all(
            [(z.tramo, z.separacion_m) for z in j.zonas] == [("todo", 0.15)] for j in a.estribos
        )
        assert a.parrillas == [] and a.avisos == [], familia
        assert _lo_que_dice(texto_armado(a)) == _lo_que_dice(texto)


@pytest.mark.parametrize(
    "texto",
    [
        "4 VARILLAS DE #4@20",
        "4 PZAS #4@20",
        "(4) #4@20",
        "4-#4@20",
        "4VARS #4@20",
        "4 VARS #4@20",
        "(4) 2#3",
        "4 PZAS 2#3",
    ],
)
def test_a_bare_count_before_a_mesh_or_a_bar_group_is_reported_with_it(texto):
    for familia in ("losa", "castillo"):
        a = parsear_armado([texto], familia)
        assert a.vacio() and a.avisos == [f"sin leer: «{texto}»"], familia


@pytest.mark.parametrize(
    "texto,pieza",
    [
        ("H=202E+1G#3@15", "H=202E+1G#3@15"),
        ("#4@20 A/SE/G#3@15", "#4@20 A/SE/G#3@15"),
        ("K-2#4", "K-2#4"),
        ("(E#3@15)", "(E#3@15)"),
    ],
)
def test_a_piece_glued_to_what_precedes_it_is_reported_with_it(texto, pieza):
    # La cola de una cabeza pegada a otra cosa no se lee sola («…2E+1G#3» → no «1G#3»).
    a = parsear_armado([texto], "losa")
    assert a.vacio() and a.avisos == [f"sin leer: «{pieza}»"]


def test_a_joiner_glued_between_two_pieces_is_still_a_joiner():
    a = parsear_armado(["4#5+2#4,E#3@15"], "castillo")
    assert [(g.cantidad, g.numero) for g in a.longitudinales] == [(4, "5"), (2, "4")]
    assert len(a.estribos) == 1 and a.avisos == []


def test_a_line_that_starts_with_a_joiner_continues_the_previous_one():
    a = parsear_armado(["4#5", "+2#4"], "castillo")
    assert [(g.cantidad, g.numero) for g in a.longitudinales] == [(4, "5"), (2, "4")]
    assert a.avisos == []


def test_the_whitelisted_context_after_a_piece_keeps_it():
    casos = [
        (["4#8 VER CORTE"], "pilote"),
        (["4#3 DALA 15X30"], "dala"),
        (["LS #4@20 A/S H=12"], "losa"),
        (["#4@20 EN X"], "zapata"),
        (["4#3 , E#2@20"], "dala"),
        (["4#3 Y E#2@20"], "dala"),
    ]
    for textos, familia in casos:
        a = parsear_armado(textos, familia)
        assert not a.vacio() and a.avisos == [], textos


# ---- la propiedad: lo que el parser entrega se escribe y se vuelve a leer igual, sin avisos


def _estructura(a: Armado) -> dict:
    return a.model_dump(exclude={"texto_original", "avisos"})


def _vuelve_igual(a: Armado, familia: str) -> None:
    b = parsear_armado([texto_armado(a)], familia)
    assert b.avisos == [] and _estructura(b) == _estructura(a), texto_armado(a)


def _simbolos(texto: str) -> tuple[int, int]:
    t = texto.upper().replace("%%C", "#").replace("Ø", "#").replace("⌀", "#")
    return t.count("#"), t.count("@")


def _escritos_juntos(a: Armado) -> tuple[int, int]:
    """Los «#» y «@» que el render ahorra al escribir un estribo y su grapa juntos («EYG»)."""
    gatos = arrobas = 0
    juegos, i = a.estribos, 0
    while i < len(juegos):
        j, sig = juegos[i], juegos[i + 1] if i + 1 < len(juegos) else None
        if (
            j.tipo == "estribo"
            and sig is not None
            and sig.tipo == "grapa"
            and (sig.numero, sig.zonas, sig.referencia) == (j.numero, j.zonas, j.referencia)
        ):
            gatos, arrobas, i = gatos + 1, arrobas + len(j.zonas), i + 2
        else:
            i += 1
    return gatos, arrobas


def _todas_las_tablas():
    casos = _casos_de_marina()
    casos += [(["LOSA MACIZA DOBLEMENTE ARMADA H=20 LS #4@20 A/S LI #4@20 A/S"], "losa")]
    casos += [(["#4@20 L.S. #3@20 L.I."], "losa"), (["#4@20 A/S L.S.", "#3@20 L.I."], "losa")]
    casos += [(["L.S. #4@20 L.I. #3@20"], "losa"), (["#4@20 A/S L.S. Y L.I."], "losa")]
    casos += [(["LECHO SUPERIOR #4@15 AMBOS SENTIDOS", "LECHO INFERIOR #3@20"], "losa")]
    casos += [(["#3@20 EN X"], "dado"), (["#4@20 #3@15"], "muro"), (["E#3@15 #4@20"], "muro")]
    casos += [(["2G+1E#3@15", "10#8+12#6"], "columna"), (["(2)E#3@15 E/G#2@20"], "castillo")]
    return casos


@pytest.mark.parametrize("textos,familia", _todas_las_tablas())
def test_every_reading_renders_and_reads_back_the_same(textos, familia):
    _vuelve_igual(parsear_armado(textos, familia), familia)


_VOCABULARIO = [
    "4#5",
    "2#4",
    "10#8",
    "12#6",
    "1#3",
    "E#3",
    "E#3@15",
    "2E#3@20",
    "EYG#3@15",
    "2E+1G#3",
    "G#3@14",
    "3E#3",
    "E#2@20",
    "#4@20",
    "#3@15",
    "#4@20 A/S",
    "LS",
    "LI",
    "L.S.",
    "L.I.",
    "LS #4@20 A/S",
    "LI #3@20",
    "EXT@10",
    "CENTRO@20",
    "@15",
    "@20",
    "VER CORTE",
    "DALA",
    "15X30",
    "H=20",
    "4",
    "VARS",
    "CM",
    "MM",
    "/20",
    ",20",
    "-20",
    "Y",
    "+",
    ",",
    "Ø5",
    "%%C4",
    "(2)E#3@15",
    "E/G#3@15",
    "2G+1E#3",
    "ESTRIBOS DE",
    "#9",
    "@1S",
    "X",
    "REFUERZO",
    "A/S",
    "EN X",
    "2.5",
    "#2.5",
    "4#2.5",
    "E.",
    "(4)",
    "PZAS",
    "L.S. Y L.I.",
    "@12.5",
]
_UNIONES = [" ", "", ", ", "+", " | ", "  "]
_FAMILIAS = ["castillo", "losa", "muro", "columna", "trabe", "pilote", "zapata", "dala"]


def _textos_al_azar(n: int):
    rng = random.Random(20261008)
    for _ in range(n):
        piezas = [rng.choice(_VOCABULARIO) for _ in range(rng.randint(1, 5))]
        texto = piezas[0]
        for pieza in piezas[1:]:
            texto += rng.choice(_UNIONES) + pieza
        yield [linea for linea in texto.split(" | ")], rng.choice(_FAMILIAS)


def test_fuzz_every_reading_renders_back_and_nothing_disappears():
    for textos, familia in _textos_al_azar(4000):
        a = parsear_armado(textos, familia)
        # 1. Lo leído se escribe y se vuelve a leer igual.
        _vuelve_igual(a, familia)
        # 2. Ningún «#» ni «@» desaparece: está en lo escrito o en un aviso.
        n_gato, n_arroba = _simbolos(" ".join(textos))
        escrito = _simbolos(texto_armado(a) + " " + " ".join(a.avisos))
        ahorro = _escritos_juntos(a)
        assert n_gato <= escrito[0] + ahorro[0], (textos, familia, a.avisos)
        assert n_arroba <= escrito[1] + ahorro[1], (textos, familia, a.avisos)


# ------------------------------------------------------------------ ronda de correcciones 3
# Los números son fichas enteras, el contexto se reconoce donde está en el texto (no en un
# recorte), dos piezas pegadas no se parten, una junta va justo antes de la pieza que une,
# y nada con cifra, «#», «@» o «/» queda fuera sin aviso.


@pytest.mark.parametrize(
    "texto,familia,aviso",
    [
        ("E#3@1520X30", "dala", "sin leer: «E#3@1520X30»"),
        ("4#320X40", "castillo", "sin leer: «4#320X40»: no hay varilla del #320"),
        ("2#55X150", "castillo", "sin leer: «2#55X150»: no hay varilla del #55"),
        ("#4@2015X30", "losa", "sin leer: «#4@2015X30»"),
        ("4#3H=20", "castillo", "sin leer: «4#3H=20»"),
        ("4#3DALA", "dala", "sin leer: «4#3DALA»"),
        ("E#3@15A/S", "castillo", "sin leer: «E#3@15A/S»"),
        ("4#8VER CORTE", "pilote", "sin leer: «4#8VER CORTE»"),
    ],
)
def test_context_never_swallows_the_end_of_a_number(texto, familia, aviso):
    a = parsear_armado([texto], familia)
    assert a.vacio() and a.avisos == [aviso]


def test_a_glued_section_after_a_spacing_unreads_only_that_piece():
    a = parsear_armado(["4#3,E#2@2015X30"], "dala")
    assert [(g.cantidad, g.numero) for g in a.longitudinales] == [(4, "3")] and a.estribos == []
    assert a.avisos == ["sin leer: «E#2@2015X30»"]


@pytest.mark.parametrize(
    "texto,familia,aviso",
    [
        ("E#32#4", "castillo", "sin leer: «E#32#4»: no hay varilla del #32"),
        ("E#212#6", "columna", "sin leer: «E#212#6»: no hay varilla del #212"),
        ("G#38#8", "castillo", "sin leer: «G#38#8»: no hay varilla del #38"),
        ("EYG#310#8", "castillo", "sin leer: «EYG#310#8»: no hay varilla del #310"),
        ("2#3#4@20", "muro", "sin leer: «2#3#4@20»"),
        ("2#3#4@20", "losa", "sin leer: «2#3#4@20»"),
        ("#4@20#3@20", "losa", "sin leer: «#4@20#3@20»"),
        ("#4@20 A/S#3@20", "losa", "sin leer: «#4@20 A/S#3@20»"),
        ("#4@20CM2#3", "losa", "sin leer: «#4@20CM2#3»"),
    ],
)
def test_two_pieces_that_touch_are_never_split(texto, familia, aviso):
    a = parsear_armado([texto], familia)
    assert a.vacio() and a.avisos == [aviso]


@pytest.mark.parametrize(
    "texto,familia",
    [
        ("4#5+", "castillo"),
        ("E#3@15 Y", "castillo"),
        ("E#3@15,", "castillo"),
        ("#4@20 A/S ,", "losa"),
    ],
)
def test_a_joiner_with_nothing_after_it_is_reported(texto, familia):
    a = parsear_armado([texto], familia)
    assert a.vacio() and a.avisos == [f"sin leer: «{texto}»"]


def test_a_joiner_must_be_right_before_the_piece_it_joins():
    # Lo que queda entre dos piezas sin ser contexto no se sabe de cuál es: no se lee ninguna.
    a = parsear_armado(["4#3 Y DALA E#2@20"], "dala")
    assert a.vacio() and a.avisos == ["sin leer: «4#3 Y DALA E#2@20»"]
    b = parsear_armado(["E#3@15,20X30 4#3"], "castillo")
    assert b.vacio() and b.avisos == ["sin leer: «E#3@15,20X30 4#3»"]


@pytest.mark.parametrize(
    "texto,familia",
    [
        ("1#3AMBOS LECHOS #3@20 A/S", "zapata"),
        ("#3@152 PARRILLAS #4@20", "losa"),
        ("#4@20 A/SE. #3@20", "muro"),
        ("4#3DALA E#2@20", "dala"),
    ],
)
def test_junk_between_two_pieces_reports_both(texto, familia):
    a = parsear_armado([texto], familia)
    assert a.vacio() and a.avisos == [f"sin leer: «{texto}»"]


def test_the_digits_after_an_at_sign_are_never_a_count():
    a = parsear_armado(["#4@20EYG#3@15"], "castillo")
    assert a.estribos == [] and a.avisos == ["sin leer: «#4@20EYG#3@15»"]
    b = parsear_armado(["#4@20E#3"], "muro")
    assert b.vacio() and b.avisos == ["sin leer: «#4@20E#3»"]


def test_a_double_word_only_doubles_the_mesh_it_is_attached_to():
    # «2 PARRILLAS» se refería a una malla que no se pudo leer: no salta a la siguiente.
    a = parsear_armado(["2 PARRILLAS #4@2012#6 + #3@15"], "muro")
    assert a.parrillas == [] and a.avisos
    assert any(w.startswith("lecho ambiguo") and "#3@15" in w for w in a.avisos)


def test_a_mesh_after_an_uncounted_plural_is_reported():
    a = parsear_armado(["XAMBOS LECHOS #3@20"], "losa")
    assert a.vacio() and a.avisos == ["sin leer: «XAMBOS LECHOS #3@20»"]


def test_a_line_that_ends_with_a_joiner_continues_on_the_next():
    for textos in (["4#5+", "2#4"], ["4#5,", "2#4"], ["4#5", "+2#4"]):
        a = parsear_armado(textos, "castillo")
        assert [(g.cantidad, g.numero) for g in a.longitudinales] == [(4, "5"), (2, "4")], textos
        assert a.avisos == [], textos


@pytest.mark.parametrize(
    "textos,familia,long,estr,mallas",
    [
        (["K-1 4#4 E#2@20"], "castillo", [(4, "4")], [("2", 0.20)], 0),
        (["ZAPATA Z-1 #4@20 A/S"], "zapata", [], [], 1),
        (["T-1 2#5+2#4"], "trabe", [(2, "5"), (2, "4")], [], 0),
        (["15 X 30 4#3"], "dala", [(4, "3")], [], 0),
        (["SECCION 20 X 40 4#4"], "castillo", [(4, "4")], [], 0),
    ],
)
def test_a_mark_or_a_spaced_section_is_context_not_a_count(textos, familia, long, estr, mallas):
    a = parsear_armado(textos, familia)
    assert [(g.cantidad, g.numero) for g in a.longitudinales] == long
    assert [(j.numero, j.zonas[0].separacion_m) for j in a.estribos] == estr
    assert len(a.parrillas) == mallas and a.avisos == []


@pytest.mark.parametrize(
    "texto,familia,sentidos",
    [
        ("2 PARRILLAS #4@20", "muro", None),
        ("2 CAPAS DE #3@20", "muro", None),
        ("2 LECHOS #4@20", "losa", None),
        ("DOBLE PARRILLA #4@20", "zapata", None),
        ("AMBOS LECHOS #4@20 A/S", "losa", "ambos"),
        ("LOSA DOBLEMENTE ARMADA H=12 #4@20 A/S", "losa", "ambos"),
    ],
)
def test_a_double_mesh_word_reads_as_two_layers(texto, familia, sentidos):
    a = parsear_armado([texto], familia)
    numero = "3" if "#3" in texto else "4"
    assert [(p.numero, p.separacion_m, p.lecho, p.sentidos) for p in a.parrillas] == [
        (numero, 0.20, "sup", sentidos),
        (numero, 0.20, "inf", sentidos),
    ]
    assert a.avisos == []
    _vuelve_igual(a, familia)


def test_a_double_mesh_on_a_family_without_meshes_is_reported_whole():
    a = parsear_armado(["2 PARRILLAS #4@20"], "castillo")
    assert a.vacio() and a.avisos == ["malla «2 PARRILLAS #4@20» en un castillo: no se toma"]


@pytest.mark.parametrize(
    "texto",
    ["4 DE #4@20", "4 X #4@20", "3 PARRILLAS #4@20", "DOBLE MALLA #4@20", "TRES CAPAS DE #3@20"],
)
def test_any_other_multiplier_before_a_mesh_is_reported_whole(texto):
    a = parsear_armado([texto], "muro")
    assert a.vacio() and a.avisos == [f"sin leer: «{texto}»"]


def test_a_mesh_after_a_layer_word_glued_to_something_is_reported():
    # «A/SLI»: el «LI» pegado no se reconoce como lecho, pero tampoco se lee la malla como
    # única; el lecho que dice el plano no puede perderse.
    a = parsear_armado(["#4@20 A/SLI #3@20"], "muro")
    assert a.vacio() and a.avisos == ["sin leer: «#4@20 A/SLI #3@20»"]


def test_a_following_line_with_a_number_never_disappears():
    a = parsear_armado(["E#3@15", "Y 20"], "castillo")
    assert a.vacio() and a.avisos == ["sin leer: «E#3@15 | Y 20»"]
    b = parsear_armado(["E#3@15", "20"], "castillo")
    assert [j.zonas[0].separacion_m for j in b.estribos] == [0.15]
    assert b.avisos == ["sin leer: «20»"]


def test_centre_to_centre_after_a_spacing_is_context():
    a = parsear_armado(["#4@20 C/C A/S"], "losa")
    assert [(p.numero, p.sentidos) for p in a.parrillas] == [("4", "ambos")] and a.avisos == []
    b = parsear_armado(["E#3@15 C/C"], "castillo")
    assert b.estribos[0].zonas[0].separacion_m == 0.15 and b.avisos == []


# ---- fuzz con lectura conocida: piezas completas unidas al azar. Si se unen limpias, el
# armado es la suma de las piezas (o hay aviso); si se pegan, siempre hay aviso; y nunca
# se lee algo que no esté en las piezas.

_PIEZAS = [
    "4#5",
    "2#4",
    "10#8",
    "12#6",
    "1#3",
    "4#2.5",
    "2 VARS #3",
    "E#3",
    "E#3@15",
    "2E#3@20",
    "EYG#3@15",
    "2E+1G#3",
    "G#3@14",
    "3E#3 VER CORTE",
    "E#2@20",
    "2E#3EXT@10 CENTRO@20",
    "(2)E#3@15",
    "E/G#2@20",
    "#4@20",
    "#3@15",
    "#4@20 A/S",
    "LS #4@20 A/S",
    "LI #3@20",
    "#4@20 C/C",
    "E#3@12.5",
    "DALA 15X30 4#3",
    "K-1 4#4",
    "REFUERZO 1#3",
    "2 PARRILLAS #4@20",
    "LOSA H=20 #4@20 A/S",
    "SECCION 20 X 40 4#4",
    "AMBOS LECHOS #3@20 A/S",
    "#4@20 L.S. Y L.I.",
    "4 VARILLAS #5",
    "E. #3@20",
    "2G+1E#3@15",
]
_UNIONES_LIMPIAS = [" ", ", ", "+", " | ", " Y ", " ,", " + "]


def _suma(textos_por_pieza: list[str], familia: str) -> dict[str, list]:
    suma: dict[str, list] = {"longitudinales": [], "estribos": [], "parrillas": []}
    for pieza in textos_por_pieza:
        sola = parsear_armado([pieza], familia).model_dump()
        for clave in suma:
            suma[clave] += sola[clave]
    return suma


def test_fuzz_known_readings_never_split_nor_invent():
    rng = random.Random(8102026)
    for _ in range(4000):
        piezas = [rng.choice(_PIEZAS) for _ in range(rng.randint(2, 4))]
        familia = rng.choice(["castillo", "losa", "muro", "columna", "pilote"])
        pegadas = False
        texto = piezas[0]
        for pieza in piezas[1:]:
            if rng.random() < 0.25:
                union, pegadas = "", True
            else:
                union = rng.choice(_UNIONES_LIMPIAS)
            texto += union + pieza
        a = parsear_armado(texto.split(" | "), familia)
        leido = a.model_dump()
        esperado = _suma(piezas, familia)
        for clave, lista in esperado.items():
            sobra = Counter(map(repr, leido[clave])) - Counter(map(repr, lista))
            assert not sobra, (texto, familia, clave, sobra)  # nada inventado ni partido
        if pegadas:
            assert a.avisos, (texto, familia)
        elif not a.avisos:
            assert {k: leido[k] for k in esperado} == esperado, (texto, familia)
        _vuelve_igual(a, familia)
