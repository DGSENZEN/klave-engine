"""El ajuste de costos: aritmética simple y una negativa firme a inventar índices."""

from klave_engine.costing import escalatoria as esc


def _indice(**valores: float) -> esc.Indice:
    return esc.Indice(
        nombre="INPP construcción",
        fuente="INEGI",
        publicacion="captura de prueba",
        valores=valores,
    )


def _renglon(**kw: object) -> esc.RenglonAjuste:
    base: dict[str, object] = dict(
        clave="OP-001", description="Muro", unit="m2", unit_price=500.0,
        quantity_contract=1000.0, quantity_executed=400.0,
    )
    base.update(kw)
    return esc.RenglonAjuste(**base)  # type: ignore[arg-type]


def test_sin_indice_no_hay_factor_y_lo_dice() -> None:
    """Un ajuste con índices inventados es un cobro sin sustento."""
    res = esc.calcular(esc.SolicitudAjuste(renglones=[_renglon()]))
    assert res.factor is None
    assert not res.calculable
    assert res.importe_ajuste == 0.0
    assert any("no guarda ninguno" in a for a in res.avisos)


def test_un_periodo_sin_valor_publicado_no_se_interpola() -> None:
    sol = esc.SolicitudAjuste(
        periodo_base="2026-01", periodo_ajuste="2026-06",
        # Hay enero y julio, pero no junio: interpolar sería inventar.
        indice=_indice(**{"2026-01": 100.0, "2026-07": 112.0}),
        renglones=[_renglon()],
    )
    res = esc.calcular(sol)
    assert res.factor is None
    assert any("no se interpola" in a.lower() or "No se interpola" in a for a in res.avisos)
    assert any("2026-06" in a for a in res.avisos)


def test_el_factor_es_la_razon_entre_los_dos_indices() -> None:
    sol = esc.SolicitudAjuste(
        periodo_base="2026-01", periodo_ajuste="2026-07",
        indice=_indice(**{"2026-01": 100.0, "2026-07": 112.0}),
        renglones=[_renglon()],
    )
    res = esc.calcular(sol)
    assert res.factor == 1.12
    # 600 m2 pendientes × $500 = $300,000; el 12 % son $36,000.
    assert res.importe_pendiente == 300_000.0
    assert res.importe_ajuste == 36_000.0


def test_lo_ya_estimado_queda_fuera_y_se_dice_cuanto() -> None:
    """Incluirlo convierte una solicitud legítima en una observación."""
    sol = esc.SolicitudAjuste(
        periodo_base="2026-01", periodo_ajuste="2026-07",
        indice=_indice(**{"2026-01": 100.0, "2026-07": 112.0}),
        renglones=[_renglon()],
    )
    res = esc.calcular(sol)
    assert any("$200,000.00 ya estimados" in a for a in res.avisos)
    assert any("art. 173" in a for a in res.avisos)


def test_el_atraso_propio_no_se_ajusta_a_este_periodo() -> None:
    """De otro modo atrasarse pagaría (RLOPSRM art. 176)."""
    sol = esc.SolicitudAjuste(
        periodo_base="2026-01", periodo_ajuste="2026-07",
        indice=_indice(**{"2026-01": 100.0, "2026-07": 112.0}),
        atraso_imputable_al_contratista=True,
        # El programa pedía 700 y sólo se ejecutaron 400: 300 de atraso propio.
        renglones=[_renglon(quantity_programada=700.0)],
    )
    res = esc.calcular(sol)
    assert res.importe_pendiente == 300_000.0
    assert res.importe_ajustable == 150_000.0  # 300 000 menos 150 000 de atraso
    assert res.importe_ajuste == 18_000.0
    assert any("art. 176" in a for a in res.avisos)


def test_marcar_atraso_sin_programa_avisa_en_vez_de_suponerlo() -> None:
    sol = esc.SolicitudAjuste(
        periodo_base="2026-01", periodo_ajuste="2026-07",
        indice=_indice(**{"2026-01": 100.0, "2026-07": 112.0}),
        atraso_imputable_al_contratista=True,
        renglones=[_renglon()],  # sin quantity_programada
    )
    res = esc.calcular(sol)
    assert res.importe_ajustable == 300_000.0
    assert any("no hay contra qué medirlo" in a for a in res.avisos)


def test_un_indice_que_baja_ajusta_a_favor_de_la_contratante() -> None:
    """El ajuste procede en los dos sentidos."""
    sol = esc.SolicitudAjuste(
        periodo_base="2026-01", periodo_ajuste="2026-07",
        indice=_indice(**{"2026-01": 110.0, "2026-07": 104.5}),
        renglones=[_renglon()],
    )
    res = esc.calcular(sol)
    assert res.factor == 0.95
    assert res.importe_ajuste == -15_000.0
    assert any("los dos sentidos" in a for a in res.avisos)


def test_un_indice_base_en_cero_no_divide() -> None:
    sol = esc.SolicitudAjuste(
        periodo_base="2026-01", periodo_ajuste="2026-07",
        indice=_indice(**{"2026-01": 0.0, "2026-07": 112.0}),
        renglones=[_renglon()],
    )
    res = esc.calcular(sol)
    assert res.factor is None
    assert any("no se puede dividir" in a for a in res.avisos)


def test_un_concepto_terminado_no_deja_nada_pendiente() -> None:
    r = _renglon(quantity_executed=1000.0)
    assert r.quantity_pendiente == 0.0
    assert r.importe_pendiente == 0.0


def test_ejecutar_de_mas_no_produce_pendiente_negativo() -> None:
    r = _renglon(quantity_executed=1200.0)
    assert r.quantity_pendiente == 0.0


def test_ir_adelantado_no_cuenta_como_atraso() -> None:
    r = _renglon(quantity_executed=800.0, quantity_programada=700.0)
    assert r.atraso == 0.0
