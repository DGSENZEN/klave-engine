"""La base se hojea sin tocar el taller; «Traer al taller» copia un renglón
publicado como concepto con su precio de tabulador, o uno importado con su
matriz y sus insumos — y cada uno dice de dónde vino."""

import pytest
from klave_engine.costing.catalog_store import CatalogStore, get_catalog_store
from klave_engine.costing.sources.matrices import parse_matrices_table

PUBLICACION = {
    "key": "cdmx-prueba", "name": "Tabulador CDMX prueba", "publisher": "SOBSE",
    "region": "MX-CMX", "vigencia": "2026-06", "kind": "precios_unitarios", "url": "",
}
RENGLONES = [
    {"clave": "IB12BB", "description": "Tubería de cobre tipo M de 13 mm", "unit": "M",
     "price": 180.5, "group_clave": "IB12B", "group_description": "Tubos de cobre"},
    {"clave": "EA01AA", "description": "Concreto f'c=250 kg/cm2 en columnas", "unit": "M3",
     "price": 3900.0, "group_clave": "EA01A", "group_description": "Concreto en estructura"},
    {"clave": "ZZ00ZZ", "description": "Renglón por cotización", "unit": "PZA", "price": 0.0,
     "group_clave": "", "group_description": ""},
]
OPUS = [
    ["Clave", "Descripción", "Unidad", "Cantidad", "Costo", "Rendimiento", "Partida"],
    ["EMC3", "Estructura para columnas con placa A-36", "TON", "", "", 0.28, "ESTRUCTURA METALICA"],
    ["313-APL-0104", "Placa A-36 3/8", "TON", 1.034, 35200.0, "", ""],
    ["1S2E", "Cuadrilla 1 soldador + 2 ayudantes", "JOR", 2.5, 4130.89, "", ""],
    ["%MO1", "Herramienta menor", "%", 3.0, "", "", ""],
]


@pytest.fixture
def store(data_dir) -> CatalogStore:
    s = get_catalog_store(data_dir)
    s.import_reference(PUBLICACION, RENGLONES)
    s.import_matrices_as_source(
        parse_matrices_table(OPUS), source_key="prisma-acero-2026",
        name="PRISMA acero 2026", publisher="Ingeniería Integral", region="MX",
        vigencia="2026-05",
    )
    return s


def test_matrices_base_is_browsable_with_its_components(store):
    sources = {s["source_key"]: s for s in store.list_sources()}
    assert sources["prisma-acero-2026"]["kind"] == "matrices"
    assert sources["prisma-acero-2026"]["row_count"] == 1
    page = store.browse_reference("columnas")
    assert page["total"] == 2
    emc3 = next(r for r in page["rows"] if r["clave"] == "EMC3")
    # 1.034 × 35,200 + 2.5 × 4,130.89 + 3 % de la mano de obra.
    assert emc3["price"] == pytest.approx(1.034 * 35200 + 2.5 * 4130.89 * 1.03, abs=0.01)
    assert emc3["extra"]["rendimiento"] == 0.28 and emc3["source_kind"] == "matrices"
    assert emc3["in_taller"] is False
    components = store.reference_components(emc3["ref_id"])
    assert [c["resource_clave"] for c in components] == ["%MO1", "1S2E", "313-APL-0104"]
    # El taller sigue intacto: ningún concepto EMC3 todavía.
    assert "EMC3" not in {c["code"] for c in store.load_concepts()}


def test_browse_filters_by_source_partida_region_and_pages(store):
    assert store.browse_reference(source_keys=["cdmx-prueba"])["total"] == 2  # el $0 no entra
    assert store.browse_reference(region="MX-CMX")["total"] == 2
    assert store.browse_reference(kind="matrices")["total"] == 1
    estructura = store.browse_reference(partida="estructura")
    assert {r["clave"] for r in estructura["rows"]} >= {"EA01AA"}
    first = store.browse_reference(limit=1, offset=0)
    second = store.browse_reference(limit=1, offset=1)
    assert first["total"] == 3 and first["rows"][0]["clave"] != second["rows"][0]["clave"]


def test_bring_a_published_row_as_a_priced_concept(store):
    ref = next(r for r in store.browse_reference("cobre")["rows"])
    row = store.adopt_reference_as_concept(ref["ref_id"])
    assert row["code"] == "IB12BB" and row["origin"] == "oficial"
    assert row["origin_ref"] == "cdmx-prueba · IB12BB"
    assert row["price_override"] == 180.5 and row["price_clave"] == "IB12BB"
    assert row["phase"] == "Instalación hidráulica"
    assert store.browse_reference("cobre")["rows"][0]["in_taller"] is True
    with pytest.raises(ValueError, match="ya existe en el taller"):
        store.adopt_reference_as_concept(ref["ref_id"])


def test_bring_an_imported_row_with_its_matrix_and_insumos(store):
    ref = next(r for r in store.browse_reference("placa")["rows"])
    row = store.adopt_reference_as_concept(ref["ref_id"], phase="Estructura")
    assert row["code"] == "EMC3" and row["origin"] == "importada"
    assert row["origin_ref"] == "prisma-acero-2026 · EMC3"
    assert row["production_rate_per_day"] == 0.28
    template = dict(store.load_templates()["EMC3"])
    assert template["313-APL-0104"] == 1.034 and template["1S2E"] == 2.5
    assert template["EQ-HERRAMIENTA"] == pytest.approx(1.0)  # 3 % = una unidad de 0.03
    insumos = {i["code"]: i for i in store.list_insumos()}
    assert insumos["1S2E"]["origin"] == "importada"
    assert insumos["1S2E"]["origin_ref"] == "prisma-acero-2026 · 1S2E"
    assert insumos["313-APL-0104"]["unit_cost"] == 35200.0


def test_bring_with_another_code_and_force_over_existing(store):
    ref = next(r for r in store.browse_reference("cobre")["rows"])
    row = store.adopt_reference_as_concept(ref["ref_id"], code="HID-COBRE-13")
    assert row["code"] == "HID-COBRE-13"
    # force: la clave existente toma el precio publicado y el origen oficial.
    again = store.adopt_reference_as_concept(ref["ref_id"], code="HID-COBRE-13", force=True)
    assert again["origin"] == "oficial" and again["price_override"] == 180.5
