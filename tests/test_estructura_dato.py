"""El dato con su fuente: la precedencia decide, y un desacuerdo del mismo rango nunca se calla."""

from klave_engine.estructura.dato import PRECEDENCIA, Dato, elegir, miembros, para_hoja
from pydantic import BaseModel


def test_higher_source_wins_and_losers_are_kept():
    d = elegir(
        [Dato(valor=(20, 30), fuente="ia"), Dato(valor=(15, 30), fuente="detalle", hoja="ES-400")]
    )
    assert d.valor == (15, 30) and d.fuente == "detalle"
    assert [a.fuente for a in d.alternativas] == ["ia"] and d.en_conflicto is False


def test_same_rank_disagreement_is_a_conflict_never_silent():
    a = Dato(valor=(20, 30), fuente="detalle", hoja="ES-400")
    b = Dato(valor=(20, 40), fuente="detalle", hoja="ES-200")
    d = elegir([a, b], preferir_hoja="ES-200")
    assert d.valor == (20, 40) and d.en_conflicto is True and d.alternativas[0].valor == (20, 30)
    d2 = elegir([a, b])  # no preference: most frequent value, tie → first by hoja
    assert d2.valor == (20, 40) and d2.en_conflicto is True


def test_equal_copies_count_not_conflict():
    d = elegir(
        [
            Dato(valor="EYG#3@15", fuente="detalle", hoja="ES-400"),
            Dato(valor="EYG#3@15", fuente="detalle", hoja="ES-400"),
        ]
    )
    assert d.copias == 2 and d.en_conflicto is False


def test_unreadable_text_blocks_ia():
    d = elegir(
        [
            Dato(valor=None, fuente="detalle", ilegible=True, texto="E#3@1S"),
            Dato(valor="E#2@15", fuente="ia"),
        ]
    )
    assert d.ilegible is True and d.valor is None and d.alternativas[0].fuente == "ia"


def test_empty_is_none():
    assert elegir([]) is None


def test_reloaded_list_equals_fresh_tuple():
    # estructura.json guarda las tuplas como listas: un [20, 40] recargado es el mismo valor.
    d = elegir(
        [
            Dato(valor=(20, 40), fuente="detalle", hoja="A"),
            Dato(valor=[20, 40], fuente="detalle", hoja="B"),
        ]
    )
    assert d.copias == 2 and d.en_conflicto is False


def test_most_frequent_value_wins_without_preference():
    a = Dato(valor=(20, 30), fuente="detalle", hoja="ES-100")
    b = Dato(valor=(20, 40), fuente="detalle", hoja="ES-200")
    c = Dato(valor=(20, 40), fuente="detalle", hoja="ES-300")
    d = elegir([a, b, c])
    assert d.valor == (20, 40) and d.copias == 2 and d.en_conflicto is True
    # todo lo demás queda como alternativa plana, la copia del valor ganador incluida
    assert [(x.valor, x.hoja) for x in d.alternativas] == [
        ((20, 30), "ES-100"),
        ((20, 40), "ES-300"),
    ]


def test_tie_without_preference_goes_to_the_smallest_hoja():
    a = Dato(valor="A", fuente="cuadro", hoja="ES-400")
    b = Dato(valor="B", fuente="cuadro", hoja="ES-200")
    d = elegir([a, b])
    assert d.valor == "B" and d.en_conflicto is True and d.copias == 1
    assert [x.valor for x in d.alternativas] == ["A"]


def test_preferred_hoja_beats_frequency():
    mayoria = [Dato(valor="X", fuente="detalle", hoja=h) for h in ("ES-100", "ES-300", "ES-400")]
    preferido = Dato(valor="Y", fuente="detalle", hoja="ES-200")
    d = elegir([*mayoria, preferido], preferir_hoja="ES-200")
    assert d.valor == "Y" and d.en_conflicto is True and d.copias == 1
    assert len(d.alternativas) == 3


