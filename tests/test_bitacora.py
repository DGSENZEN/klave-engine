"""Una bitácora que se puede corregir no prueba nada."""

import pytest
from klave_engine.costing import bitacora as bit


def _nota(numero: int, **kw: object) -> bit.NotaBitacora:
    base: dict[str, object] = dict(
        numero=numero, fecha="2026-03-01", tipo="ordinaria", parte="contratante",
        autor="Ing. Diego Gaytán", cargo="Residente de obra",
        texto="Se recibe el frente norte para iniciar cimentación.",
    )
    base.update(kw)
    return bit.NotaBitacora(**base)  # type: ignore[arg-type]


def _abierta() -> list[bit.NotaBitacora]:
    return bit.asentar([], _nota(1, tipo="apertura", texto="Se abre la bitácora del contrato."))


def test_la_primera_nota_es_la_de_apertura() -> None:
    with pytest.raises(bit.BitacoraError, match="no está abierta"):
        bit.asentar([], _nota(1))


def test_no_hay_dos_aperturas() -> None:
    notas = _abierta()
    with pytest.raises(bit.BitacoraError, match="art. 125"):
        bit.asentar(notas, _nota(2, tipo="apertura"))


def test_una_nota_asentada_no_se_reescribe() -> None:
    """Si se pudiera, cualquier cosa que dijera pudo escribirse después."""
    notas = bit.asentar(_abierta(), _nota(2))
    with pytest.raises(bit.BitacoraError, match="no se reescribe"):
        bit.asentar(notas, _nota(2, texto="Otra cosa"))


def test_una_nota_mal_asentada_se_aclara_con_otra_y_las_dos_quedan() -> None:
    notas = bit.asentar(_abierta(), _nota(2, texto="El frente norte mide 40 m."))
    notas = bit.asentar(
        notas,
        _nota(3, parte="contratista", autor="Ing. Ana Ruiz", cargo="Superintendente",
              texto="Aclaración a la nota 2: el frente norte mide 45 m según levantamiento.",
              referencia=2),
    )
    assert len(notas) == 3
    # La equivocada sigue ahí: eso es lo que hace que la bitácora pruebe algo.
    assert notas[1].texto == "El frente norte mide 40 m."
    assert notas[2].referencia == 2


def test_el_consecutivo_va_sin_huecos() -> None:
    """Un salto es la señal de una nota retirada."""
    notas = _abierta()
    with pytest.raises(bit.BitacoraError, match="La siguiente nota es la 2"):
        bit.asentar(notas, _nota(7))


def test_aclarar_una_nota_que_no_existe_se_rechaza() -> None:
    notas = _abierta()
    with pytest.raises(bit.BitacoraError, match="no existe"):
        bit.asentar(notas, _nota(2, referencia=99))


def test_una_nota_sin_texto_no_se_asienta() -> None:
    with pytest.raises(bit.BitacoraError, match="no comunica nada"):
        bit.asentar(_abierta(), _nota(2, texto="   "))


def test_una_nota_sin_autor_no_se_asienta() -> None:
    with pytest.raises(bit.BitacoraError, match="sin autor"):
        bit.asentar(_abierta(), _nota(2, autor=""))


def test_despues_del_cierre_no_se_asienta_nada() -> None:
    notas = bit.asentar(_abierta(), _nota(2, tipo="cierre", texto="Se cierra la bitácora."))
    with pytest.raises(bit.BitacoraError, match="cerrada"):
        bit.asentar(notas, _nota(3))


def test_asentar_no_modifica_la_lista_que_recibe() -> None:
    """El módulo sólo agrega al final, y esa ausencia de mutación es la garantía."""
    original = _abierta()
    bit.asentar(original, _nota(2))
    assert len(original) == 1


def test_un_hueco_metido_por_fuera_se_grita() -> None:
    """asentar() no lo permite, pero un archivo se puede editar a mano."""
    st = bit.estado([_nota(1, tipo="apertura"), _nota(2), _nota(5)])
    assert any("Faltan las notas 3, 4" in a for a in st.avisos)
    assert any("valor probatorio" in a for a in st.avisos)


def test_una_bitacora_vacia_dice_que_no_esta_abierta() -> None:
    st = bit.estado([])
    assert not st.abierta
    assert st.siguiente_numero == 1
    assert any("art. 125" in a for a in st.avisos)


def test_si_solo_escribe_una_parte_sirve_de_diario_no_de_prueba() -> None:
    notas = [_nota(1, tipo="apertura")] + [_nota(n) for n in range(2, 7)]
    st = bit.estado(notas)
    assert any("una sola parte" in a and "art. 123" in a for a in st.avisos)


def test_dos_partes_escribiendo_no_generan_ese_aviso() -> None:
    notas = [_nota(1, tipo="apertura")] + [
        _nota(n, parte="contratista" if n % 2 else "contratante", autor="Ing. Ana Ruiz")
        for n in range(2, 7)
    ]
    st = bit.estado(notas)
    assert not any("una sola parte" in a for a in st.avisos)


def test_el_estado_ordena_por_consecutivo_aunque_lleguen_revueltas() -> None:
    st = bit.estado([_nota(3), _nota(1, tipo="apertura"), _nota(2)])
    assert [n.numero for n in st.notas] == [1, 2, 3]
    assert st.siguiente_numero == 4
    assert st.abierta and not st.cerrada
