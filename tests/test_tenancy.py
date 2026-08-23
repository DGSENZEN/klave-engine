"""One catálogo per taller: a workspace's prices never leak into another's,
and the default workspace inherits the pre-workspace catalog file."""

from klave_engine.costing.catalog_store import get_catalog_store


def test_each_workspace_gets_its_own_catalog_file(data_dir):
    ws_a = get_catalog_store(data_dir, workspace_id="ws-a")
    ws_b = get_catalog_store(data_dir, workspace_id="ws-b")
    legacy = get_catalog_store(data_dir)
    assert ws_a is not ws_b and ws_a is not legacy
    assert ws_a.workspace_id == "ws-a" and legacy.workspace_id is None
    assert (data_dir / "catalogs" / "ws-a.db").exists()
    assert (data_dir / "catalogs" / "ws-b.db").exists()

    ws_a.upsert_insumo("MAT-BLOCK", unit_cost=999.0, source="Cotización A")
    assert ws_a.load_price_book()["MAT-BLOCK"].unit_cost == 999.0
    assert ws_b.load_price_book()["MAT-BLOCK"].unit_cost != 999.0
    assert legacy.load_price_book()["MAT-BLOCK"].unit_cost != 999.0


def test_default_workspace_adopts_the_legacy_catalog(data_dir, monkeypatch):
    from klave_engine.common.config import get_settings

    import apps.api.tenancy as tenancy

    legacy = get_catalog_store(data_dir)
    legacy.upsert_insumo("MAT-BLOCK", unit_cost=777.0, source="Cotización histórica")
    monkeypatch.setattr(tenancy, "default_workspace_id", lambda settings: "ws-default")
    settings = get_settings()

    adopted = tenancy.workspace_store(settings, "ws-default")
    assert adopted.load_price_book()["MAT-BLOCK"].unit_cost == 777.0
    other = tenancy.workspace_store(settings, "ws-other")
    assert other.load_price_book()["MAT-BLOCK"].unit_cost != 777.0
    # Open mode still reaches the legacy file.
    assert tenancy.workspace_store(settings, None).load_price_book()["MAT-BLOCK"].unit_cost == 777.0


def test_defaults_scope_is_per_workspace(data_dir, monkeypatch):
    from klave_engine.common.config import get_settings
    from klave_engine.costing.defaults import (
        defaults_path,
        load_workspace_defaults,
        save_workspace_defaults,
    )
    from klave_engine.costing.models import CostingConfig

    import apps.api.tenancy as tenancy

    monkeypatch.setattr(tenancy, "default_workspace_id", lambda settings: "ws-default")
    settings = get_settings()
    scope_a = tenancy.defaults_scope(settings, "ws-a")
    save_workspace_defaults(scope_a, CostingConfig(), "Ana")
    assert defaults_path(scope_a).name == "ws-a-defaults.json"
    assert load_workspace_defaults(scope_a) is not None
    assert load_workspace_defaults(tenancy.defaults_scope(settings, "ws-b")) is None
    assert load_workspace_defaults(tenancy.defaults_scope(settings, None)) is None
