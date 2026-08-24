"""Cantidades que se siguen de otras: aritmética sobre lo medido, con la
evidencia de dónde salió y sin cruzar unidades."""

from klave_engine.costing.derivadas import Derivada, aplicar_derivadas
from klave_engine.costing.models import Concept, UnitPriceAnalysis

from tests.test_hallazgos import _line, _report


def _concepto(code: str, unit: str = "M2", desc: str = "") -> Concept:
    return Concept(
        code=code, description=desc or f"Concepto {code}", unit=unit,
        phase="Acabados", production_rate_per_day=20.0,
    )


def _apu(code: str, precio: float) -> UnitPriceAnalysis:
    return UnitPriceAnalysis(
        concept_code=code, concept_description=code, unit="M2", lines=[],
        breakdown={}, direct_unit_cost=precio,
    )


_PINTURA = (Derivada(destino="ACA-002", origenes=("ACA-001",), factor=1.0, razon="uno a uno"),)


def test_la_cantidad_derivada_entra_con_su_evidencia():
    boq = _report([_line("ACA-001", quantity=420.0, amount=50000.0, unit="M2")]).boq
    catalog = [_concepto("ACA-001"), _concepto("ACA-002", desc="Pintura vinílica")]
    derivadas = aplicar_derivadas(boq, catalog, {"ACA-002": _apu("ACA-002", 95.0)}, _PINTURA)

    assert derivadas == 1
    linea = next(x for x in boq.lines if x.concept_code == "ACA-002")
    assert linea.quantity == 420.0
    assert linea.amount == round(420.0 * 95.0, 2)
    assert linea.source_detection_count == 0  # no se leyó del plano, y lo dice
    evidencia = " ".join(linea.assumptions)
    assert "derivada de ACA-001" in evidencia
    assert "420.00 M2 × 1" in evidencia
    assert "No se leyó del plano" in evidencia


def test_una_cantidad_leida_del_plano_nunca_se_pisa():
    """La lectura manda sobre la deducción: si el muro se midió, no se deduce
    encima de él."""
    boq = _report(
        [
            _line("ACA-001", quantity=420.0, unit="M2"),
            _line("ACA-002", quantity=999.0, unit="M2"),
        ]
    ).boq
    catalog = [_concepto("ACA-001"), _concepto("ACA-002")]
    assert aplicar_derivadas(boq, catalog, {}, _PINTURA) == 0
    assert next(x for x in boq.lines if x.concept_code == "ACA-002").quantity == 999.0


def test_sin_cantidad_de_origen_no_se_deriva_nada():
    """Inventar la base y multiplicarla sería inventar dinero con más pasos."""
    boq = _report([]).boq
    catalog = [_concepto("ACA-001"), _concepto("ACA-002")]
    assert aplicar_derivadas(boq, catalog, {}, _PINTURA) == 0
    assert boq.lines == []


def test_no_se_deriva_cruzando_unidades():
    """Un factor multiplica, no convierte: derivar m² a partir de m³ daría una
    cifra con la forma correcta y el valor equivocado."""
    boq = _report([_line("CIM-002", quantity=7.5, unit="M3")]).boq
    catalog = [_concepto("CIM-002", unit="M3"), _concepto("CIM-003", unit="M2")]
    reglas = (
        Derivada(destino="CIM-003", origenes=("CIM-002",), factor=1.0, razon="prueba"),
    )
    assert aplicar_derivadas(boq, catalog, {}, reglas) == 0
    assert any("otra unidad" in w for w in boq.warnings)


def test_sin_matriz_la_derivada_queda_visible_pero_sin_precio():
    """Una cantidad real sin precio es «sin precio», nunca cero disfrazado."""
    boq = _report([_line("ACA-001", quantity=100.0, unit="M2")]).boq
    catalog = [_concepto("ACA-001"), _concepto("ACA-002")]
    aplicar_derivadas(boq, catalog, {}, _PINTURA)
    linea = next(x for x in boq.lines if x.concept_code == "ACA-002")
    assert linea.quantity == 100.0
    assert linea.unpriced is True and linea.amount == 0.0


def test_el_factor_se_aplica_y_se_declara():
    boq = _report([_line("ACA-001", quantity=200.0, unit="M2")]).boq
    catalog = [_concepto("ACA-001"), _concepto("ACA-002")]
    reglas = (
        Derivada(
            destino="ACA-002", origenes=("ACA-001",), factor=2.0,
            razon="dos manos de pintura",
        ),
    )
    aplicar_derivadas(boq, catalog, {}, reglas)
    linea = next(x for x in boq.lines if x.concept_code == "ACA-002")
    assert linea.quantity == 400.0
    assert "dos manos de pintura" in " ".join(linea.assumptions)


def test_un_destino_que_no_existe_en_el_catalogo_se_ignora():
    boq = _report([_line("ACA-001", quantity=100.0, unit="M2")]).boq
    assert aplicar_derivadas(boq, [_concepto("ACA-001")], {}, _PINTURA) == 0


def test_la_confianza_hereda_la_del_origen():
    """Derivar no degrada la confianza: la aritmética no se equivoca. Pero
    tampoco la mejora."""
    origen = _line("ACA-001", quantity=100.0, unit="M2")
    origen.confidence = 0.62
    boq = _report([origen]).boq
    catalog = [_concepto("ACA-001"), _concepto("ACA-002")]
    aplicar_derivadas(boq, catalog, {}, _PINTURA)
    assert next(x for x in boq.lines if x.concept_code == "ACA-002").confidence == 0.62