def test_alternativas_are_flat_and_include_every_lower_rank():
    humano = Dato(valor=1, fuente="humano")
    d1 = Dato(valor=2, fuente="detalle", hoja="A")
    d2 = Dato(valor=2, fuente="detalle", hoja="B")
    ia = Dato(valor=3, fuente="ia")
    d = elegir([ia, d1, humano, d2])
    assert d.fuente == "humano" and d.en_conflicto is False
    assert [x.fuente for x in d.alternativas] == ["ia", "detalle", "detalle"]


def test_losers_alternativas_are_kept_nested_not_spliced():
    anidado = Dato(
        valor="B", fuente="detalle", hoja="Z", alternativas=[Dato(valor="C", fuente="ia")]
    )
    d = elegir([Dato(valor="A", fuente="cuadro"), anidado])
    assert d.valor == "A"
    assert [x.valor for x in d.alternativas] == ["B"]
    # el perdedor viaja tal cual; su propia lista no se aplana ni se pierde
    assert d.alternativas[0].alternativas[0].valor == "C"


def test_elegir_does_not_mutate_inputs():
    a = Dato(valor=(20, 30), fuente="detalle", hoja="ES-400")
    b = Dato(valor=(20, 40), fuente="detalle", hoja="ES-200")
    ia = Dato(valor=(1, 1), fuente="ia")
    d = elegir([a, b, ia])
    assert d is not a and d is not b
    for x in (a, b, ia):
        assert x.alternativas == [] and x.en_conflicto is False and x.copias == 1
    assert a.valor == (20, 30) and b.valor == (20, 40)


def test_json_roundtrip_keeps_the_chosen_dato():
    d = elegir([Dato(valor=(20, 30), fuente="detalle", hoja="A"), Dato(valor=(1, 2), fuente="ia")])
    otra = Dato.model_validate(d.model_dump(mode="json"))
    assert otra.fuente == "detalle" and otra.alternativas[0].fuente == "ia"
    assert list(otra.valor) == [20, 30]


def test_valor_can_be_a_pydantic_model():
    class Medida(BaseModel):  # cualquier BaseModel como valor se compara por su volcado JSON
        largo: float

    d = elegir(
        [Dato(valor=Medida(largo=1.5), fuente="regla"), Dato(valor={"largo": 1.5}, fuente="regla")]
    )
    assert d.copias == 2 and d.en_conflicto is False
    d2 = elegir(
        [
            Dato(valor=Medida(largo=1.5), fuente="regla"),
            Dato(valor=Medida(largo=2.0), fuente="regla"),
        ]
    )
    assert d2.copias == 1 and d2.en_conflicto is True


def test_the_same_object_twice_counts_as_two_copies():
    x = Dato(valor="E#3@15", fuente="detalle", hoja="ES-400")
    d = elegir([x, x])
    assert d.copias == 2 and len(d.alternativas) == 1 and d.en_conflicto is False


def test_precedencia_matches_the_brief():
    assert PRECEDENCIA == {
        "humano": 8,
        "cuadro": 7,
        "detalle": 6,
        "seccion_dibujada": 5,
        "nota": 4,
        "medido": 3,
        "regla": 2,
        "supuesto": 1,
        "ia": 0,
    }


def test_top_rank_unreadable_with_value_conflict():
    # el ilegible del mismo rango cuenta como un valor más (None) y choca con uno legible
    d = elegir(
        [
            Dato(valor=None, fuente="detalle", hoja="A", ilegible=True, texto="E#3@1S"),
            Dato(valor="E#3@15", fuente="detalle", hoja="B"),
        ]
    )
    assert d.en_conflicto is True


def _eleccion_en_conflicto():
    return elegir(
        [
            Dato(valor=(20, 30), fuente="detalle", hoja="A"),
            Dato(valor=(20, 40), fuente="detalle", hoja="B"),
        ]
    )


