"""El armado como estructura: cada `#` y cada `@` del texto queda leído o avisado, nunca perdido."""

import pytest
from klave_engine.costing.steel import BAR_KG_PER_M
from klave_engine.estructura.armado import (
    FAMILIAS_CON_PARRILLA,
    NUMEROS,
    Armado,
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


@pytest.mark.parametrize(
    "textos,familia,long,estr",
    [
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
    ],
)
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
    (["2 VARILLAS #5 ANCLADA AL MURO"], "castillo", [(2, "5")], []),
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
    a = parsear_armado(["4%%C5+2Ø4 E%%c3@20 100%%%"], "castillo")
    assert [(g.cantidad, g.numero) for g in a.longitudinales] == [(4, "5"), (2, "4")]
    assert [(j.numero, j.zonas[0].separacion_m) for j in a.estribos] == [("3", 0.20)]
    assert a.avisos == []


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
    assert c.longitudinales == [] and c.avisos and "#3/8" in c.avisos[0]
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
    assert c.estribos[0].zonas == [] and c.avisos == ["sin leer: «@0»"]


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
    assert a.longitudinales == [] and a.avisos == ["sin leer: «2#5X150»"]


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
            Parrilla(numero="3", separacion_m=0.15, lecho="unico", sentidos=None),
        ],
    )
    assert texto_longitudinal(a) == ""
    assert texto_estribos(a) == "1E+2G#3@15 G#2 VER CORTE"
    assert texto_parrillas(a) == "LS #4@20 A/S #3@15"
    assert texto_armado(a) == "1E+2G#3@15 G#2 VER CORTE LS #4@20 A/S #3@15"
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
