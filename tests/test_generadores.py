"""El generador manda sobre la cantidad, y una dimensión que falta es un hueco."""

import pytest
from klave_engine.costing import generadores as gen


def _linea(**kw: object) -> gen.LineaGenerador:
    return gen.LineaGenerador(**kw)  # type: ignore[arg-type]


def test_area_multiplica_largo_por_ancho_y_no_toca_la_altura() -> None:
    """Un concepto en m2 no tiene altura, aunque venga capturada."""
    res = gen.calcular(
        [_linea(ubicacion="Eje A-3", largo=4.0, ancho=2.5, alto=99.0)], "m2", 10.0
    )
    assert res.total == 10.0
    assert res.lineas[0].formula == "4 × 2.5"
    assert res.cuadra


def test_volumen_multiplica_las_tres() -> None:
    res = gen.calcular([_linea(largo=3.0, ancho=2.0, alto=0.5)], "m3", 3.0)
    assert res.total == 3.0
    assert res.lineas[0].formula == "3 × 2 × 0.5"


def test_las_veces_multiplican_y_se_ven_en_la_formula() -> None:
    res = gen.calcular(
        [_linea(ubicacion="Zapatas Z-1", veces=4, largo=1.5, ancho=1.5, alto=0.4)],
        "m3", 3.6,
    )
    assert res.total == 3.6
    assert res.lineas[0].formula == "4 × 1.5 × 1.5 × 0.4"
    assert res.cuadra


def test_una_dimension_que_falta_no_se_rellena_con_uno() -> None:
    """La tentación es poner 1.00 y seguir. Eso da un número plausible y falso."""
    res = gen.calcular([_linea(ubicacion="Muro norte", largo=6.0)], "m2", 6.0)

    assert res.lineas[0].medida is None
    assert res.lineas[0].falta == ("ancho",)
    assert res.total == 0.0
    assert not res.cuadra
    assert any("no se rellenan con 1.00" in a for a in res.avisos)


def test_una_linea_incompleta_impide_cuadrar_aunque_el_resto_de_el_numero() -> None:
    """El faltante podría ser justo lo que sobra."""
    res = gen.calcular(
        [_linea(largo=4.0, ancho=2.5), _linea(ubicacion="Pendiente", largo=3.0)],
        "m2", 10.0,
    )
    assert res.total == 10.0
    assert res.diferencia == 0.0
    assert res.incompletas == 1
    assert not res.cuadra


def test_la_diferencia_se_dice_con_las_dos_cifras_y_su_direccion() -> None:
    res = gen.calcular([_linea(largo=10.0, ancho=10.0)], "m2", 120.0)
    aviso = next(a for a in res.avisos if "suma" in a)
    assert "100" in aviso and "120" in aviso
    assert "en la cantidad cobrada" in aviso
    assert "La cantidad sale del generador, no al revés." in aviso


def test_cobrar_sin_una_sola_linea_de_generador_se_dice() -> None:
    res = gen.calcular([], "m2", 320.0)
    assert any("sin una sola línea de generador" in a for a in res.avisos)
    assert not res.cuadra


def test_no_cobrar_nada_sin_generador_no_es_un_problema() -> None:
    res = gen.calcular([], "m2", 0.0)
    assert res.avisos == []


def test_una_unidad_sin_dimensiones_cuenta_las_veces() -> None:
    res = gen.calcular(
        [_linea(ubicacion="Nivel 1", veces=12), _linea(ubicacion="Nivel 2", veces=8)],
        "pza", 20.0,
    )
    assert res.total == 20.0
    assert res.cuadra


def test_la_medida_directa_manda_sobre_las_dimensiones() -> None:
    """Kilos de acero salen de una lista de habilitado, no de multiplicar."""
    res = gen.calcular(
        [_linea(ubicacion="Trabe TR-1", medida_directa=847.5, largo=99.0)], "kg", 847.5
    )
    assert res.total == 847.5
    assert res.lineas[0].formula == "847.5"


def test_una_unidad_desconocida_pide_la_medida_a_mano_sin_inventar_formula() -> None:
    res = gen.calcular([_linea(ubicacion="Tramo 1", largo=5.0)], "curva", 5.0)
    assert res.lineas[0].medida is None
    assert res.lineas[0].falta == ("medida_directa",)
    assert any("no tiene una fórmula conocida" in a for a in res.avisos)


@pytest.mark.parametrize("unidad", ["m2", "M2", " m² ", "m3", "kg", "pza", "sal", "jor"])
def test_las_unidades_reales_de_los_catalogos_se_reconocen(unidad: str) -> None:
    assert gen.dimensiones_de(unidad) is not None


def test_el_redondeo_de_cinta_metrica_no_es_un_error() -> None:
    res = gen.calcular([_linea(largo=4.0, ancho=2.5)], "m2", 10.002)
    assert res.cuadra


# --- Cómo se ve desde la estimación -----------------------------------------


def _estimacion(renglon: dict) -> object:
    from klave_engine.costing.estimaciones import Estimacion, RenglonEstimado

    base = dict(
        clave="OP-001", description="Muro de tabique", unit="m2", unit_price=500.0,
        quantity_period=100.0, quantity_previous=0.0, quantity_contract=300.0,
    )
    base.update(renglon)
    return Estimacion(
        numero=1, periodo_inicio="2026-02-01", periodo_fin="2026-02-28",
        monto_contrato=150_000.0,
        renglones=[RenglonEstimado(**base)],  # type: ignore[arg-type]
    )


def test_la_estimacion_avisa_de_lo_que_se_cobra_sin_generador() -> None:
    from klave_engine.costing.estimaciones import calcular

    resumen = calcular(_estimacion({}))  # type: ignore[arg-type]
    assert any("sin números generadores" in a for a in resumen.avisos)


def test_un_generador_que_cuadra_no_genera_ruido() -> None:
    from klave_engine.costing.estimaciones import calcular

    resumen = calcular(  # type: ignore[arg-type]
        _estimacion({"generador": [_linea(ubicacion="Eje A", largo=20.0, ancho=5.0)]})
    )
    assert not any("generador" in a for a in resumen.avisos)


def test_un_generador_que_no_cuadra_sale_con_las_dos_cifras() -> None:
    from klave_engine.costing.estimaciones import calcular

    resumen = calcular(  # type: ignore[arg-type]
        _estimacion({"generador": [_linea(ubicacion="Eje A", largo=20.0, ancho=4.0)]})
    )
    aviso = next(a for a in resumen.avisos if "no cuadra" in a)
    assert "80" in aviso and "100" in aviso
    assert "La cantidad sale del generador, no al revés." in aviso


def test_la_estimacion_no_corrige_la_cantidad_por_su_cuenta() -> None:
    """Avisar sí, reescribir no: quien midió decide, y puede estar a medio capturar."""
    from klave_engine.costing.estimaciones import calcular

    est = _estimacion({"generador": [_linea(largo=20.0, ancho=4.0)]})
    calcular(est)  # type: ignore[arg-type]
    assert est.renglones[0].quantity_period == 100.0  # type: ignore[attr-defined]


def test_los_avisos_concuerdan_en_numero() -> None:
    """«1 conceptos rebasan» delata que el aviso lo escribió una plantilla."""
    from klave_engine.costing.estimaciones import calcular

    uno = calcular(_estimacion({}))  # type: ignore[arg-type]
    aviso = next(a for a in uno.avisos if "generadores" in a)
    assert "1 de 1 concepto se cobra sin" in aviso
