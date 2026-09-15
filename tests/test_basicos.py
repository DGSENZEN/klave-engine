"""Un básico o una cuadrilla es un insumo con matriz propia: su precio sale
de sus componentes, sube por la cadena y se despliega en el análisis; un
ciclo se rechaza con los dos nombres; «dónde se usa» dice cuánto pesa."""

import pytest
from klave_engine.common.errors import ReportGenerationError
from klave_engine.costing.apu import build_apu
from klave_engine.costing.catalog import build_catalog_from_store
from klave_engine.costing.catalog_store import CatalogStore, get_catalog_store
from klave_engine.costing.models import CostingAssumptions


@pytest.fixture
def store(data_dir) -> CatalogStore:
    s = get_catalog_store(data_dir)
    s.upsert_insumo("MO-SOLD", description="Oficial soldador", unit="JOR",
                    resource_type="mano_de_obra", unit_cost=1748.2)
    s.upsert_insumo("MO-AYU", description="Ayudante especializado", unit="JOR",
                    resource_type="mano_de_obra", unit_cost=1113.01)
    s.upsert_insumo("CUAD-1S2E", description="Cuadrilla 1 soldador + 2 ayudantes", unit="JOR",
                    resource_type="mano_de_obra", unit_cost=1.0, kind="cuadrilla")
    s.set_basico_components("CUAD-1S2E", [("MO-SOLD", 1.0), ("MO-AYU", 2.0)])
    s.upsert_insumo("MAT-PLACA", description="Placa A-36", unit="TON",
                    resource_type="material", unit_cost=35200.0)
    s.create_concept(
        code="EMC-TEST", description="Columna de acero", unit="TON", phase="Estructura",
        production_rate_per_day=0.3,
        components=[("MAT-PLACA", 1.034), ("CUAD-1S2E", 2.5), ("EQ-HERRAMIENTA", 1.0)],
    )
    return s


def test_cuadrilla_prices_from_its_members(store):
    cuad = next(i for i in store.list_insumos() if i["code"] == "CUAD-1S2E")
    assert cuad["kind"] == "cuadrilla"
    assert cuad["unit_cost"] == pytest.approx(1748.2 + 2 * 1113.01)
    assert cuad["source_type"] == "calculado"
    assert cuad["origin_ref"] == "derivado de su matriz"


def test_concept_prices_through_the_cuadrilla_and_shows_its_matrix(store):
    concepts = build_catalog_from_store(store.load_concepts(), CostingAssumptions())
    concept = next(c for c in concepts if c.code == "EMC-TEST")
    apu = build_apu(concept, resources=store.load_price_book(), templates=store.load_templates())
    cuadrilla_line = next(line for line in apu.lines if line.resource_code == "CUAD-1S2E")
    assert cuadrilla_line.kind == "cuadrilla"
    assert cuadrilla_line.sub_analysis is not None
    assert sorted(line.resource_code for line in cuadrilla_line.sub_analysis.lines) == [
        "MO-AYU", "MO-SOLD",
    ]
    jornada = 1748.2 + 2 * 1113.01
    assert cuadrilla_line.unit_cost == pytest.approx(jornada)
    # La herramienta es 3 % de la mano de obra, y la cuadrilla es mano de obra.
    assert apu.direct_unit_cost == pytest.approx(1.034 * 35200 + 2.5 * jornada * 1.03, abs=0.05)


def test_raising_a_member_reprices_cuadrilla_and_concept(store):
    store.upsert_insumo("MO-AYU", unit_cost=1200.0)
    cuad = next(i for i in store.list_insumos() if i["code"] == "CUAD-1S2E")
    assert cuad["unit_cost"] == pytest.approx(1748.2 + 2 * 1200.0)


def test_cycles_and_depth_are_refused(store):
    store.upsert_insumo("BAS-A", description="Básico A", unit="M3", resource_type="material",
                        unit_cost=1.0, kind="basico")
    store.upsert_insumo("BAS-B", description="Básico B", unit="M3", resource_type="material",
                        unit_cost=1.0, kind="basico")
    store.set_basico_components("BAS-A", [("BAS-B", 1.0)])
    with pytest.raises(ValueError, match="Ciclo entre básicos: BAS-B → BAS-A → BAS-B"):
        store.set_basico_components("BAS-B", [("BAS-A", 1.0)])
    with pytest.raises(ValueError, match="no es un básico"):
        store.set_basico_components("MAT-PLACA", [("MO-AYU", 1.0)])
    # El constructor del análisis también se protege si la base trae un ciclo.
    templates = store.load_templates()
    templates["BAS-B"] = [("BAS-A", 1.0)]
    book = store.load_price_book()
    from klave_engine.costing.models import Concept

    with pytest.raises(ReportGenerationError, match="Ciclo entre básicos"):
        build_apu(
            Concept(code="BAS-A", description="A", unit="M3", phase="x",
                    production_rate_per_day=1.0),
            resources=book, templates=templates,
        )


def test_basico_without_a_priced_member_keeps_its_price_and_says_so(store):
    store.upsert_insumo("MAT-SIN", description="Sin precio todavía", unit="KG",
                        resource_type="material", unit_cost=1.0)
    store.upsert_insumo("BAS-M", description="Mortero", unit="M3", resource_type="material",
                        unit_cost=900.0, kind="basico")
    store.set_basico_components("BAS-M", [("MAT-SIN", 10.0)])
    import sqlite3

    conn = sqlite3.connect(store.db_path)
    conn.execute("UPDATE insumos SET unit_cost = 0 WHERE code = 'MAT-SIN'")
    conn.commit()
    conn.close()
    result = store.recompute_basicos()
    assert any("BAS-M: MAT-SIN sin precio" in p for p in result["problems"])
    assert next(i for i in store.list_insumos() if i["code"] == "BAS-M")["unit_cost"] == 10.0


def test_insumo_uses_reports_concepts_and_basicos(store):
    uses = store.insumo_uses("MO-AYU")
    assert uses["basicos"] == [
        {"code": "CUAD-1S2E", "description": "Cuadrilla 1 soldador + 2 ayudantes",
         "quantity": 2.0, "amount": pytest.approx(2226.02)},
    ]
    uses = store.insumo_uses("CUAD-1S2E")
    assert uses["concepts"][0]["code"] == "EMC-TEST"
    assert uses["concepts"][0]["quantity"] == 2.5
    assert 0 < uses["concepts"][0]["share"] < 1
