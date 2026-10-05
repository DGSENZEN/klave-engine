"""El mapeo: cada variante encuentra su concepto en el catálogo de la
oficina; ≥ 0.8 se aplica, la duda espera a una persona, y una decisión se
recuerda para el siguiente proyecto."""

import pytest
from klave_engine.costing.catalog_store import get_catalog_store
from klave_engine.costing.mapeo import consolidar_variantes, mapear, proponer
from klave_engine.costing.matching import Candidate
from klave_engine.costing.models import (
    BillOfQuantities,
    BoqLine,
    BoqVariant,
    QuantityKind,
    ResourceType,
    UnitPriceAnalysis,
)


def _line(code="EST-001", quantity=10.0, unit_price=1000.0, variants=None):
    return BoqLine(
        concept_code=code, description="Columnas de concreto armado f'c=250 kg/cm²",
        unit="M3", quantity=quantity, unit_price=unit_price, amount=quantity * unit_price,
        phase="Estructura", raw_quantity=quantity, raw_kind=QuantityKind.COUNT,
        source_detection_count=3, confidence=0.9, variants=variants or [],
    )


def _apu(code, price):
    return UnitPriceAnalysis(
        concept_code=code, concept_description=code, unit="M3", lines=[],
        breakdown={rt.value: 0.0 for rt in ResourceType}, direct_unit_cost=price,
    )


def test_proponer_bands():
    cands = [Candidate(kind="concept", key="EMC-3", clave="EMC-3",
                       description="Columna de concreto armado f'c=250 kg/cm2 sección 30x40 cm",
                       unit="M3", price=None)]
    status, match = proponer(
        "Columnas de concreto armado f'c=250 kg/cm², de sección 30×40 cm", "M3", "", cands
    )
    assert status in ("automatica", "propuesta") and match.candidate.clave == "EMC-3"
    assert proponer("Luminaria LED de 18 W", "M3", "", cands)[0] == "sin_equivalente"
    assert proponer("Columnas de concreto", "PZA", "", cands)[0] == "sin_equivalente"


def test_consolidar_prices_by_variant_and_line_is_their_sum():
    v1 = BoqVariant(key="EST-001.30X40", quantity=6.0)
    v2 = BoqVariant(key="EST-001.15X15", quantity=4.0)
    boq = BillOfQuantities(project_id="p", lines=[_line(variants=[v1, v2])])
    mappings = {
        "EST-001.30X40": {"status": "confirmada", "target_kind": "concept",
                          "target_code": "EMC-3", "clave": "EMC-3",
                          "description": "Columna 30x40", "reason": ""},
        "EST-001.15X15": {"status": "propuesta", "target_kind": "concept",
                          "target_code": "CAS-1", "clave": "CAS-1", "description": "",
                          "reason": ""},
    }
    consolidar_variantes(boq, mappings, {"EMC-3": _apu("EMC-3", 4000.0)})
    line = boq.lines[0]
    a, b = line.variants
    assert a.clave == "EMC-3" and a.unit_price == 4000.0 and a.amount == 24000.0
    # La propuesta se muestra pero no se aplica: queda el precio del motor.
    assert b.mapping == "propuesta" and b.clave == "CAS-1" and b.unit_price == 1000.0
    assert line.amount == 28000.0 and line.unit_price == pytest.approx(2800.0)
    assert boq.direct_cost_total == 28000.0


def test_consolidar_rebalances_after_an_adjustment_and_adds_gen():
    variants = [
        BoqVariant(key="EST-001.A", quantity=6.0), BoqVariant(key="EST-001.B", quantity=4.0),
    ]
    boq = BillOfQuantities(project_id="p", lines=[
        _line(quantity=12.0, variants=variants), _line(code="EST-008", quantity=5.0),
    ])
    consolidar_variantes(boq, {}, {})
    first, derived = boq.lines
    assert [v.quantity for v in first.variants] == [pytest.approx(7.2), pytest.approx(4.8)]
    assert derived.variants[0].key == "EST-008.GEN" and derived.variants[0].quantity == 5.0
    # Sin decisiones de la oficina, el importe queda como lo dejó el motor.
    assert first.amount == 12000.0


def test_mapear_remembers_and_respects_a_person(data_dir):
    store = get_catalog_store(data_dir)
    store.upsert_insumo("MAT-X", description="X", unit="M3", resource_type="material",
                        unit_cost=100.0)
    store.create_concept(
        code="EMC-3", description="Columna de concreto armado f'c=250 kg/cm2 sección 30x40 cm",
        unit="M3", phase="Estructura", production_rate_per_day=2.0, components=[("MAT-X", 1.0)],
    )
    variant = BoqVariant(
        key="EST-001.30X40",
        description="Columnas de concreto armado f'c=250 kg/cm², de sección 30×40 cm",
        quantity=10.0,
    )
    boq = BillOfQuantities(project_id="p", lines=[_line(variants=[variant])])
    first = mapear(boq, store, actor="motor")
    assert first["automatica"] + first["propuesta"] == 1
    memory = store.load_variant_mappings()["EST-001.30X40"]
    assert memory["target_code"] == "EMC-3"
    # Una persona dice «sin equivalente»; volver a mapear con rematch no la pisa.
    store.set_variant_mapping("EST-001.30X40", status="confirmada", target_kind="concept",
                              target_code="EMC-3", clave="EMC-3", actor="Diego")
    again = mapear(boq, store, rematch=True)
    assert again["conservadas"] == 1
    assert store.load_variant_mappings()["EST-001.30X40"]["actor"] == "Diego"
    with pytest.raises(ValueError):
        store.set_variant_mapping("EST-001.X", status="confirmada")
