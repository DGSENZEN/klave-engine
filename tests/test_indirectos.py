"""Desglose de indirectos: la aritmética del documento, a mano."""

from klave_engine.costing.financial import build_financial_plan
from klave_engine.costing.indirectos import (
    AnalisisFinanciamiento,
    CargoAdicional,
    ComponenteResuelto,
    DesgloseCampo,
    DesgloseOficinaCentral,
    RubroIndirecto,
    compute_financiamiento,
    documenta_campo,
    documenta_oficina,
)
from klave_engine.costing.integration import integrate_costs, resolve_integration
from klave_engine.costing.models import (
    CostingConfig,
    FinancialConfig,
    IndirectsConfig,
    ScheduleActivity,
    WorkSchedule,
)
from klave_engine.costing.plantilla import CargoCampo
from klave_engine.costing.report import _integrate_with_analyses


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
    config.plantilla_campo = [CargoCampo(
        puesto="Residente de obra", salario_mensual=30_000.0, fsr=1.6)]
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


def test_resolver_campo_vacio_cae_en_declarado_silencioso():
    # DesgloseCampo(rubros=[]) sin plantilla: nada se capturó nunca, ni un
    # renglón. Cae en declarado sin regaños, la misma doctrina que un
    # desglose ausente — no un "análisis" en $0.
    config = CostingConfig()
    config.desglose_campo = DesgloseCampo(rubros=[])
    resolved = resolve_integration(config, None, 1_000_000.0, _schedule(), None)
    campo = resolved[0]
    assert campo.fuente == "declarado"
    assert campo.pct == IndirectsConfig().field_indirects_pct
    assert campo.faltantes == []


def test_resolver_campo_rubro_en_cero_reclama_que_no_suma():
    # Un renglón sí se capturó, pero en $0: a medias, no vacío — se reclama.
    config = CostingConfig()
    config.desglose_campo = DesgloseCampo(rubros=[
        RubroIndirecto(concepto="Renta de bodega", importe=0.0, base="mensual"),
    ])
    resolved = resolve_integration(config, None, 1_000_000.0, _schedule(), None)
    campo = resolved[0]
    assert campo.fuente == "declarado"
    assert any("no suma" in f for f in campo.faltantes)


def test_taller_financiamiento_en_blanco_no_reclama_nada():
    # El web siempre manda las dos mitades del PUT: guardar sólo la oficina
    # deja financiamiento como puros defaults, truthy como dict pero vacío
    # como captura. No debe adoptarse ni reclamar sus cuatro faltantes.
    config = CostingConfig()
    taller = {"financiamiento": {"tasa_anual": 0, "indicador": "", "fuente": "",
                                 "fecha_publicacion": ""}}
    resolved = resolve_integration(config, taller, 1_000_000.0, _schedule(), None)
    fi = resolved[2]
    assert fi.fuente == "declarado"
    assert fi.faltantes == []


def test_config_financiamiento_en_blanco_cuenta_como_ausente():
    config = CostingConfig()
    config.financiamiento = AnalisisFinanciamiento()  # todo en su valor por defecto
    resolved = resolve_integration(config, None, 1_000_000.0, _schedule(), None)
    fi = resolved[2]
    assert fi.fuente == "declarado"
    assert fi.faltantes == []


def test_resolver_financiamiento_completo_sin_flujo_se_reclama():
    config = CostingConfig()
    config.financiamiento = AnalisisFinanciamiento(
        tasa_anual=12.0, indicador="TIIE 28 días",
        fuente="Banxico SF43783", fecha_publicacion="2026-08-27")
    resolved = resolve_integration(config, None, 1_000_000.0, _schedule(), None)
    fi = resolved[2]
    assert fi.fuente == "declarado"
    assert any("flujo" in f for f in fi.faltantes)


def test_integrate_declarado_identico_a_hoy():
    # La garantía de regresión del modo dual: sin resolved, la aritmética de
    # siempre (los importes encadenados, verificados a mano para el primero).
    config = IndirectsConfig()
    antes = integrate_costs(1_000_000.0, config)
    despues = integrate_costs(1_000_000.0, config, resolved=None)
    assert antes.model_dump() == despues.model_dump()
    assert [linea.code for linea in antes.lines] == ["CI-C", "CI-O", "FI", "UT", "CA"]
    assert antes.lines[0].amount == 80_000.0  # 8 % de 1,000,000, a mano
    assert antes.lines[2].base == 1_130_000.0  # FI corre sobre CD+CI
    assert all(line.fuente == "declarado" for line in antes.lines)


def test_integrate_amounts_mandan_y_el_pct_es_derivado():
    config = IndirectsConfig()
    resolved = [
        ComponenteResuelto(code="CI-C", amount=116_000.0, fuente="analisis"),
        ComponenteResuelto(code="CI-O", pct=5.0),
        ComponenteResuelto(code="FI", pct=1.5),
        ComponenteResuelto(code="UT", pct=10.0),
        ComponenteResuelto(code="CA", pct=0.5),
    ]
    integration = integrate_costs(1_000_000.0, config, resolved=resolved)
    campo = integration.lines[0]
    assert campo.amount == 116_000.0 and campo.fuente == "analisis"
    assert campo.percentage == 11.6  # derivado del importe, no al revés
    # El documento y el presupuesto no pueden discrepar ni por un centavo:
    assert campo.amount == round(1_000_000.0 * campo.percentage / 100.0, 2)


