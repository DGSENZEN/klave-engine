"""Acero, cimbra y plantilla are priced once: as their own lines, never
inside a concrete matrix that also gets them derived."""

import sqlite3

from klave_engine.costing.catalog_store import (
    CONCRETE_MATRICES_V12,
    DOUBLE_COUNTED_RESOURCES,
    CatalogStore,
)
from klave_engine.costing.formwork import CODE_PLANTILLA
from klave_engine.costing.insumos import APU_TEMPLATES
from klave_engine.costing.models import CostingConfig
from klave_engine.costing.report import generate_cost_report
from klave_engine.detection.results import DetectionType, make_detection
from klave_engine.detection.taxonomy import classify_family
from klave_engine.dxf.units import DrawingUnits

# Concrete concepts whose acero/cimbra/plantilla the engine derives on its own.
DERIVED_FOR = ("CIM-002", "EST-001", "EST-002", "EST-005", "CIM-008")


def test_concrete_matrices_carry_no_steel_cimbra_or_plantilla():
    for code in DERIVED_FOR:
        resources = {resource for resource, _ in APU_TEMPLATES[code]}
        assert not resources & set(DOUBLE_COUNTED_RESOURCES), code
    # The reticular slab keeps only its rib steel; malla and cimbra are derived.
    assert "MAT-CIMBRA" not in {r for r, _ in APU_TEMPLATES["EST-003"]}


def _footing(det_id, x):
    det = make_detection(
        det_id, DetectionType.footing, det_id, (x, 0, x + 1.5, 1.5), 0.9, [], "m", [],
        {"estimated_area": 2.25},
    )
    det.family = classify_family(det).value
    return det


def test_plantilla_is_its_own_line_from_the_footing_plan_area():
    units = DrawingUnits(unit="m", source="declared", confidence=1.0)
    report = generate_cost_report(
        "p", [_footing("z1", 0.0), _footing("z2", 5.0)], units, CostingConfig(), None, None,
    )
    lines = {ln.concept_code: ln for ln in report.boq.lines}
    assert "CIM-002" in lines
    plantilla = lines[CODE_PLANTILLA]
    # (1.5 + 0.2)² per footing, two footings
    assert abs(plantilla.quantity - 2 * 1.7 * 1.7) < 0.01
    assert plantilla.amount > 0
    concrete_apu = next(a for a in report.apus if a.concept_code == "CIM-002")
    assert not {ln.resource_code for ln in concrete_apu.lines} & set(DOUBLE_COUNTED_RESOURCES)


def test_v13_migration_replaces_seed_matrices_but_keeps_edited_ones(tmp_path):
    db = tmp_path / "catalog.db"
    CatalogStore(db)  # seeds v13 directly
    with sqlite3.connect(db) as conn:
        # Pretend the taller still has the v12 seed in EST-001 and an edited CIM-002.
        conn.execute("DELETE FROM apu_components WHERE concept_code IN ('EST-001', 'CIM-002')")
        conn.executemany(
            "INSERT INTO apu_components (concept_code, resource_code, quantity) VALUES (?, ?, ?)",
            [("EST-001", r, q) for r, q in CONCRETE_MATRICES_V12["EST-001"]]
            + [("CIM-002", "MAT-CONC250", 1.10), ("CIM-002", "MAT-ACERO", 0.05),
               ("CIM-002", "MO-CUAD-ALB", 0.40)],
        )
        conn.execute("UPDATE meta SET value = '12' WHERE key = 'schema_version'")
    CatalogStore(db)  # opening migrates to v13
    with sqlite3.connect(db) as conn:
        est = {r for (r,) in conn.execute(
            "SELECT resource_code FROM apu_components WHERE concept_code = 'EST-001'"
        )}
        cim = {r for (r,) in conn.execute(
            "SELECT resource_code FROM apu_components WHERE concept_code = 'CIM-002'"
        )}
        version = conn.execute("SELECT value FROM meta WHERE key = 'schema_version'").fetchone()
    assert not est & set(DOUBLE_COUNTED_RESOURCES)          # seed replaced
    assert "MAT-ACERO" in cim and "MAT-CONC250" in cim      # edited matrix untouched
    assert version[0] == "13"
