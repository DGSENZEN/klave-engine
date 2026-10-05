"""Los índices de un proyecto contra los otros del taller: con tres o más hay
historia y una frase cuando éste cae fuera; con menos, no se inventa."""

from klave_engine.costing.catalog_store import get_catalog_store
from klave_engine.costing.indicadores import con_historia, valores_de


def _ind(value):
    return {"indicators": [{"key": "acero_por_m3", "label": "Acero", "value": value,
                            "unit": "kg/m³", "status": "ok"}]}


def test_history_needs_three_projects_and_names_the_outlier():
    out = con_historia(_ind(210.0), [{"acero_por_m3": 140.0}, {"acero_por_m3": 165.0}])
    assert out["indicators"][0]["taller_n"] == 2 and "taller_note" not in out["indicators"][0]
    otros = [{"acero_por_m3": v} for v in (140.0, 150.0, 165.0, 155.0)]
    item = con_historia(_ind(210.0), otros)["indicators"][0]
    assert item["taller_median"] == 152.5 and item["taller_low"] == 140.0
    assert item["taller_note"] == "210.00 kg/m³; tus últimos 4: 140.00–165.00"
    inside = con_historia(_ind(150.0), otros)["indicators"][0]
    assert not inside.get("taller_note")


def test_store_keeps_one_row_per_project_and_excludes_self(data_dir):
    store = get_catalog_store(data_dir)
    store.save_project_indices("a", {"acero_por_m3": 140.0})
    store.save_project_indices("b", {"acero_por_m3": 150.0})
    store.save_project_indices("a", {"acero_por_m3": 145.0})
    assert sorted(v["acero_por_m3"] for v in store.load_project_indices()) == [145.0, 150.0]
    assert store.load_project_indices(exclude="a") == [{"acero_por_m3": 150.0}]
    assert valores_de(_ind(None)) == {}
