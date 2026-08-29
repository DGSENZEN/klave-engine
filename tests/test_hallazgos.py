"""Rationalized findings: consequence first, money where it is knowable,
and nothing silently swallowed."""

from klave_engine.costing.hallazgos import diagnose
from klave_engine.costing.models import (
    BillOfQuantities,
    BoqLine,
    CostIntegration,
    CostReport,
    QuantityKind,
    WorkSchedule,
)
from klave_engine.costing.reviews import ProjectReviews
from klave_engine.dxf.units import DrawingUnits


def _line(code="EST-002", quantity=10.0, amount=1000.0, unpriced=False, unit="M3"):
    return BoqLine(
        concept_code=code, description=f"Concepto {code}", unit=unit,
        quantity=quantity, unit_price=0.0 if unpriced else amount / max(quantity, 1),
        amount=0.0 if unpriced else amount, phase="Estructura",
        raw_quantity=quantity, raw_kind=QuantityKind.VOLUME,
        source_detection_count=3, confidence=0.9, unpriced=unpriced,
    )


def _report(lines=None, warnings=(), units_reliable=True, grand_total=1000.0):
    boq = BillOfQuantities(
        project_id="p", lines=list(lines or []), warnings=list(warnings),
        units_reliable=units_reliable,
        direct_cost_total=sum(line.amount for line in (lines or [])),
    )
    return CostReport(
        project_id="p",
        currency="MXN",
        drawing_units=DrawingUnits(unit="m", source="declared", confidence=1.0),
        boq=boq, apus=[],
        integration=CostIntegration(
            direct_cost=boq.direct_cost_total, lines=[], sale_price=grand_total,
            contingency=0.0, grand_total=grand_total, overcost_factor=1.16,
        ),
        schedule=WorkSchedule(
            activities=[], total_duration_days=0, workdays_per_month=24, phases=[]
        ),
        financial=_plan(),
    )


def _plan():
    from klave_engine.costing.models import FinancialPlan

    return FinancialPlan(
        advance_payment_pct=30.0, retention_pct=5.0, advance_payment=0.0,
        total_retention=0.0, periods=[], operating_projection=[], annual_operating_cost=0.0,
    )


def test_unreliable_units_block_the_deliverable():
    d = diagnose(_report(units_reliable=False, warnings=["SIN UNIDADES: la unidad…"]))
    assert d.entregable is False
    top = d.hallazgos[0]
    assert top.severity == "bloqueante"
    assert "unidad confiable" in top.title
    assert "no tiene precios" in d.resumen
    # The prose warning is not repeated: the structural finding said it better.
    assert sum(1 for h in d.hallazgos if "UNIDADES" in h.title.upper()) == 0


def test_a_quantity_without_a_price_is_money_not_a_note():
    d = diagnose(_report([_line("CIM-010", quantity=23.0, unpriced=True, unit="PZA")]))
    finding = next(h for h in d.hallazgos if h.id == "sin_precio:CIM-010")
    assert finding.severity == "dinero"
    assert finding.exposicion == "23.00 PZA"
    # The money is unknowable from here, so it is never guessed.
    assert finding.monto_afectado is None
    assert finding.action.startswith("Dale precio")
    assert d.conceptos_sin_precio == 1
    assert "no los incluye" in d.resumen
    # A missing price does not make the presupuesto undeliverable, only short.
    assert d.entregable is True


def test_a_concept_that_contradicts_the_plano_blocks_and_carries_its_amount():
    line = _line("CIM-002", amount=27424.36)
    d = diagnose(
        _report(
            [line],
            warnings=["CIM-002: El plano declara f'c=300 para cimentacion; "
                      "el concepto costea f'c=250. Ajusta el concepto o su matriz."],
        )
    )
    finding = d.hallazgos[0]
    assert finding.severity == "bloqueante"
    assert finding.concept_code == "CIM-002"
    assert finding.monto_afectado == 27424.36
    assert finding.target == "parametros"
    assert d.entregable is False
    assert d.monto_en_duda == 27424.36
    assert "en duda" in d.resumen


def test_repeats_of_one_problem_collapse_into_one_finding():
    """Six copies of one decision are one finding carrying all the money —
    printing them six times is the flood that trains people to skip the list."""
    d = diagnose(
        _report(
            [_line("CIM-002", amount=500.0), _line("CIM-007", amount=9000.0)],
            warnings=[
                "CIM-002: El plano declara f'c=300; el concepto costea f'c=250. Ajústalo.",
                "CIM-007: El plano declara f'c=300; el concepto costea f'c=250. Ajústalo.",
            ],
        )
    )
    blocking = [h for h in d.hallazgos if h.severity == "bloqueante"]
    assert len(blocking) == 1
    assert blocking[0].title == "2 conceptos costean un f'c menor al que declara el plano"
    assert blocking[0].monto_afectado == 9500.0  # the family's money, added up
    assert "CIM-002" in blocking[0].detail and "CIM-007" in blocking[0].detail
    # The instruction lives in the action, never repeated inside the title.
    assert "Ajusta" not in blocking[0].title
    assert blocking[0].action.startswith("Ajusta")
    assert d.monto_en_duda == 9500.0


def test_severity_ranks_the_list_and_money_breaks_ties():
    d = diagnose(
        _report(
            [_line("CIM-010", unpriced=True), _line("CIM-002", amount=500.0),
             _line("EST-013", amount=9000.0)],
            warnings=[
                "Losa de vigueta: sin cimbra de contacto; el apuntalamiento va en la matriz.",
                "CIM-002: El plano declara f'c=300; el concepto costea f'c=250.",
                "Precios con vigencia vencida: 3 insumos.",
                "Terracerías: falta definir el nivel de plataforma.",
            ],
        )
    )
    tiers = ["bloqueante", "dinero", "revisar"]
    order = [h.severity for h in d.hallazgos]
    assert order == sorted(order, key=tiers.index)
    assert d.by_severity == {"bloqueante": 1, "dinero": 1, "revisar": 2}
    # The vigueta note asks nothing of the reader, so it is not an alarm at
    # all — it joins the criterios that defend the number later.
    assert any("cimbra de contacto" in c for c in d.criterios)


