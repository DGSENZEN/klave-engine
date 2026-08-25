"""Estimaciones: lo que de verdad se cobra cada mes, con sus descuentos.

El presupuesto se hace una vez y la obra se cobra veinte. La aritmética de
aquí es la que un residente rehace a mano cada periodo y la que una
contratante revisa antes de pagar.
"""

from klave_engine.costing.estimaciones import (
    Deductiva,
    Estimacion,
    RenglonEstimado,
    calcular,
    siguiente,
)


def _renglon(clave: str, contratado: float, periodo: float, previo: float = 0.0,
             pu: float = 100.0) -> RenglonEstimado:
    return RenglonEstimado(
        clave=clave, description=f"Concepto {clave}", unit="M2", unit_price=pu,
        quantity_contract=contratado, quantity_period=periodo, quantity_previous=previo,
    )


def _estimacion(**kw) -> Estimacion:
    base = dict(
        numero=1, periodo_inicio="2026-09-01", periodo_fin="2026-09-30",
        anticipo_pct=30.0, retencion_pct=5.0, monto_contrato=1_000_000.0,
    )
    base.update(kw)
    return Estimacion(**base)


def test_de_lo_medido_a_lo_que_se_cobra():
    """La carátula: importe, amortización, retención y líquido."""
    est = _estimacion(renglones=[_renglon("A", 1000.0, 100.0), _renglon("B", 500.0, 50.0)])
    r = calcular(est)
    assert r.importe == 15_000.0                    # 150 m² × $100
    assert r.amortizacion == 4_500.0                # 30 % de lo estimado
    assert r.retencion == 750.0                     # 5 %
    assert r.liquido == 15_000.0 - 4_500.0 - 750.0
    assert r.acumulado == 15_000.0


def test_el_anticipo_se_amortiza_al_mismo_porcentaje_al_que_se_recibio():
    """Así queda saldado exactamente cuando la obra termina, que es lo que
    pide el art. 132 — no antes ni después."""
    est = _estimacion(renglones=[_renglon("A", 10_000.0, 10_000.0)])
    r = calcular(est)
    assert r.importe == 1_000_000.0
    assert r.amortizacion == 300_000.0              # justo el anticipo entero
    assert r.amortizacion == est.monto_contrato * est.anticipo_pct / 100


def test_la_amortizacion_nunca_pasa_de_lo_que_queda_del_anticipo():
    """Y cuando se topa, lo dice: a partir de ahí las estimaciones ya no
    amortizan y el flujo del contratista cambia."""
    est = _estimacion(
        renglones=[_renglon("A", 10_000.0, 1_000.0)],
        amortizado_previo=290_000.0,
    )
    r = calcular(est)
    assert r.amortizacion == 10_000.0               # quedaban 10 mil, no 30 mil
    assert any("se topó" in a for a in r.avisos)


def test_lo_ya_estimado_no_se_cobra_dos_veces():
    est = _estimacion(renglones=[_renglon("A", 1000.0, periodo=200.0, previo=300.0)])
    r = calcular(est)
    assert r.importe == 20_000.0                    # sólo lo de este periodo
    assert r.acumulado == 50_000.0                  # 500 m² acumulados
    assert est.renglones[0].pct_avance == 50.0


def test_rebasar_el_catalogo_contratado_se_dice_en_vez_de_dejarlo_pasar():
    """Pasarse del catálogo firmado necesita convenio, no una estimación más."""
    est = _estimacion(renglones=[_renglon("A", 1000.0, periodo=200.0, previo=900.0)])
    r = calcular(est)
    aviso = " ".join(r.avisos)
    assert "rebasan la cantidad del catálogo" in aviso
    assert "convenio" in aviso and "art. 132" in aviso


def test_las_deductivas_bajan_el_liquido_y_llevan_su_razon():
    est = _estimacion(
        renglones=[_renglon("A", 1000.0, 100.0)],
        deductivas=[Deductiva(concepto="Pena por atraso", importe=1_000.0,
                              razon="5 días sobre el programa")],
    )
    r = calcular(est)
    assert r.importe == 10_000.0                    # 100 m² × $100
    assert r.deductivas == 1_000.0
    assert r.liquido == 10_000.0 - 3_000.0 - 500.0 - 1_000.0


def test_un_liquido_negativo_se_avisa_antes_de_presentarla():
    est = _estimacion(
        renglones=[_renglon("A", 1000.0, 10.0)],       # $1,000 estimados
        deductivas=[Deductiva(concepto="Materiales de la contratante",
                              importe=5_000.0)],
    )
    r = calcular(est)
    assert r.liquido < 0
    assert any("negativo" in a for a in r.avisos)


def test_una_estimacion_sin_medir_no_es_una_estimacion():
    """No hay «porcentaje de avance» que reparta importes: cada renglón lleva
    la cantidad que alguien midió en obra."""
    r = calcular(_estimacion(renglones=[]))
    assert r.importe == 0.0
    assert any("alguien midió en obra" in a for a in r.avisos)


def test_la_siguiente_estimacion_carga_sola_lo_acumulado():
    """Encadenar a mano es como se cobra dos veces el mismo metro."""
    primera = _estimacion(renglones=[_renglon("A", 1000.0, 400.0)])
    segunda = siguiente(primera, 2, "2026-10-01", "2026-10-31")
    assert segunda.numero == 2
    assert segunda.renglones[0].quantity_previous == 400.0
    assert segunda.renglones[0].quantity_period == 0.0
    assert segunda.amortizado_previo == calcular(primera).amortizacion
    assert segunda.monto_contrato == primera.monto_contrato


def test_el_avance_de_la_obra_es_contra_el_contrato():
    est = _estimacion(renglones=[_renglon("A", 10_000.0, 2_500.0)])
    assert calcular(est).avance_pct == 25.0
