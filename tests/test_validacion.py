"""Generar la matriz de un concepto sin matriz y validarla contra el precio
publicado: cada línea con su fuente, cuadrillas y precios de referencia
marcados, el veredicto en la fila, recalculado cuando un precio cambia y
conservado cuando una persona edita."""

import sqlite3

import pytest
from klave_engine.costing.catalog_store import CatalogStore, get_catalog_store

PUBLICACION = {
    "key": "cdmx-prueba", "name": "Tabulador CDMX prueba", "publisher": "SOBSE",
    "region": "MX-CMX", "vigencia": "2026-06", "kind": "precios_unitarios", "url": "",
}


def _bare_concept(store: CatalogStore, code: str, description: str, unit: str, phase: str) -> None:
    conn = sqlite3.connect(store.db_path)
    conn.execute(
        "INSERT INTO concepts (code, description, unit, phase, production_rate_per_day, "
        "sequence_order, origin) VALUES (?, ?, ?, ?, 1.0, 900, 'taller')",
        (code, description, unit, phase),
    )
    conn.commit()
    conn.close()


@pytest.fixture
def store(data_dir) -> CatalogStore:
    s = get_catalog_store(data_dir)
    _bare_concept(s, "COL-TEST", "Columnas de concreto armado f'c=250 kg/cm² de 30x40 cm",
                  "M3", "Estructura")
    return s


def _concept(store: CatalogStore, code: str) -> dict:
    return next(c for c in store.load_concepts() if c["code"] == code)


def test_generate_writes_lines_with_sources_cuadrillas_and_reference_prices(store):
    result = store.generate_matrix("COL-TEST", actor="Diego")
    assert result["plantilla"] == "concreto-armado-m3"
    template = dict(store.load_templates()["COL-TEST"])
    assert template["MAT-CONC250"] == pytest.approx(1.03)
    assert template["MAT-CIMBRA"] == pytest.approx(11.67, abs=0.01)
    sources = store.load_template_sources()["COL-TEST"]
    assert sources["MAT-CONC250"] and "desperdicio" in sources["MAT-CONC250"]
    insumos = {i["code"]: i for i in store.list_insumos()}
    # La cuadrilla nació con su matriz y cobra por sus categorías (salario real).
    assert insumos["CUAD-ALB-1x1"]["kind"] == "cuadrilla"
    assert insumos["CUAD-ALB-1x1"]["unit_cost"] == pytest.approx(
        insumos["MO-ALBA"]["unit_cost"] + insumos["MO-AYUD"]["unit_cost"]
    )
    assert insumos["MO-ALBA"]["unit_cost"] > 400 and result["labor_aplicada"] is True
    assert store.get_setting("labor_fsr")
    # El concreto sin precio tomó el de referencia, marcado para validar.
    assert insumos["MAT-CONC250"]["unit_cost"] == 2650.0
    assert insumos["MAT-CONC250"]["source"] == "precio de referencia, validar"
    assert insumos["MAT-CONC250"]["origin"] == "generada"
    assert "MAT-VARILLA" in insumos and insumos["MAT-VARILLA"]["unit"] == "KG"
    assert "MAT-CONC250" in result["precios_de_referencia"]
    assert "CUAD-ALB-1x1" in result["cuadrillas_creadas"]
    row = _concept(store, "COL-TEST")
    assert row["origin"] == "generada"
    assert row["origin_ref"] == "generada · plantilla concreto-armado-m3"
    assert row["production_rate_per_day"] == pytest.approx(3.0)
    assert row["validation"]["verdict"] == "sin_referencia"
    assert row["validation"]["direct_cost"] > 0
    assert result["validation"]["verdict"] == "sin_referencia"