def test_re_electing_an_elected_dato_keeps_its_conflict_and_the_losing_reading():
    e1 = _eleccion_en_conflicto()
    assert e1.en_conflicto is True and [a.valor for a in e1.alternativas] == [(20, 40)]
    e2 = elegir([e1])
    assert e2.valor == (20, 30) and e2.en_conflicto is True and e2.copias == 1
    assert [a.valor for a in e2.alternativas] == [(20, 40)]
    assert e2 is not e1 and len(e1.alternativas) == 1  # ni muta ni devuelve el mismo objeto


def test_re_electing_with_a_lower_source_keeps_the_conflict_and_lists_both():
    e1 = _eleccion_en_conflicto()
    ia = Dato(valor=(1, 1), fuente="ia")
    e2 = elegir([e1, ia])
    assert e2.valor == (20, 30) and e2.en_conflicto is True
    # primero los demás datos recibidos, luego lo que el elegido ya traía, todo plano
    assert [a.valor for a in e2.alternativas] == [(1, 1), (20, 40)]
    assert all(a.alternativas == [] for a in e2.alternativas)


def test_re_electing_survives_a_json_reload():
    e1 = _eleccion_en_conflicto()
    recargado = Dato.model_validate(e1.model_dump(mode="json"))
    e2 = elegir([recargado, Dato(valor="x", fuente="supuesto")])
    assert e2.en_conflicto is True
    assert [list(a.valor) if isinstance(a.valor, list) else a.valor for a in e2.alternativas] == [
        "x",
        [20, 40],
    ]


def test_copias_sum_the_incoming_copias_of_the_winning_group():
    dos = elegir(
        [
            Dato(valor="EYG#3@15", fuente="detalle", hoja="A"),
            Dato(valor="EYG#3@15", fuente="detalle", hoja="A"),
        ]
    )
    assert dos.copias == 2
    tres = elegir([dos, Dato(valor="EYG#3@15", fuente="detalle", hoja="B")])
    assert tres.copias == 3 and tres.en_conflicto is False
    otra = elegir([dos, Dato(valor="EYG#3@15", fuente="detalle", hoja="B"), dos])
    assert otra.copias == 5


def test_winner_takes_the_preferred_hoja_when_a_member_of_its_group_has_it():
    d = elegir(
        [
            Dato(valor=(20, 40), fuente="detalle", hoja="ES-300"),
            Dato(valor=(20, 40), fuente="detalle", hoja="ES-200"),
            Dato(valor=(20, 30), fuente="detalle", hoja="ES-100"),
        ],
        preferir_hoja="ES-200",
    )
    assert d.hoja == "ES-200" and d.valor == (20, 40) and d.copias == 2
    assert d.en_conflicto is True
    assert sorted(a.hoja for a in d.alternativas) == ["ES-100", "ES-300"]


def test_winner_keeps_the_first_member_when_no_hoja_is_preferred():
    d = elegir(
        [
            Dato(valor=(20, 40), fuente="detalle", hoja="ES-300"),
            Dato(valor=(20, 40), fuente="detalle", hoja="ES-200"),
        ]
    )
    assert d.hoja == "ES-300" and d.copias == 2


def test_clave_is_total_for_values_json_cannot_dump():
    sucio = {1: "a", "b": 2}  # claves de tipos mezclados: sort_keys falla
    con_tuplas = {(1, 2): "x"}  # clave que no es str/int/float/bool/None
    d = elegir(
        [
            Dato(valor=sucio, fuente="regla", hoja="A"),
            Dato(valor={1: "a", "b": 2}, fuente="regla", hoja="B"),
        ]
    )
    assert d.copias == 2 and d.en_conflicto is False
    d2 = elegir(
        [
            Dato(valor=con_tuplas, fuente="regla", hoja="A"),
            Dato(valor={(1, 2): "x"}, fuente="regla", hoja="B"),
            Dato(valor={(3, 4): "y"}, fuente="regla", hoja="C"),
        ]
    )
    assert d2.copias == 2 and d2.en_conflicto is True


