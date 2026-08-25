"""La cuenta que cierra el contrato: cada saldo con su nombre y su signo."""

from klave_engine.costing import finiquito


def _base(**kw: object) -> finiquito.Finiquito:
    datos: dict[str, object] = dict(
        fecha="2026-08-01", monto_contrato=1_000_000.0, ejecutado=1_000_000.0,
        pagado=1_000_000.0, anticipo_otorgado=300_000.0, anticipo_amortizado=300_000.0,
        retenciones_aplicadas=50_000.0,
    )
    datos.update(kw)
    return finiquito.Finiquito(**datos)  # type: ignore[arg-type]


def test_la_retencion_vuelve_al_contratista() -> None:
    res = finiquito.calcular(_base())
    devolucion = [s for s in res.saldos if "garantía" in s.concepto]
    assert len(devolucion) == 1
    assert devolucion[0].importe == 50_000.0
    assert res.saldo_final == 50_000.0
    assert res.a_favor_de == "contratista"


def test_la_retencion_sustituida_por_fianza_no_se_devuelve() -> None:
    res = finiquito.calcular(_base(retencion_sustituida_por_fianza=True))
    assert not any("garantía" in s.concepto for s in res.saldos)
    assert res.saldo_final == 0.0
    assert res.a_favor_de == "nadie"
    assert any("fianza" in a for a in res.avisos)


def test_el_anticipo_sin_amortizar_es_un_saldo_contra_el_contratista() -> None:
    """Obra ejecutada por debajo de lo contratado: la amortización proporcional
    no alcanza y el remanente se reintegra."""
    res = finiquito.calcular(
        _base(ejecutado=800_000.0, pagado=800_000.0, anticipo_amortizado=240_000.0)
    )
    remanente = [s for s in res.saldos if "Anticipo" in s.concepto]
    assert remanente[0].importe == -60_000.0
    assert remanente[0].a_favor == "contratante"
    # 50 000 de retención menos 60 000 de anticipo.
    assert res.saldo_final == -10_000.0
    assert res.a_favor_de == "contratante"


def test_amortizar_de_mas_avisa_en_lugar_de_pasar_callado() -> None:
    res = finiquito.calcular(_base(anticipo_amortizado=320_000.0))
    assert any("más de lo que recibió" in a for a in res.avisos)


def test_la_pena_se_calcula_sobre_lo_no_ejecutado() -> None:
    """RLOPSRM art. 86: la base es el monto de los trabajos que no se hicieron
    en la fecha pactada, no el contrato completo."""
    res = finiquito.calcular(
        _base(ejecutado=900_000.0, pagado=900_000.0, anticipo_amortizado=270_000.0,
              dias_atraso=10, pena_pct_diario=0.1)
    )
    pena = [s for s in res.saldos if "Pena" in s.concepto]
    # 100 000 no ejecutados * 0.1 % * 10 días.
    assert pena[0].importe == -1_000.0
    assert "art. 86" in pena[0].razon


def test_atraso_sin_porcentaje_pactado_avisa_y_no_inventa() -> None:
    res = finiquito.calcular(_base(dias_atraso=15))
    assert not any("Pena" in s.concepto for s in res.saldos)
    assert any("lo fija el contrato" in a for a in res.avisos)


def test_lo_ejecutado_y_no_pagado_sale_como_saldo_propio() -> None:
    res = finiquito.calcular(_base(pagado=950_000.0))
    pendiente = [s for s in res.saldos if "no pagadas" in s.concepto]
    assert pendiente[0].importe == 50_000.0


def test_los_saldos_no_se_compensan_antes_de_mostrarse() -> None:
    """Un finiquito que sólo enseña el resultado es uno que nadie puede revisar."""
    res = finiquito.calcular(
        _base(ejecutado=900_000.0, pagado=900_000.0, anticipo_amortizado=270_000.0,
              dias_atraso=10, pena_pct_diario=0.1)
    )
    assert [s.concepto for s in res.saldos] == [
        "Devolución del fondo de garantía",
        "Anticipo no amortizado",
        "Pena convencional por atraso",
    ]
    assert res.saldo_final == round(50_000.0 - 30_000.0 - 1_000.0, 2)


def test_ejecutar_muy_por_debajo_del_contrato_pide_explicacion() -> None:
    res = finiquito.calcular(
        _base(ejecutado=700_000.0, pagado=700_000.0, anticipo_amortizado=300_000.0)
    )
    assert any("70.0 %" in a and "qué no se hizo" in a for a in res.avisos)
