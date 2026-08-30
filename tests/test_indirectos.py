"""Desglose de indirectos: la aritmética del documento, a mano."""

from klave_engine.costing.indirectos import (
    AnalisisFinanciamiento,
    DesgloseCampo,
    DesgloseOficinaCentral,
    RubroIndirecto,
    compute_financiamiento,
    documenta_campo,
    documenta_oficina,
)


def test_campo_mensual_por_meses_y_unicos_una_vez():
    desglose = DesgloseCampo(rubros=[
        RubroIndirecto(concepto="Renta de bodega", categoria="depreciacion_mantenimiento_rentas",
                       importe=10_000.0, base="mensual"),
        RubroIndirecto(concepto="Fianza de cumplimiento", categoria="seguros_fianzas",
                       importe=30_000.0, base="unico"),
    ])
    doc = documenta_campo(desglose, meses=6, plantilla_total=120_000.0, cargos_sin_sueldo=0)
    # 10,000 × 6 + 30,000 + 120,000 de plantilla = 210,000
    assert doc.total == 210_000.0
    personal = doc.renglones[0]
    assert personal.fuente == "plantilla de campo" and personal.importe == 120_000.0
    assert not any(r.sin_capturar for r in doc.renglones)


def test_campo_rubro_sin_importe_queda_visible_y_fuera_del_total():
    desglose = DesgloseCampo(rubros=[
        RubroIndirecto(concepto="Renta de bodega", importe=10_000.0, base="mensual"),
        RubroIndirecto(concepto="Vehículo de residente", importe=0.0, base="mensual"),
    ])
    doc = documenta_campo(desglose, meses=3, plantilla_total=0.0, cargos_sin_sueldo=0)
    assert doc.total == 30_000.0  # el rubro sin capturar no suma
    vacio = next(r for r in doc.renglones if r.concepto == "Vehículo de residente")
    assert vacio.sin_capturar and vacio.importe == 0.0
    assert any("sin importe capturado" in n for n in doc.notas)


def test_campo_plantilla_incompleta_se_dice():
    doc = documenta_campo(DesgloseCampo(), meses=4, plantilla_total=80_000.0, cargos_sin_sueldo=2)
    assert doc.total == 80_000.0
    assert any("sin sueldo" in n for n in doc.notas)


def test_oficina_prorratea_por_volumen_anual():
    oficina = DesgloseOficinaCentral(
        rubros=[RubroIndirecto(concepto="Renta de oficina", importe=600_000.0),
                RubroIndirecto(concepto="Nómina administrativa", importe=1_400_000.0)],
        volumen_anual_contratado=40_000_000.0,
    )
    doc = documenta_oficina(oficina, costo_directo=10_000_000.0)
    # 2,000,000 / 40,000,000 = 5 % → 500,000 en esta obra
    assert doc is not None and doc.total == 500_000.0
    assert any("5.0000 %" in n for n in doc.notas)


def test_oficina_sin_volumen_no_hay_analisis():
    oficina = DesgloseOficinaCentral(
        rubros=[RubroIndirecto(concepto="Renta", importe=600_000.0)],
        volumen_anual_contratado=0.0,
    )
    assert documenta_oficina(oficina, costo_directo=10_000_000.0) is None


def test_financiamiento_faltantes_nombra_lo_que_falta():
    a = AnalisisFinanciamiento(tasa_anual=12.0, indicador="TIIE 28 días")
    assert not a.completo
    assert a.faltantes() == ["fuente", "fecha de publicación"]
    b = AnalisisFinanciamiento(tasa_anual=12.0, indicador="TIIE 28 días",
                               fuente="Banxico SF43783", fecha_publicacion="2026-08-27")
    assert b.completo and b.faltantes() == []


def _analisis():
    return AnalisisFinanciamiento(tasa_anual=12.0, indicador="TIIE 28 días",
                                  fuente="Banxico SF43783", fecha_publicacion="2026-08-27")


def test_financiamiento_a_mano():
    # Tasa 12 % anual → 1 % mensual. Mes 1: saldo 100, costo 1.00.
    # Mes 2: saldo 100+100−250 = −50, costo −0.50. Total 0.50.
    doc = compute_financiamiento(_analisis(), egresos=[100.0, 100.0], ingresos=[0.0, 250.0])
    assert [p.saldo for p in doc.periodos] == [100.0, -50.0]
    assert [p.costo for p in doc.periodos] == [1.0, -0.5]
    assert doc.total == 0.5
    assert doc.indicador == "TIIE 28 días" and doc.fecha_publicacion == "2026-08-27"


def test_financiamiento_negativo_se_conserva():
    # Anticipo grande: el contratista trabaja con dinero ajeno y el costo es
    # negativo. Se conserva, jamás se recorta a cero.
    doc = compute_financiamiento(_analisis(), egresos=[100.0, 100.0], ingresos=[150.0, 50.0])
    assert [p.saldo for p in doc.periodos] == [-50.0, 0.0]
    assert doc.total == -0.5


from klave_engine.costing.indirectos import CargoAdicional
from klave_engine.costing.integration import integrate_costs, resolve_integration
from klave_engine.costing.models import (
    CostingConfig,
    FinancialConfig,
    IndirectsConfig,
    ScheduleActivity,
    WorkSchedule,
)
from klave_engine.costing.financial import build_financial_plan
from klave_engine.costing.plantilla import CargoCampo


def _schedule(months: int = 2) -> WorkSchedule:
    days = months * 24
    return WorkSchedule(
        activities=[ScheduleActivity(
            concept_code="EST-001", description="Obra", phase="Estructura",
            quantity=1.0, unit="LOTE", rendimiento_per_day=1.0, crews=1,
            duration_days=days, start_day=0, end_day=days, direct_cost=1_000_000.0,
        )],
        total_duration_days=days, workdays_per_month=24, phases=["Estructura"],
    )