def test_verdicts_at_the_tolerance_boundary(store):
    store.generate_matrix("COL-TEST")
    direct = _concept(store, "COL-TEST")["validation"]["direct_cost"]
    store.import_reference(PUBLICACION, [
        {"clave": "EA01AA", "description": "Columnas de concreto armado f'c=250 kg/cm2",
         "unit": "M3", "price": round(direct / 1.10, 2), "group_clave": "EA01A",
         "group_description": "Concreto en estructura"},
    ])
    validation = store.validate_concept("COL-TEST")
    assert validation["verdict"] == "validada"
    assert validation["deviation_pct"] == pytest.approx(10.0, abs=0.05)
    assert validation["reference_clave"] == "EA01AA" and validation["reference_ref_id"]
    assert validation["tolerance_pct"] == 15.0
    # La tolerancia es del taller: bajarla cambia el veredicto sin volver a buscar.
    store.set_validation_tolerance(5.0)
    again = _concept(store, "COL-TEST")["validation"]
    assert again["verdict"] == "fuera_de_rango" and again["reference_ref_id"] == (
        validation["reference_ref_id"]
    )
    store.set_validation_tolerance(15.0)
    assert _concept(store, "COL-TEST")["validation"]["verdict"] == "validada"
    with pytest.raises(ValueError):
        store.set_validation_tolerance(0)


def test_price_change_revalidates_without_rematching(store):
    store.generate_matrix("COL-TEST")
    direct = _concept(store, "COL-TEST")["validation"]["direct_cost"]
    store.import_reference(PUBLICACION, [
        {"clave": "EA01AA", "description": "Columnas de concreto armado f'c=250 kg/cm2",
         "unit": "M3", "price": direct, "group_clave": "", "group_description": ""},
    ])
    before = store.validate_concept("COL-TEST")
    assert before["verdict"] == "validada" and abs(before["deviation_pct"]) < 0.01
    store.upsert_insumo("MAT-CONC250", unit_cost=2650.0 * 2)
    after = _concept(store, "COL-TEST")["validation"]
    assert after["verdict"] == "fuera_de_rango"
    assert after["direct_cost"] > before["direct_cost"]
    assert after["reference_ref_id"] == before["reference_ref_id"]
    store.adjust_prices(["MAT-CONC250"], -50.0, actor="Diego")
    assert _concept(store, "COL-TEST")["validation"]["verdict"] == "validada"


def test_person_edit_promotes_and_keeps_validation_and_sources(store):
    store.generate_matrix("COL-TEST")
    template = store.load_templates()["COL-TEST"]
    edited = [(code, qty * 1.5 if code == "MAT-VARILLA" else qty) for code, qty in template]
    store.set_apu_components("COL-TEST", edited, actor="Diego")
    row = _concept(store, "COL-TEST")
    assert row["origin"] == "taller" and row["touched_by"] == "Diego"
    assert row["validation"]["verdict"] == "sin_referencia"
    sources = store.load_template_sources()["COL-TEST"]
    assert sources["MAT-CONC250"]  # la fuente de la línea que no se tocó sobrevive


def test_generate_refuses_a_taller_matrix_without_force(store):
    store.upsert_insumo("MAT-X", description="X", unit="PZA", resource_type="material",
                        unit_cost=10.0)
    store.create_concept(
        code="COL-MANUAL", description="Columnas de concreto armado f'c=250 kg/cm²",
        unit="M3", phase="Estructura", production_rate_per_day=2.0,
        components=[("MAT-X", 1.0)],
    )
    with pytest.raises(ValueError, match="matriz del taller"):
        store.generate_matrix("COL-MANUAL")
    result = store.generate_matrix("COL-MANUAL", force=True)
    assert result["plantilla"] == "concreto-armado-m3"
    assert "MAT-X" not in dict(store.load_templates()["COL-MANUAL"])
    assert _concept(store, "COL-MANUAL")["origin"] == "generada"


def test_generate_missing_reports_what_it_could_not(store):
    _bare_concept(store, "LUM-TEST", "Suministro de luminaria LED 18 W", "PZA", "Eléctrica")
    est001_before = store.load_templates()["EST-001"]
    result = store.generate_missing(actor="Diego")
    generated = {g["code"] for g in result["generated"]}
    # Los conceptos sembrados que nunca tuvieron matriz también reciben una;
    # los que ya la tenían no se tocan.
    assert "COL-TEST" in generated and "ALB-001" in generated
    assert store.load_templates()["EST-001"] == est001_before
    skipped = {s["code"]: s["reason"] for s in result["skipped"]}
    assert "Ninguna plantilla" in skipped["LUM-TEST"]
    assert "diámetro" in skipped["HID-003"]  # tubería sin diámetro: no se inventa
    # Segunda pasada: nada que hacer.
    assert store.generate_missing()["generated"] == []
    summary = store.validate_generated()
    assert summary["validated"] == len(generated)
    assert summary["verdicts"]["sin_referencia"] == len(generated)
