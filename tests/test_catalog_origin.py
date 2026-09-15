"""Cada concepto e insumo dice de qué capa viene — oficial, importada,
generada o taller — y una persona que toca una fila ajena la vuelve suya."""

import sqlite3

import pytest
from klave_engine.costing.catalog_store import (
    ORIGINS,
    SEED_ORIGIN_REF,
    CatalogStore,
    get_catalog_store,
)
from klave_engine.costing.sources.matrices import parse_matrices_table

TABLE = [
    ["Clave", "Descripción", "Unidad", "Cantidad", "Costo", "Rendimiento", "Partida"],
    ["ALB-010", "Muro de block 15 cm", "M2", "", "", 12.5, "ALBAÑILERÍA"],
    ["MAT-BLOCK15", "Block 15x20x40", "PZA", 12.5, 14.2, "", ""],
    ["MO-OF-ALB2", "Oficial albañil", "JOR", 0.16, 690.0, "", ""],
]


@pytest.fixture
def store(data_dir) -> CatalogStore:
    return get_catalog_store(data_dir)


def test_seeded_rows_are_generada_semilla(store):
    concepts = {c["code"]: c for c in store.load_concepts(include_inactive=True)}
    assert concepts["EST-001"]["origin"] == "generada"
    assert concepts["EST-001"]["origin_ref"] == SEED_ORIGIN_REF
    assert all(c["origin"] in ORIGINS for c in concepts.values())
    insumos = {i["code"]: i for i in store.list_insumos()}
    assert all(i["origin"] in ORIGINS for i in insumos.values())
    assert any(i["origin"] == "generada" for i in insumos.values())
    assert concepts["EST-001"]["validation"] is None
    assert concepts["EST-001"]["spec_signature"] is None


def test_manual_rows_are_taller_and_import_marks_importada(store):
    store.upsert_insumo(
        "MAT-X", description="Un material cotizado a mano", unit="PZA",
        resource_type="material", unit_cost=10.0, source="Ferretería local",
        source_type="cotizacion",
    )
    assert next(i for i in store.list_insumos() if i["code"] == "MAT-X")["origin"] == "taller"
    store.create_concept(
        code="MAN-001", description="Concepto manual", unit="PZA", phase="Acabados",
        production_rate_per_day=5.0, components=[("MAT-X", 2.0)],
    )
    rows = {c["code"]: c for c in store.load_concepts()}
    assert rows["MAN-001"]["origin"] == "taller"

    result = store.import_matrices(parse_matrices_table(TABLE), "OPUS agosto")
    assert result["concepts_created"] == 1
    rows = {c["code"]: c for c in store.load_concepts()}
    assert rows["ALB-010"]["origin"] == "importada"
    assert rows["ALB-010"]["origin_ref"] == "OPUS agosto · ALB-010"
    block = next(i for i in store.list_insumos() if i["code"] == "MAT-BLOCK15")
    assert block["origin"] == "importada" and block["origin_ref"].startswith("OPUS agosto")


def test_touching_an_imported_row_promotes_it_to_taller(store):
    store.import_matrices(parse_matrices_table(TABLE), "OPUS agosto")
    row = store.update_concept("ALB-010", description="Muro de block 15 cm, junta 1 cm",
                               actor="Diego")
    assert row["origin"] == "taller" and row["touched_by"] == "Diego"
    assert row["touched_at"]
    # Sin actor (una máquina), no se promueve.
    store.update_concept("ALB-010", origin="importada", origin_ref="OPUS agosto · ALB-010")
    row = store.update_concept("ALB-010", phase="Albañilería")
    assert row["origin"] == "importada"
    # La matriz también cuenta como toque.
    store.set_apu_components("ALB-010", [("MAT-BLOCK15", 13.0)], actor="Diego")
    assert {c["code"]: c for c in store.load_concepts()}["ALB-010"]["origin"] == "taller"
    # Un insumo editado por una persona también pasa al taller.
    store.upsert_insumo("MAT-BLOCK15", unit_cost=15.0, actor="Diego")
    block = next(i for i in store.list_insumos() if i["code"] == "MAT-BLOCK15")
    assert block["origin"] == "taller" and "Diego" in block["origin_ref"]


def test_adopting_a_publication_marks_the_insumo_oficial(store):
    count = store.import_reference(
        {"key": "cdmx-test", "name": "Tabulador CDMX prueba", "publisher": "SOBSE",
         "region": "MX-CMX", "vigencia": "2026-06", "kind": "precios_unitarios", "url": ""},
        [{"clave": "AB12BB", "description": "Cemento gris", "unit": "TON", "price": 4100.0,
          "group_clave": "AB12B", "group_description": "Cementos"}],
    )
    assert count == 1
    ref = store.search_reference("cemento")[0]
    store.upsert_insumo(
        "MAT-CEM", description="Cemento", unit="TON", resource_type="material",
        unit_cost=1.0, source="", source_type="cotizacion",
    )
    row = store.adopt_reference("MAT-CEM", ref["ref_id"])
    assert row["origin"] == "oficial" and row["origin_ref"] == "cdmx-test · AB12BB"


def test_invalid_origin_is_refused(store):
    with pytest.raises(ValueError, match="Origen inválido"):
        store.upsert_insumo(
            "MAT-Y", description="x", unit="PZA", resource_type="material",
            unit_cost=1.0, origin="misterio",
        )


def test_old_database_is_backfilled(data_dir):
    """Una base de la versión anterior: sin columnas de origen. Al abrirla se
    clasifica lo que había según lo que se sabe de cada fila."""
    store = get_catalog_store(data_dir)
    store.upsert_insumo(
        "MAT-PUB", description="De publicación", unit="PZA", resource_type="material",
        unit_cost=1.0, source="Tabulador X · Z1", source_type="publicacion",
    )
    store.create_concept(
        code="IMPORT-Z1", description="Importado", unit="PZA", phase="Acabados",
        production_rate_per_day=1.0, components=[("MAT-PUB", 1.0)], import_source="OPUS julio",
    )
    store.create_concept(
        code="MANUAL-Z2", description="Manual", unit="PZA", phase="Acabados",
        production_rate_per_day=1.0, components=[("MAT-PUB", 1.0)],
    )
    # Borra la clasificación y baja la versión, como una base vieja.
    conn = sqlite3.connect(store.db_path)
    conn.execute("UPDATE concepts SET origin = '', origin_ref = ''")
    conn.execute("UPDATE insumos SET origin = '', origin_ref = ''")
    conn.execute("UPDATE meta SET value = '24' WHERE key = 'schema_version'")
    conn.commit()
    conn.close()
    import klave_engine.costing.catalog_store as module

    module._STORES.clear()
    reopened = get_catalog_store(data_dir)
    concepts = {c["code"]: c for c in reopened.load_concepts(include_inactive=True)}
    assert concepts["IMPORT-Z1"]["origin"] == "importada"
    assert concepts["IMPORT-Z1"]["origin_ref"] == "OPUS julio"
    assert concepts["MANUAL-Z2"]["origin"] == "taller"
    assert concepts["EST-001"]["origin"] == "generada"
    insumos = {i["code"]: i for i in reopened.list_insumos()}
    assert insumos["MAT-PUB"]["origin"] == "oficial"
    assert insumos["MAT-PUB"]["origin_ref"] == "Tabulador X · Z1"
