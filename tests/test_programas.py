"""Los programas de erogaciones: derived from the explosión put on the
programa's own calendar, so they cannot contradict either."""

from klave_engine.costing.apu import build_all_apus
from klave_engine.costing.catalog import build_default_catalog
from klave_engine.costing.models import CostingAssumptions
from klave_engine.costing.plantilla import CargoCampo
from klave_engine.costing.programas import RUBROS, build_programas
from klave_engine.costing.report import generate_cost_report
from klave_engine.detection.results import DetectionType, make_detection
from klave_engine.dxf.units import DrawingUnits


def _report():
    dets = [
        make_detection(
            f"z{i}", DetectionType.footing, f"Z-{i}", (0, 0, 1, 1), 0.9, [], "m", [],
            {"estimated_area": 4.0},
        )
        for i in range(6)
    ]
    return generate_cost_report(
        "p", dets, DrawingUnits(unit="m", source="declared", confidence=1.0),
    )


def test_the_four_programs_of_article_45_are_produced():
    programas = build_programas(_report())
    assert [p.rubro for p in programas.programas] == list(RUBROS)
    assert programas.periods >= 1
    assert programas.period_label == "mes"


def test_each_insumo_is_spread_over_the_days_its_concept_runs():
    """The calendar comes from the programa, so the sum across periods is
    exactly the explosión's total for that insumo — no leakage, no invention."""
    report = _report()
    programas = build_programas(report)
    mano = programas.get("mano_de_obra")
    assert mano is not None and mano.rows
    for row in mano.rows:
        assert abs(sum(row.by_period) - row.quantity) < 0.01
        assert abs(sum(row.amount_by_period) - row.amount) < 1.0
    assert abs(sum(mano.total_by_period) - mano.total) < 1.0


def test_labour_and_machinery_keep_their_own_units():
    programas = build_programas(_report())
    mano = programas.get("mano_de_obra")
    assert mano is not None
    assert any(r.unit.upper().startswith("JOR") for r in mano.rows)
    maquinaria = programas.get("maquinaria")
    assert maquinaria is not None
    if maquinaria.rows:
        assert any("horas efectivas" in n for n in maquinaria.notes)


def test_technical_staff_says_it_is_missing_instead_of_coming_out_blank():
    """Sin plantilla capturada el programa sigue vacío — no se deriva de la
    explosión porque no está ahí — pero deja de salir en silencio: una
    propuesta a la que le falta uno de los cinco programas se desecha."""
    programas = build_programas(_report())
    personal = programas.get("personal_tecnico")
    assert personal is not None
    assert personal.rows == []
    assert any("45-A-XI-d" in n for n in personal.notes)
    assert any("costo indirecto" in n for n in personal.notes)


def test_technical_staff_comes_from_the_captured_plantilla():
    """Cuando hay plantilla, el programa se llena sobre el mismo calendario que
    los otros tres."""
    report = _report()
    report.plantilla_campo = [
        CargoCampo(puesto="Superintendente", salario_mensual=45000.0),
        CargoCampo(puesto="Velador", tipo="servicio", salario_mensual=9000.0),
    ]
    personal = build_programas(report).get("personal_tecnico")
    assert personal is not None
    assert [r.description.split(" — ")[0] for r in personal.rows] == [
        "Superintendente", "Velador",
    ]
    assert personal.total > 0
    # Técnico antes que servicio: el orden del formato, no el del importe.
    assert personal.rows[0].code == "Técnico"
    assert personal.rows[1].code == "Servicio"
    for row in personal.rows:
        assert abs(sum(row.amount_by_period) - row.amount) < 1.0


def test_the_period_is_a_parameter_because_the_convocante_sets_it():
    """Real convocatorias ask monthly, fortnightly and weekly — the law says
    "conforme a los periodos determinados por la convocante"."""
    report = _report()
    monthly = build_programas(report, workdays_per_period=24)
    weekly = build_programas(report, workdays_per_period=6)
    assert weekly.periods >= monthly.periods
    assert weekly.period_label == "semana"
    assert build_programas(report, workdays_per_period=12).period_label == "quincena"
    # Whatever the period, the totals are the same money.
    a = monthly.get("materiales")
    b = weekly.get("materiales")
    assert a is not None and b is not None
    assert abs(a.total - b.total) < 1.0


def test_herramienta_menor_has_no_calendar_of_its_own():
    """It is a percentage of the labour in each matrix, not a resource with a
    delivery date; putting it on a supply program would be nonsense."""
    programas = build_programas(_report())
    codes = {r.code for p in programas.programas for r in p.rows}
    assert "EQ-HERRAMIENTA" not in codes


def test_an_obra_without_a_schedule_does_not_pretend_to_have_one():
    assumptions = CostingAssumptions()
    catalog = build_default_catalog(assumptions)
    build_all_apus(catalog)
    empty = generate_cost_report(
        "p", [], DrawingUnits(unit="m", source="declared", confidence=1.0)
    )
    programas = build_programas(empty)
    assert programas.periods == 0
    assert all(p.rows == [] or all(r.by_period == [] for r in p.rows) for p in programas.programas)


def test_a_post_with_no_captured_salary_never_exports_as_zero():
    """Cero en la columna del importe se lee como «sale gratis». Un puesto sin
    sueldo capturado tiene cantidad y no tiene importe, y eso es lo que dice."""
    report = _report()
    report.plantilla_campo = [CargoCampo(puesto="Velador", tipo="servicio")]
    personal = build_programas(report).get("personal_tecnico")
    assert personal is not None
    velador = personal.rows[0]
    assert velador.quantity > 0  # su participación sí se cuenta
    assert velador.sin_importe is True
