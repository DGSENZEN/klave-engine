"""Previews before rewriting prices: roll-forward with dry_run writes
nothing, and the salario real preview shows old vs new per category."""

from klave_engine.common import config as config_module


def _client(monkeypatch):
    from fastapi.testclient import TestClient

    from apps.api.main import create_app

    monkeypatch.setenv("KLAVE_USERS_DATABASE_URL", "postgresql://nobody@127.0.0.1:1/none")
    config_module.get_settings.cache_clear()
    return TestClient(create_app())


def test_roll_forward_dry_run_previews_without_writing(data_dir, monkeypatch):
    client = _client(monkeypatch)
    before = {r["code"]: r for r in client.get("/catalog").json()["insumos"]}
    stale = client.put(
        "/catalog/insumos/MAT-BLOCK",
        json={"unit_cost": 20.0, "vigencia": "2024-01", "source_type": "cotizacion"},
    )
    assert stale.status_code == 200, stale.text
    client.put(
        "/catalog/indices",
        json={"source": "INPP", "values": {"2024-01": 100.0, "2026-08": 110.0}},
    )

    preview = client.post(
        "/catalog/indices/roll-forward",
        json={"status": "vencido", "dry_run": True, "to_month": "2026-08"},
    ).json()
    assert preview["dry_run"] is True
    row = next(u for u in preview["updated"] if u["code"] == "MAT-BLOCK")
    assert row["from"] == 20.0 and row["to"] == 22.0 and row["description"]
    after = {r["code"]: r for r in client.get("/catalog").json()["insumos"]}
    assert after["MAT-BLOCK"]["unit_cost"] == 20.0  # nothing written
    assert after["MAT-BLOCK"]["vigencia"] == "2024-01"

    applied = client.post(
        "/catalog/indices/roll-forward",
        json={"codes": ["MAT-BLOCK"], "dry_run": False, "to_month": "2026-08"},
    ).json()
    assert applied["dry_run"] is False and applied["updated"][0]["to"] == 22.0
    final = {r["code"]: r for r in client.get("/catalog").json()["insumos"]}
    assert final["MAT-BLOCK"]["unit_cost"] == 22.0
    assert final["MAT-BLOCK"]["source_type"] == "calculado"
    assert before["MAT-BLOCK"]["source_type"] != "calculado"


def test_labor_preview_shows_current_and_new_salario_real(data_dir, monkeypatch):
    client = _client(monkeypatch)
    state = client.get("/catalog/labor").json()
    categories = [
        {k: v for k, v in c.items() if k != "breakdown"} for c in state["categories"]
    ]
    categories[0]["salario_nominal"] = categories[0]["salario_nominal"] * 2
    preview = client.post(
        "/catalog/labor/preview", json={"params": state["params"], "categories": categories}
    )
    assert preview.status_code == 200, preview.text
    rows = preview.json()["rows"]
    assert rows[0]["code"] == categories[0]["code"]
    assert rows[0]["to"] > categories[0]["salario_nominal"]  # Sn × Fsr
    assert rows[0]["fsr"] > 1.0
    # The preview is not an apply: the saved state is untouched.
    again = client.get("/catalog/labor").json()
    assert again["categories"][0]["salario_nominal"] == state["categories"][0]["salario_nominal"]