def test_integrate_pct_resuelto_reemplaza_al_de_config():
    config = IndirectsConfig()  # additional_charges_pct = 0.5
    resolved = resolve_integration(CostingConfig(), None, 1_000_000.0, _schedule(), None)
    resolved[4] = ComponenteResuelto(code="CA", pct=0.7, fuente="analisis")
    integration = integrate_costs(1_000_000.0, config, resolved=resolved)
    ca = integration.lines[4]
    assert ca.percentage == 0.7 and ca.fuente == "analisis"


def _config_analisis_total() -> CostingConfig:
    config = CostingConfig()
    config.desglose_campo = DesgloseCampo(rubros=[
        RubroIndirecto(concepto="Renta de bodega", importe=10_000.0, base="mensual")])
    config.plantilla_campo = [CargoCampo(puesto="Residente de obra",
                                         salario_mensual=30_000.0, fsr=1.6)]
    config.financiamiento = AnalisisFinanciamiento(
        tasa_anual=12.0, indicador="TIIE 28 días",
        fuente="Banxico SF43783", fecha_publicacion="2026-08-27")
    return config


def test_iteracion_converge_y_los_totales_se_estabilizan():
    warnings: list[str] = []
    resolved, integration, financial = _integrate_with_analyses(
        1_000_000.0, _config_analisis_total(), None, _schedule(months=2), "MXN", warnings)
    fi = next(c for c in resolved if c.code == "FI")
    assert fi.fuente == "analisis"
    # Punto fijo: reintegrar con lo resuelto no mueve el total ni un centavo.
    again = integrate_costs(1_000_000.0, _config_analisis_total().indirects, resolved=resolved)
    assert abs(again.grand_total - integration.grand_total) < 0.01
    assert not any("no convergió" in w for w in warnings)
    # El pct derivado del análisis se rellena en el componente resuelto, no
    # se queda en el 0.0 de fábrica junto a la insignia de "análisis".
    campo = next(c for c in resolved if c.code == "CI-C")
    linea = next(line for line in integration.lines if line.code == "CI-C")
    assert campo.pct == linea.percentage
    assert campo.pct != 0.0


def test_modo_declarado_una_pasada_numeros_de_siempre():
    warnings: list[str] = []
    resolved, integration, _ = _integrate_with_analyses(
        1_000_000.0, CostingConfig(), None, _schedule(), "MXN", warnings)
    assert all(c.fuente == "declarado" for c in resolved)
    assert integration.model_dump(exclude={"lines"}) == integrate_costs(
        1_000_000.0, IndirectsConfig()).model_dump(exclude={"lines"})
    assert warnings == []


def test_faltantes_parciales_llegan_como_warnings():
    config = CostingConfig()
    config.financiamiento = AnalisisFinanciamiento(tasa_anual=12.0)  # a medias
    warnings: list[str] = []
    _integrate_with_analyses(1_000_000.0, config, None, _schedule(), "MXN", warnings)
    assert any("Integración (FI)" in w and "sin indicador" in w for w in warnings)


def test_congruencia_de_plantilla_solo_en_modo_declarado():
    from klave_engine.costing.models import BillOfQuantities
    from klave_engine.costing.report import _warn_plantilla_vs_indirectos

    config = CostingConfig()
    config.plantilla_campo = [CargoCampo(puesto="Residente de obra",
                                         salario_mensual=80_000.0, fsr=1.6)]
    sched = _schedule(months=2)
    # Plantilla 256,000 contra indirectos de campo de 100,000: desajuste real.
    declarado = BillOfQuantities(project_id="p")
    _warn_plantilla_vs_indirectos(declarado, config, sched, 100_000.0,
                                  ci_c_fuente="declarado")
    assert any("plantilla" in w for w in declarado.warnings)
    # En modo análisis la plantilla está DENTRO del desglose: comparar sería
    # compararla consigo misma, y el aviso no existe.
    analisis = BillOfQuantities(project_id="p")
    _warn_plantilla_vs_indirectos(analisis, config, sched, 100_000.0,
                                  ci_c_fuente="analisis")
    assert analisis.warnings == []


def test_faltantes_de_analisis_no_dicen_declarado():
    # Desglose capturado (modo análisis) con un rubro sin importe: el
    # componente sigue siendo "analisis", no "declarado" — el aviso no
    # puede decir que sigue por porcentaje declarado.
    config = CostingConfig()
    config.desglose_campo = DesgloseCampo(rubros=[
        RubroIndirecto(concepto="Renta de bodega", importe=10_000.0, base="mensual"),
        RubroIndirecto(concepto="Vehículo de residente", importe=0.0, base="mensual"),
    ])
    warnings: list[str] = []
    _integrate_with_analyses(1_000_000.0, config, None, _schedule(months=2), "MXN", warnings)
    ci_c = [w for w in warnings if w.startswith("Integración (CI-C):")]
    assert any("incompleto" in w for w in ci_c)
    assert not any("sigue por porcentaje declarado" in w for w in ci_c)
