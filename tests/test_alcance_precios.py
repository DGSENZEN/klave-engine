"""Qué incluye un precio adoptado.

Un catálogo de destajos es un precio real, citable y con vigencia — y no es
el precio del concepto: paga la mano de obra y nada más. En una línea
sanitaria de 4 pulgadas el destajo vale $61.76 y el precio con tubo $315.59,
así que adoptar uno creyendo que es el otro deja el presupuesto corto por el
material entero.
"""

import pytest
from klave_engine.costing.catalog_store import CatalogStore
from klave_engine.costing.models import Concept
from klave_engine.costing.report import adopted_price_apu


def _concepto() -> Concept:
    return Concept(
        code="SAN-002", description="Tubería sanitaria de albañal", unit="M",
        phase="Instalación sanitaria", production_rate_per_day=28.0,
    )


def test_un_destajo_adoptado_lo_dice_en_la_procedencia():
    apu = adopted_price_apu(_concepto(), {
        "price": 61.76, "source": "Destajos (mano de obra) zona Sur",
        "clave": "S1-SAN-SN-01", "vigencia": "2026-08", "alcance": "mano_de_obra",
    })
    assert apu.direct_unit_cost == 61.76
    assert "SÓLO MANO DE OBRA, sin materiales" in (apu.price_source or "")
    assert "S1-SAN-SN-01" in (apu.price_source or "")


def test_un_precio_unitario_completo_no_lleva_esa_advertencia():
    apu = adopted_price_apu(_concepto(), {
        "price": 315.59, "source": "Catálogo Vivienda KLAV3",
        "clave": "1-INS-TUB-002", "vigencia": "2026-01", "alcance": "precios_unitarios",
    })
    assert "MANO DE OBRA" not in (apu.price_source or "")


def test_sin_alcance_declarado_se_asume_completo_y_no_se_grita():
    """Las fuentes viejas no traen el dato; inventar una advertencia sobre
    ellas sería ruido, y el ruido gasta la atención de la advertencia real."""
    apu = adopted_price_apu(_concepto(), {
        "price": 100.0, "source": "X", "clave": "Y", "vigencia": "",
    })
    assert "MANO DE OBRA" not in (apu.price_source or "")


def test_el_presupuesto_avisa_cuando_suma_destajos_como_si_fueran_completos():
    from klave_engine.costing.models import (
        BillOfQuantities,
        BoqLine,
        QuantityKind,
        UnitPriceAnalysis,
    )
    from klave_engine.costing.report import _warn_solo_mano_de_obra

    boq = BillOfQuantities(project_id="p", currency="MXN", lines=[
        BoqLine(concept_code="SAN-002", description="Tubería sanitaria", unit="M",
                quantity=167.75, unit_price=61.76, amount=10359.97, phase="Sanitaria",
                raw_quantity=167.75, raw_kind=QuantityKind.LENGTH,
                source_detection_count=1, confidence=0.78),
    ])
    apus = {"SAN-002": UnitPriceAnalysis(
        concept_code="SAN-002", concept_description="Tubería sanitaria", unit="M",
        lines=[], breakdown={}, direct_unit_cost=61.76,
        price_source="Destajos zona Sur · S1-SAN-SN-01 · SÓLO MANO DE OBRA, sin materiales",
    )}
    _warn_solo_mano_de_obra(boq, apus)
    aviso = next(w for w in boq.warnings if "destajo" in w)
    assert "$10,359.97" in aviso
    assert "SAN-002" in aviso
    assert "no el material" in aviso


# ------------------------------------------------- quitar una fuente -------


def test_una_fuente_importada_se_puede_quitar(tmp_path):
    """Sin esto, un catálogo importado con el alcance equivocado se queda para
    siempre compitiendo contra el bueno en el buscador."""
    store = CatalogStore(tmp_path / "c.db")
    store.import_reference(
        {"key": "prueba", "name": "Prueba", "publisher": "Catálogo propio",
         "region": "MX", "vigencia": "2026-08", "kind": "mano_de_obra", "url": ""},
        [{"clave": "A-1", "description": "Algo", "unit": "M", "price": 10.0}],
    )
    assert any(s["source_key"] == "prueba" for s in store.list_sources())
    quitada = store.delete_source("prueba")
    assert quitada["rows"] == 1
    assert not any(s["source_key"] == "prueba" for s in store.list_sources())


def test_no_se_quita_una_fuente_de_la_que_cuelga_un_precio(tmp_path):
    """El presupuesto quedaría citando una procedencia que ya no existe, que
    es peor que no citar ninguna."""
    store = CatalogStore(tmp_path / "c.db")
    store.import_reference(
        {"key": "prueba", "name": "Prueba", "publisher": "Catálogo propio",
         "region": "MX", "vigencia": "2026-08", "kind": "mano_de_obra", "url": ""},
        [{"clave": "A-1", "description": "Tubería sanitaria de albañal", "unit": "M",
          "price": 61.76}],
    )
    ref = next(r for r in store.list_reference_rows(["prueba"]))
    store.adopt_concept_reference("SAN-002", int(ref["ref_id"]))
    with pytest.raises(ValueError, match="SAN-002"):
        store.delete_source("prueba")
    assert any(s["source_key"] == "prueba" for s in store.list_sources())


def test_quitar_una_fuente_que_no_existe_es_un_error_claro(tmp_path):
    store = CatalogStore(tmp_path / "c.db")
    with pytest.raises(ValueError, match="no existe"):
        store.delete_source("nunca-importada")
