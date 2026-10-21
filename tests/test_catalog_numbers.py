"""Non-finite numeric input must not poison the workshop's saved catalog."""

import pytest
from fastapi.testclient import TestClient
from klave_engine.costing.catalog_store import get_catalog_store


@pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf")])
@pytest.mark.parametrize(
    "operation",
    ["price", "apu", "basico", "rendimiento", "concept_rate", "new_concept_rate",
     "new_concept_quantity", "parametric", "parametric_update", "inventory"],
)
def test_non_finite_catalog_edits_are_rejected_before_writing(data_dir, operation, value):
    store = get_catalog_store(data_dir)
    store.upsert_insumo(
        "BASIC", description="Basic material", unit="M3", resource_type="material",
        unit_cost=10.0, kind="basico",
    )
    rule = store.add_parametric_rule(
        concept_code="EST-001", basis="area", factor=1.0,
    ) if operation == "parametric_update" else None
    before_prices = store.list_insumos()
    before_concepts = store.load_concepts()
    before_templates = store.load_templates()
    before_rules = store.list_parametric_rules()
    edits = {
        "price": lambda: store.upsert_insumo("MAT-BLOCK", unit_cost=value),
        "apu": lambda: store.set_apu_components("EST-001", [("MO-PEON", value)]),
        "basico": lambda: store.set_basico_components("BASIC", [("MO-PEON", value)]),
        "rendimiento": lambda: store.set_rendimiento("EST-001", value),
        "concept_rate": lambda: store.update_concept("EST-001", production_rate_per_day=value),
        "new_concept_rate": lambda: store.create_concept(
            code="NEW", description="New concept", unit="PZA", phase="estructura",
            production_rate_per_day=value, components=[("MO-PEON", 1.0)],
        ),
        "new_concept_quantity": lambda: store.create_concept(
            code="NEW", description="New concept", unit="PZA", phase="estructura",
            production_rate_per_day=1.0, components=[("MO-PEON", value)],
        ),
        "parametric": lambda: store.add_parametric_rule(
            concept_code="EST-001", basis="area", factor=value,
        ),
        "parametric_update": lambda: store.update_parametric_rule(rule["id"], factor=value),
        "inventory": lambda: store.add_inventory_mapping(
            kind="block", pattern="column", concept_code="EST-001", factor=value,
        ),
    }

    with pytest.raises(ValueError):
        edits[operation]()

    assert store.list_insumos() == before_prices
    assert store.load_concepts() == before_concepts
    assert store.load_templates() == before_templates
    assert store.list_parametric_rules() == before_rules
    assert store.list_inventory_mappings() == []


@pytest.mark.parametrize("invalid", ["NaN", "Infinity", "-Infinity", "1e999"])
def test_price_import_skips_non_finite_rows_and_keeps_valid_rows(data_dir, invalid):
    store = get_catalog_store(data_dir)
    result = store.import_prices([
        {"code": "MO-PEON", "unit_cost": "700"},
        {"code": "MAT-BLOCK", "unit_cost": invalid},
        {"code": "MAT-CIMBRA", "unit_cost": "200"},
    ], source="CSV quote")

    assert result == {"updated": 2, "skipped": ["MAT-BLOCK"]}
    prices = store.load_price_book()
    assert prices["MO-PEON"].unit_cost == 700.0
    assert prices["MAT-CIMBRA"].unit_cost == 200.0
    assert prices["MAT-BLOCK"].unit_cost == 0.0


@pytest.mark.parametrize(
    ("path", "body"),
    [
        ("/catalog/insumos/MAT-BLOCK", {"unit_cost": "Infinity"}),
        ("/catalog/apus/EST-001", {
            "components": [{"resource_code": "MO-PEON", "quantity": "Infinity"}],
        }),
        ("/catalog/rendimientos/EST-001", {"production_rate_per_day": "Infinity"}),
        ("/catalog/concepts/EST-001", {"production_rate_per_day": "Infinity"}),
    ],
)
def test_invalid_numeric_edits_return_422_and_leave_catalog_readable(data_dir, path, body):
    from apps.api.main import create_app

    client = TestClient(create_app(), raise_server_exceptions=False)
    before = client.get("/catalog").json()
    response = client.put(path, json=body)

    assert response.status_code == 422, response.text
    after = client.get("/catalog")
    assert after.status_code == 200
    assert after.json() == before


def test_saved_price_indices_exclude_non_finite_values(data_dir):
    store = get_catalog_store(data_dir)
    saved = store.save_indices("INPP", {
        "2026-01": 100.0, "2026-02": float("inf"), "2026-03": float("nan"),
    })
    assert saved["values"] == {"2026-01": 100.0}
    assert store.load_indices()["values"] == {"2026-01": 100.0}


@pytest.mark.parametrize("number", ["1e999", "NaN", "Infinity", "-Infinity"])
def test_non_finite_json_numbers_return_a_validation_error(data_dir, number):
    from apps.api.main import create_app

    client = TestClient(create_app(), raise_server_exceptions=False)
    response = client.put(
        "/catalog/insumos/MAT-BLOCK", content='{"unit_cost": ' + number + '}',
        headers={"Content-Type": "application/json"},
    )

    assert response.status_code == 422, response.text[:200]
    assert client.get("/catalog").status_code == 200


@pytest.mark.parametrize("params", [
    {"vm": 100000, "vr": 1000, "ve": "Infinity"},
    {"vm": 100000, "vr": 1000, "ve": 10000, "hea": "Infinity"},
])
def test_equipment_rejects_non_finite_inputs_even_when_final_cost_is_finite(data_dir, params):
    from apps.api.main import create_app

    client = TestClient(create_app(), raise_server_exceptions=False)
    response = client.put("/catalog/equipment/TEST-EQ", json={
        "description": "Test equipment", "params": params,
    })

    assert response.status_code == 422, response.text[:200]
    catalog = get_catalog_store(data_dir)
    assert catalog.get_analysis("TEST-EQ") is None
    assert "TEST-EQ" not in catalog.load_price_book()


@pytest.mark.parametrize("invalid_part", ["params", "second_category"])
def test_labor_rejects_non_finite_inputs_before_applying_any_prices(data_dir, invalid_part):
    from apps.api.main import create_app

    client = TestClient(create_app(), raise_server_exceptions=False)
    before = client.get("/catalog").json()
    body = {
        "params": {"isn_pct": "Infinity", "isn_in_fsr": False} if invalid_part == "params" else {},
        "categories": [
            {"code": "MO-PEON", "description": "Peon", "salario_nominal": 400},
            {"code": "MO-OFICIAL", "description": "Official", "salario_nominal": (
                "NaN" if invalid_part == "second_category" else 500
            )},
        ],
    }
    response = client.put("/catalog/labor", json=body)

    assert response.status_code == 422, response.text[:200]
    assert client.get("/catalog").json() == before
    assert get_catalog_store(data_dir).get_setting("labor_fsr") is None