def test_resolver_todo_declarado_sin_captura():
    config = CostingConfig()
    resolved = resolve_integration(config, None, 1_000_000.0, _schedule(), None)
    assert [c.code for c in resolved] == ["CI-C", "CI-O", "FI", "UT", "CA"]
    assert all(c.fuente == "declarado" for c in resolved)
    assert all(c.amount is None for c in resolved)
    # Nada capturado = nada que reclamar: sin faltantes ruidosos.
    assert all(not c.faltantes for c in resolved)
    assert resolved[0].pct == IndirectsConfig().field_indirects_pct


def test_resolver_campo_con_desglose_y_plantilla():
    config = CostingConfig()
    config.desglose_campo = DesgloseCampo(rubros=[
        RubroIndirecto(concepto="Renta de bodega", importe=10_000.0, base="mensual"),
    ])
    config.plantilla_campo = [CargoCampo(puesto="Residente de obra", salario_mensual=30_000.0, fsr=1.6)]
    resolved = resolve_integration(config, None, 1_000_000.0, _schedule(months=2), None)
    campo = resolved[0]
    # 10,000×2 + (30,000×1.6×2) = 20,000 + 96,000 = 116,000
    assert campo.fuente == "analisis" and campo.amount == 116_000.0
    assert campo.documento["por_periodo"] == [58_000.0, 58_000.0]


def test_resolver_oficina_parcial_reclama_el_volumen():
    config = CostingConfig()
    taller = {"oficina": {"rubros": [{"concepto": "Renta", "importe": 600_000.0}],
                          "volumen_anual_contratado": 0.0}}
    resolved = resolve_integration(config, taller, 1_000_000.0, _schedule(), None)
    oficina = resolved[1]
    assert oficina.fuente == "declarado"
    assert any("volumen anual" in f for f in oficina.faltantes)


def test_resolver_financiamiento_necesita_tasa_y_flujo():
    config = CostingConfig()
    config.financiamiento = AnalisisFinanciamiento(tasa_anual=12.0, indicador="TIIE 28 días")
    sched = _schedule()
    sin_flujo = resolve_integration(config, None, 1_000_000.0, sched, None)
    assert sin_flujo[2].fuente == "declarado"
    assert any("fuente" in f for f in sin_flujo[2].faltantes)  # análisis parcial: se reclama
    config.financiamiento = AnalisisFinanciamiento(
        tasa_anual=12.0, indicador="TIIE 28 días",
        fuente="Banxico SF43783", fecha_publicacion="2026-08-27")
    integration = integrate_costs(1_000_000.0, config.indirects)
    flujo = build_financial_plan(sched, integration, FinancialConfig())
    con_flujo = resolve_integration(config, None, 1_000_000.0, sched, flujo)
    fi = con_flujo[2]
    assert fi.fuente == "analisis" and fi.amount is not None
    assert fi.documento["periodos"], "el documento trae la tabla por periodo"


def test_resolver_cargos_itemizados():
    config = CostingConfig()
    config.cargos_adicionales = [
        CargoAdicional(concepto="Inspección y vigilancia", base_legal="5 al millar", pct=0.5),
        CargoAdicional(concepto="Impuesto estatal de obra", base_legal="2 al millar", pct=0.2),
    ]
    resolved = resolve_integration(config, None, 1_000_000.0, _schedule(), None)
    ca = resolved[4]
    assert ca.fuente == "analisis" and ca.amount is None and ca.pct == 0.7
    assert len(ca.documento["items"]) == 2


def test_utilidad_siempre_declarada():
    config = CostingConfig()
    resolved = resolve_integration(config, None, 1_000_000.0, _schedule(), None)
    assert resolved[3].code == "UT" and resolved[3].fuente == "declarado"


def test_share_de_oficina_solo_con_motivo_escrito():
    taller = {"oficina": {"rubros": [{"concepto": "Renta", "importe": 600_000.0}],
                          "volumen_anual_contratado": 40_000_000.0}}
    config = CostingConfig()
    config.oficina_share_pct = 3.0
    config.oficina_share_motivo = "corto"  # < 15 caracteres: no cuenta
    resolved = resolve_integration(config, taller, 1_000_000.0, _schedule(), None)
    oficina = resolved[1]
    assert oficina.amount == 15_000.0  # 1.5 % derivado del prorrateo, no el 3 %
    assert any("motivo" in f for f in oficina.faltantes)

    config.oficina_share_motivo = "obra fuera de la zona de cobertura de la oficina"
    resolved = resolve_integration(config, taller, 1_000_000.0, _schedule(), None)
    oficina = resolved[1]
    assert oficina.amount == 30_000.0 and oficina.fuente == "analisis"
    assert oficina.documento["override"] == 3.0


def test_resolver_campo_sin_programa_se_reclama():
    config = CostingConfig()
    config.desglose_campo = DesgloseCampo(rubros=[
        RubroIndirecto(concepto="Renta de bodega", importe=10_000.0, base="mensual"),
    ])
    resolved = resolve_integration(config, None, 1_000_000.0, None, None)
    campo = resolved[0]
    assert campo.fuente == "declarado"
    assert any("programa de obra" in f for f in campo.faltantes)


def test_resolver_financiamiento_completo_sin_flujo_se_reclama():
    config = CostingConfig()
    config.financiamiento = AnalisisFinanciamiento(
        tasa_anual=12.0, indicador="TIIE 28 días",
        fuente="Banxico SF43783", fecha_publicacion="2026-08-27")
    resolved = resolve_integration(config, None, 1_000_000.0, _schedule(), None)
    fi = resolved[2]
    assert fi.fuente == "declarado"
    assert any("flujo" in f for f in fi.faltantes)
