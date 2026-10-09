"""El dato con su fuente: la precedencia decide, y un desacuerdo del mismo rango nunca se calla."""

from klave_engine.estructura.dato import PRECEDENCIA, Dato, elegir
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