def test_the_most_repeated_value_wins_by_the_copies_each_dato_already_carries():
    # Un dato que ya junta 12 copias pesa más que uno que junta 8, aunque su hoja sea mayor.
    ocho = Dato(valor="8", fuente="nota", hoja="ES-000", copias=8)
    doce = Dato(valor="10", fuente="nota", hoja="ES-100", copias=12)
    d = elegir([ocho, doce])
    assert d.valor == "10" and d.copias == 12 and d.en_conflicto is True
    assert [a.valor for a in d.alternativas] == ["8"]
    assert elegir([doce, ocho]).valor == "10"  # y no depende del orden
    empate = elegir(
        [
            Dato(valor="8", fuente="nota", hoja="ES-100", copias=3),
            Dato(valor="10", fuente="nota", hoja="ES-000", copias=3),
        ]
    )
    assert empate.valor == "10" and empate.hoja == "ES-000"  # el empate lo desempata la hoja menor


# --- hojas: todas las hojas que dicen el valor ---------------------------------------------------


def _cimentacion_y_plantas():
    """Dos lecturas de la misma regla, cada una en varias hojas (como las notas de Marina)."""
    cimentacion = Dato(
        valor="8",
        fuente="nota",
        hoja="ES-000",
        hojas=["ES-000", "ES-001", "ES-002"],
        copias=3,
        texto="DEL #8 Y DIAMETROS MAYORES",
    )
    plantas = Dato(
        valor="10",
        fuente="nota",
        hoja="ES-100",
        hojas=["ES-100", "ES-101", "ES-200", "ES-201"],
        copias=4,
    )
    return cimentacion, plantas


def test_a_hoja_inside_hojas_counts_as_the_preferred_one():
    cimentacion, plantas = _cimentacion_y_plantas()
    d = elegir([cimentacion, plantas], preferir_hoja="ES-002")  # no es la primera de su dato
    assert d.valor == "8" and d.hoja == "ES-000" and d.en_conflicto is True
    assert d.copias == 3 and [a.valor for a in d.alternativas] == ["10"]
    # Sin preferida gana la más repetida.
    assert elegir([cimentacion, plantas]).valor == "10"
    assert elegir([cimentacion, plantas], preferir_hoja="ES-201").valor == "10"
    assert elegir([cimentacion, plantas], preferir_hoja="ES-999").valor == "10"


def test_the_elected_dato_knows_every_hoja_of_its_group():
    solo = Dato(valor=(20, 40), fuente="detalle", hoja="ES-300")
    otro = Dato(valor=(20, 40), fuente="detalle", hoja="ES-200", hojas=["ES-200", "ES-201"])
    perdedor = Dato(valor=(20, 30), fuente="detalle", hoja="ES-100")
    d = elegir([solo, otro, perdedor])
    assert d.hoja == "ES-300" and d.hojas == ["ES-300", "ES-200", "ES-201"]
    assert d.copias == 2 and d.en_conflicto is True
    preferido = elegir([solo, otro, perdedor], preferir_hoja="ES-201")
    assert preferido.hoja == "ES-200" and preferido.hojas == ["ES-200", "ES-201", "ES-300"]
    # Elegir de nuevo sobre el elegido no pierde ninguna hoja.
    otra_vez = elegir([d, Dato(valor=(20, 40), fuente="detalle", hoja="ES-400")])
    assert otra_vez.hojas == ["ES-300", "ES-200", "ES-201", "ES-400"] and otra_vez.copias == 3
    assert elegir([Dato(valor=1, fuente="supuesto")]).hojas == []  # sin hoja, sin hojas


def test_a_dato_without_hoja_is_not_preferred_by_an_empty_hoja():
    d = elegir(
        [Dato(valor="a", fuente="nota"), Dato(valor="b", fuente="nota", hoja="ES-100")],
        preferir_hoja="",
    )
    assert d.valor == "a"  # empate: manda el orden, no una hoja vacía que no existe


