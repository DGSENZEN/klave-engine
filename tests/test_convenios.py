"""El techo del art. 59 y lo que un convenio le hace al catálogo."""

from klave_engine.costing import convenios
from klave_engine.costing.estimaciones import Estimacion, RenglonEstimado


def _convenio(numero: int, *renglones: convenios.RenglonConvenio) -> convenios.Convenio:
    return convenios.Convenio(numero=numero, fecha="2026-03-01", renglones=list(renglones))


def _renglon(clave: str, precio: float, nueva: float, anterior: float) -> convenios.RenglonConvenio:
    return convenios.RenglonConvenio(
        clave=clave, description=clave, unit="m2", unit_price=precio,
        quantity=nueva, quantity_anterior=anterior,
    )


def test_el_delta_es_contra_lo_que_ya_estaba_contratado() -> None:
    r = _renglon("OP-001", 100.0, nueva=120.0, anterior=100.0)
    assert r.delta_cantidad == 20.0
    assert r.delta_importe == 2000.0
    assert not r.es_nuevo


def test_un_concepto_que_no_existia_es_nuevo_y_cuenta_completo() -> None:
    r = _renglon("OP-099", 50.0, nueva=10.0, anterior=0.0)
    assert r.es_nuevo
    assert r.delta_importe == 500.0


def test_tres_convenios_del_diez_por_ciento_rebasan_el_techo() -> None:
    """El error clásico: cada uno cabe, los tres juntos no.

    El art. 59 limita los convenios *en conjunto* al 25 % del monto original,
    no uno por uno."""
    convs = [
        _convenio(n, _renglon(f"OP-00{n}", 1000.0, nueva=110.0, anterior=100.0))
        for n in (1, 2, 3)
    ]
    st = convenios.estado(convs, monto_original=100_000.0, plazo_original_dias=180)

    assert st.monto_convenido == 30_000.0
    assert st.monto_pct == 30.0
    assert st.rebasa_techo
    assert any("art. 59" in a and "25 %" in a for a in st.avisos)


def test_cerca_del_techo_avisa_cuanto_margen_queda() -> None:
    conv = _convenio(1, _renglon("OP-001", 1000.0, nueva=122.0, anterior=100.0))
    st = convenios.estado([conv], monto_original=100_000.0, plazo_original_dias=180)

    assert st.monto_pct == 22.0
    assert not st.rebasa_techo
    # 25 % de 100 000 son 25 000; ya se usaron 22 000.
    assert any("$3,000.00" in a for a in st.avisos)


def test_el_plazo_tiene_su_propio_techo() -> None:
    conv = convenios.Convenio(numero=1, fecha="2026-03-01", tipo="plazo", dias_plazo=60)
    st = convenios.estado([conv], monto_original=100_000.0, plazo_original_dias=180)

    assert st.plazo_vigente_dias == 240
    assert st.plazo_pct == 33.33
    assert st.rebasa_techo
    assert any("plazo" in a for a in st.avisos)


def test_conceptos_nuevos_disparan_el_aviso_de_variacion_sustancial() -> None:
    conv = _convenio(1, _renglon("OP-099", 50.0, nueva=10.0, anterior=0.0))
    st = convenios.estado([conv], monto_original=100_000.0, plazo_original_dias=180)
    assert any("sustanciales" in a for a in st.avisos)


def test_un_convenio_posterior_manda_sobre_uno_anterior() -> None:
    """Modificar significa que el último firmado es el que rige."""
    vigente = convenios.catalogo_vigente(
        {"OP-001": 100.0, "OP-002": 50.0},
        [
            _convenio(2, _renglon("OP-001", 1.0, nueva=140.0, anterior=120.0)),
            _convenio(1, _renglon("OP-001", 1.0, nueva=120.0, anterior=100.0)),
        ],
    )
    assert vigente["OP-001"] == 140.0
    assert vigente["OP-002"] == 50.0


def test_el_borrador_nace_de_lo_que_la_estimacion_no_pudo_cobrar() -> None:
    est = Estimacion(
        numero=1, periodo_inicio="2026-02-01", periodo_fin="2026-02-28",
        renglones=[
            RenglonEstimado(
                clave="OP-001", description="Muro", unit="m2", unit_price=100.0,
                quantity_period=320.0, quantity_previous=0.0, quantity_contract=300.0,
            ),
            RenglonEstimado(
                clave="OP-002", description="Firme", unit="m2", unit_price=80.0,
                quantity_period=50.0, quantity_previous=0.0, quantity_contract=100.0,
            ),
        ],
    )
    conv = convenios.desde_estimacion(est, numero=1, fecha="2026-03-01")

    # Sólo entra el que se excedió.
    assert [r.clave for r in conv.renglones] == ["OP-001"]
    assert conv.renglones[0].quantity == 320.0
    assert conv.renglones[0].quantity_anterior == 300.0
    assert conv.importe == 2000.0
    # El motivo lo escribe una persona: la ley pide causa justificada.
    assert conv.motivo == ""


def test_sin_convenios_el_contrato_es_el_original() -> None:
    st = convenios.estado([], monto_original=100_000.0, plazo_original_dias=180)
    assert st.monto_vigente == 100_000.0
    assert st.plazo_vigente_dias == 180
    assert not st.rebasa_techo
    assert st.avisos == []


def test_avisa_cuando_el_catalogo_y_las_estimaciones_no_hablan_del_mismo_contrato() -> None:
    """Un porcentaje seguro sobre una base equivocada es peor que ninguno."""
    conv = _convenio(1, _renglon("OP-001", 1000.0, nueva=110.0, anterior=100.0))
    st = convenios.estado(
        [conv], monto_original=100_000.0, plazo_original_dias=180,
        monto_capturado=250_000.0,
    )
    assert st.monto_pct == 10.0  # el número sale igual: esconderlo no ayuda
    assert any("no coincidan" in a or "base distinta" in a for a in st.avisos)


def test_bases_que_coinciden_no_generan_ruido() -> None:
    conv = _convenio(1, _renglon("OP-001", 1000.0, nueva=110.0, anterior=100.0))
    st = convenios.estado(
        [conv], monto_original=100_000.0, plazo_original_dias=180,
        monto_capturado=100_000.0,
    )
    assert st.avisos == []