def test_an_unknown_warning_still_shows_up():
    d = diagnose(_report(warnings=["Algo que este build no conoce todavía"]))
    finding = next(h for h in d.hallazgos if "no conoce" in h.title)
    assert finding.severity == "revisar"  # not promoted, never dropped


def test_pending_verification_is_a_finding_with_the_route():
    d = diagnose(_report(), reviews=ProjectReviews())
    finding = next(h for h in d.hallazgos if h.id == "verificacion_pendiente")
    assert "3 de 3" in finding.title or "Faltan 3" in finding.title
    assert finding.severity == "revisar"


def test_coverage_gaps_point_at_the_worst_sheet():
    d = diagnose(
        _report(),
        cobertura=[
            {"kind": "faltante", "frame_code": "ES-200", "family": "dala",
             "ai_count": 14, "engine_count": 9},
            {"kind": "sobrante", "frame_code": "ES-100", "family": "castillo",
             "ai_count": 35, "engine_count": 60},
        ],
    )
    finding = next(h for h in d.hallazgos if h.id == "cobertura_faltante")
    assert "una hoja" in finding.title
    assert "ES-200" in finding.detail and "dala" in finding.detail
    assert finding.target == "revision"


def test_a_clean_presupuesto_says_so_without_inventing_problems():
    d = diagnose(_report([_line()], grand_total=1160.0), reviews=None)
    assert d.hallazgos == []
    assert d.entregable is True
    assert d.resumen == "$1,160 costeados."


def test_ids_are_stable_across_processes():
    warnings = ["Una advertencia cualquiera del motor"]
    first = diagnose(_report(warnings=warnings)).hallazgos[0].id
    second = diagnose(_report(warnings=warnings)).hallazgos[0].id
    assert first == second and first.startswith("motor:")


def test_a_choice_that_asks_nothing_is_a_criterio_not_an_alarm():
    """ISA-18.2's validity test: no required action means it is not an alarm.
    The content still survives — it moves to the assumptions register."""
    d = diagnose(
        _report(
            warnings=["Losa de vigueta 12-5: sin cimbra de contacto; el apuntalamiento "
                      "va en la matriz de la losa."],
        )
    )
    assert d.hallazgos == []
    assert any("cimbra de contacto" in c for c in d.criterios)


def test_findings_carry_the_last_responsible_moment_and_a_way_to_check_them():
    d = diagnose(
        _report(
            [_line("CIM-002", amount=500.0)],
            warnings=["CIM-002: El plano declara f'c=300; el concepto costea f'c=250."],
        )
    )
    finding = d.hallazgos[0]
    assert finding.momento == "cotizar"
    assert "notas de f'c" in finding.verificar


def test_corridas_sin_diametro_es_un_hallazgo_con_denominador():
    from klave_engine.costing.hallazgos import _classify
    texto = ("3 de 20 corridas de instalación sin diámetro legible: 481 m que "
             "ninguna publicación deja cotizar.")
    rule = _classify(texto)
    assert rule.severity == "dinero"
    assert rule.group == "corridas_sin_diametro"
    assert rule.momento == "cotizar"

    tiros = "2 tiros de bajada ligados sin niveles N.P.T. de dónde medir su tramo vertical."
    rule2 = _classify(tiros)
    assert rule2.severity == "revisar"
    assert rule2.group == "bajadas_sin_nivel"


def test_el_boq_emite_un_solo_aviso_por_causa():
    from klave_engine.costing.apu import build_all_apus
    from klave_engine.costing.boq import generate_bill_of_quantities
    from klave_engine.costing.instalaciones import conceptos_de_instalaciones
    from klave_engine.detection.results import DetectionType, make_detection
    from klave_engine.dxf.units import DrawingUnits

    from tests.precios import LIBRO

    def corrida(det_id, spec):
        return make_detection(
            det_id, DetectionType.pipe_run, "00-SANITARIA", (0, 0, 1, 1), 0.78, [],
            "layer_run", [],
            {"run_family": "sanitaria", "estimated_length": 10.0, "length_m": 10.0,
             "spec": spec},
        )

    dets = [corrida("r1", ""), corrida("r2", ""), corrida("r3", '4"')]
    catalog = [c for c in conceptos_de_instalaciones() if c.code == "SAN-002"]
    units = DrawingUnits(unit="m", source="declared", confidence=1.0)
    boq = generate_bill_of_quantities(
        "t", dets, units, catalog, build_all_apus(catalog, LIBRO)
    )
    avisos = [w for w in boq.warnings if "sin diámetro legible" in w]
    assert len(avisos) == 1
    assert "2 de 3" in avisos[0] and "20 m" in avisos[0]


def test_piezas_sin_clave_es_hallazgo_y_viaja_al_diagnostico():
    from klave_engine.costing.hallazgos import _classify, promote_detection_warnings

    texto = ("3 de 38 piezas de cancelería sin clave legible: el globo no "
             "declara qué pieza es. Siguen en el levantamiento.")
    rule = _classify(texto)
    assert rule.severity == "revisar"
    assert rule.group == "canceleria_sin_clave"

    # Solo viaja lo que el diagnóstico sabe clasificar; el ruido de
    # detección genérico se queda donde estaba.
    ruido = "126 líneas largas fuera de las capas de muros se ignoraron al buscar muros."
    assert promote_detection_warnings([texto, ruido]) == [texto]
