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


# ------------------------------------------- deshacer una importación ------


def _matriz(store, source: str, clave: str, costo: float) -> None:
    from klave_engine.costing.sources.matrices import ConceptRow, InsumoRow, MatricesParse

    store.import_matrices(
        MatricesParse(
            concepts=[ConceptRow(code=clave, description=f"Concepto {clave}", unit="M2",
                                 phase="Destajos", production_rate_per_day=None,
                                 components=[("CUA-01", 0.05)])],
            insumos={"CUA-01": InsumoRow(code="CUA-01", description="Cuadrilla 1",
                                         unit="JOR", unit_cost=costo,
                                         resource_type="mano_de_obra")},
            problems=[],
        ),
        source,
    )


def test_una_importacion_de_matrices_se_puede_deshacer(tmp_path):
    """La primera importación de un taller casi nunca es la buena, y sin esto
    se quedaba para siempre."""
    store = CatalogStore(tmp_path / "c.db")
    _matriz(store, "Destajos zona Norte", "N1-PRE-TRA-01", 650.0)
    assert any(c["code"] == "N1-PRE-TRA-01" for c in store.load_concepts())
    hecho = store.undo_import("Destajos zona Norte")
    assert hecho["removed"] == 1
    assert not any(c["code"] == "N1-PRE-TRA-01" for c in store.load_concepts())


def test_deshacer_no_toca_los_conceptos_del_motor(tmp_path):
    """Los que el motor lee del plano y los que el taller escribió a mano no
    nacieron de esa importación y no se van con ella."""
    store = CatalogStore(tmp_path / "c.db")
    antes = {c["code"] for c in store.load_concepts()}
    _matriz(store, "Destajos zona Sur", "S1-PRE-TRA-01", 540.0)
    store.undo_import("Destajos zona Sur")
    assert antes <= {c["code"] for c in store.load_concepts()}


def test_deshacer_conserva_lo_que_ya_tiene_precio_adoptado(tmp_path):
    """Algún presupuesto lo está citando."""
    store = CatalogStore(tmp_path / "c.db")
    _matriz(store, "Destajos X", "X1-ALB-MUR-01", 700.0)
    store.import_reference(
        {"key": "pub", "name": "Publicación", "publisher": "Alguien", "region": "MX",
         "vigencia": "2026-08", "kind": "precios_unitarios", "url": ""},
        [{"clave": "P-1", "description": "Muro", "unit": "M2", "price": 500.0}],
    )
    ref = next(iter(store.list_reference_rows(["pub"])))
    store.adopt_concept_reference("X1-ALB-MUR-01", int(ref["ref_id"]))
    hecho = store.undo_import("Destajos X")
    assert hecho["removed"] == 0
    assert hecho["kept_with_price"] == ["X1-ALB-MUR-01"]


def test_dos_catalogos_con_la_misma_clave_de_cuadrilla_lo_dicen(tmp_path):
    """La cuadrilla «CUA-01» vale distinto en el norte y en el sur, y las
    matrices de cada zona la usan esperando la suya. El último import gana
    —no hay dónde guardar dos— pero callarlo dejaría media obra costeando con
    el precio de la otra punta del país."""
    store = CatalogStore(tmp_path / "c.db")
    _matriz(store, "Destajos zona Norte", "N1-A", 650.0)
    with_sur = store.import_matrices.__self__  # noqa: B018 — legibilidad
    from klave_engine.costing.sources.matrices import ConceptRow, InsumoRow, MatricesParse

    aviso = with_sur.import_matrices(
        MatricesParse(
            concepts=[ConceptRow(code="S1-A", description="Concepto sur", unit="M2",
                                 phase="Destajos", production_rate_per_day=None,
                                 components=[("CUA-01", 0.05)])],
            insumos={"CUA-01": InsumoRow(code="CUA-01", description="Cuadrilla 1",
                                         unit="JOR", unit_cost=540.0,
                                         resource_type="mano_de_obra")},
            problems=[],
        ),
        "Destajos zona Sur",
    )
    texto = " ".join(aviso["problems"])
    assert "cambiaron de precio" in texto
    assert "CUA-01" in texto and "650" in texto and "540" in texto
