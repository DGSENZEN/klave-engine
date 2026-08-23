"""Imported matrices land in the store as priced concepts and cotización
insumos; an existing concept keeps its rule and takes the new matrix."""

import pytest
from klave_engine.costing.catalog_store import get_catalog_store
from klave_engine.costing.sources.matrices import parse_matrices_table

TABLE = [
    ["Clave", "Descripción", "Unidad", "Cantidad", "Costo", "Rendimiento", "Partida"],
    ["ALB-010", "Muro de block 15 cm", "M2", "", "", 12.5, "ALBAÑILERÍA"],
    ["MAT-BLOCK15", "Block 15x20x40", "PZA", 12.5, 14.2, "", ""],
    ["MO-OF-ALB2", "Oficial albañil", "JOR", 0.16, 690.0, "", ""],
    ["HERR", "Herramienta menor", "%", 3.0, "", "", ""],
    ["EST-004", "Muros de block (matriz del taller)", "M2", "", "", 14.0, "ESTRUCTURA"],
    ["MAT-BLOCK15", "Block 15x20x40", "PZA", 12.5, 14.2, "", ""],
    ["MO-OF-ALB2", "Oficial albañil", "JOR", 0.14, 690.0, "", ""],
]


@pytest.fixture
def store(data_dir):
    return get_catalog_store(data_dir)


def test_import_matrices_creates_and_updates_concepts(store):
    result = store.import_matrices(parse_matrices_table(TABLE), "OPUS agosto")
    assert result["concepts_created"] == 1 and result["concepts_updated"] == 1
    assert result["insumos_upserted"] == 2  # the % row maps to EQ-HERRAMIENTA, not a new insumo
    book = store.load_price_book()
    assert book["MAT-BLOCK15"].unit_cost == 14.2
    assert book["MO-OF-ALB2"].resource_type.value == "mano_de_obra"
    rows = {r["code"]: r for r in store.load_concepts(include_inactive=True)}
    new = rows["ALB-010"]
    assert new["rule_key"] is None and new["phase"] == "ALBAÑILERÍA"
    assert new["production_rate_per_day"] == 12.5
    existing = rows["EST-004"]
    assert existing["rule_key"] == "EST-004"  # still reads walls from the plan
    assert existing["description"] == "Muros de block (matriz del taller)"
    templates = store.load_templates()
    assert sorted(templates["ALB-010"]) == [
        ("EQ-HERRAMIENTA", 0.03), ("MAT-BLOCK15", 12.5), ("MO-OF-ALB2", 0.16),
    ]
    assert sorted(templates["EST-004"]) == [("MAT-BLOCK15", 12.5), ("MO-OF-ALB2", 0.14)]
    insumo = next(i for i in store.list_insumos() if i["code"] == "MAT-BLOCK15")
    assert insumo["source_type"] == "cotizacion" and insumo["source"] == "OPUS agosto"