def test_members_gives_back_what_elegir_joined():
    cimentacion, plantas = _cimentacion_y_plantas()
    otra_cimentacion = Dato(valor="8", fuente="nota", hoja="ES-050", copias=2)
    d = elegir([cimentacion, otra_cimentacion, plantas])
    assert d.valor == "8" and d.copias == 5
    originales = miembros(d)
    assert [(m.valor, m.copias, m.alternativas, m.en_conflicto) for m in originales] == [
        ("8", 3, [], False),
        ("8", 2, [], False),
        ("10", 4, [], False),
    ]


def test_each_hoja_resolves_its_own_value_and_the_others_stay_as_alternatives():
    cimentacion, plantas = _cimentacion_y_plantas()
    d = elegir([cimentacion, plantas])
    assert d.valor == "10" and d.en_conflicto is True  # globalmente gana la mayoría

    en_000 = para_hoja(d, "ES-000")
    assert en_000.valor == "8" and en_000.hoja == "ES-000" and en_000.copias == 3
    assert en_000.en_conflicto is False  # ES-000 se dice una sola vez
    assert en_000.hojas == ["ES-000", "ES-001", "ES-002"]
    assert [(a.valor, a.copias) for a in en_000.alternativas] == [("10", 4)]  # sin contar

    en_201 = para_hoja(d, "ES-201")
    assert en_201.valor == "10" and en_201.en_conflicto is False and en_201.copias == 4
    assert [a.valor for a in en_201.alternativas] == ["8"]

    sin_copia = para_hoja(d, "ES-999")  # una hoja sin copia propia: el elegido, con su conflicto
    assert sin_copia.valor == "10" and sin_copia.en_conflicto is True
    assert sin_copia == d


def test_a_hoja_that_says_two_things_keeps_its_conflict():
    a = Dato(valor="8", fuente="nota", hoja="ES-000", hojas=["ES-000", "ES-001"], copias=2)
    b = Dato(valor="10", fuente="nota", hoja="ES-001", copias=1)
    c = Dato(valor="12", fuente="nota", hoja="ES-100", copias=1)
    d = elegir([a, b, c])
    en_001 = para_hoja(d, "ES-001")
    assert en_001.en_conflicto is True and en_001.valor == "8"  # la más repetida de las suyas
    assert sorted(x.valor for x in en_001.alternativas) == ["10", "12"]
    en_100 = para_hoja(d, "ES-100")
    assert en_100.valor == "12" and en_100.en_conflicto is False


def test_a_supuesto_is_the_same_for_every_hoja_but_never_the_same_object():
    d = Dato(valor=0.05, fuente="supuesto")
    de_hoja = para_hoja(d, "ES-000")
    assert de_hoja == d and de_hoja is not d
    de_hoja.valor = 9.0
    assert d.valor == 0.05  # editar el resultado no toca el original


def test_a_hoja_without_a_copy_of_its_own_gets_a_deep_copy_of_the_elected_dato():
    cimentacion, plantas = _cimentacion_y_plantas()
    d = elegir([cimentacion, plantas])
    sin_copia = para_hoja(d, "ES-999")
    assert sin_copia == d and sin_copia is not d
    sin_copia.alternativas[0].valor = "x"
    sin_copia.hojas.append("ES-999")
    assert d.alternativas[0].valor == "8" and "ES-999" not in d.hojas


def test_a_hojas_own_nota_beats_a_detalle_of_another_hoja():
    nota = Dato(valor=0.05, fuente="nota", hoja="ES-000")
    detalle = Dato(valor=0.08, fuente="detalle", hoja="ES-100")
    d = elegir([nota, detalle])
    assert d.valor == 0.08  # globalmente un detalle manda sobre una nota
    assert para_hoja(d, "ES-000").valor == 0.05  # pero cada hoja manda sobre lo suyo
    assert para_hoja(d, "ES-100").valor == 0.08
