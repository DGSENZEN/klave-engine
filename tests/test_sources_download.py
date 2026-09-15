"""Descargar e importar en un paso, y el arranque de un taller nuevo: cada
fuente oficial baja al servidor, se asienta en el manifiesto y entra a la
base; la que falla se reporta sin detener a las demás."""

import json
from pathlib import Path

import httpx
import pytest
from klave_engine.common import config as config_module
from klave_engine.costing.sources import registry
from klave_engine.costing.sources.registry import SourceSpec, fetch_source, local_manifest

PDF_BYTES = b"%PDF-1.4 fake tabulador\n"


def _spec(url: str, filename: str = "prueba.pdf") -> SourceSpec:
    return SourceSpec(
        key="prueba", name="Prueba", publisher="Nadie", region="MX", vigencia="2026-01",
        kind="precios_unitarios", filename=filename, parser=lambda p: iter(()), url=url,
    )


def _client(handler) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(handler))


def test_fetch_source_writes_file_and_manifest(data_dir):
    def handler(request):
        assert request.url.path.endswith("tab.pdf")
        return httpx.Response(200, content=PDF_BYTES)

    spec = _spec("https://ejemplo.gob.mx/tab.pdf")
    result = fetch_source(spec, data_dir, client=_client(handler))
    assert result["ok"] and result["bytes"] == len(PDF_BYTES)
    assert (data_dir / "sources" / "prueba.pdf").read_bytes() == PDF_BYTES
    assert not (data_dir / "sources" / "prueba.pdf.part").exists()
    manifest = local_manifest(data_dir)
    assert manifest["prueba.pdf"]["sha256"] == result["sha256"]
    assert manifest["prueba.pdf"]["fetched_at"]


def test_fetch_source_refuses_errors_and_indirect_links(data_dir):
    def not_found(request):
        return httpx.Response(404)

    spec = _spec("https://ejemplo.gob.mx/tab.pdf")
    result = fetch_source(spec, data_dir, client=_client(not_found))
    assert not result["ok"] and "404" in result["problem"]
    assert not (data_dir / "sources" / "prueba.pdf").exists()

    def empty(request):
        return httpx.Response(200, content=b"")

    result = fetch_source(_spec("https://ejemplo.gob.mx/tab.pdf"), data_dir, client=_client(empty))
    assert not result["ok"] and "vacía" in result["problem"]

    result = fetch_source(_spec("https://ejemplo.gob.mx/pagina-de-descargas/"), data_dir)
    assert not result["ok"] and "descárgalo a mano" in result["problem"]


def _api(monkeypatch):
    from fastapi.testclient import TestClient

    from apps.api.main import create_app

    config_module.get_settings.cache_clear()
    return TestClient(create_app())


def test_download_endpoint_fetches_and_imports(data_dir, monkeypatch):
    rows = [{"clave": "X-1", "description": "Concepto de prueba", "unit": "M2", "price": 10.0}]
    spec = SourceSpec(
        key="prueba-oficial", name="Fuente de prueba", publisher="Nadie", region="MX",
        vigencia="2026-01", kind="precios_unitarios", filename="prueba_oficial.pdf",
        parser=lambda p: iter(rows), url="https://ejemplo.gob.mx/prueba.pdf",
    )
    monkeypatch.setitem(registry.SOURCES, spec.key, spec)

    def fake_fetch(spec_, data_dir_, *, client=None):
        directory = Path(data_dir_) / "sources"
        directory.mkdir(parents=True, exist_ok=True)
        (directory / spec_.filename).write_bytes(PDF_BYTES)
        manifest = local_manifest(data_dir_)
        manifest[spec_.filename] = {"sha256": "abc", "bytes": 3, "fetched_at": "hoy", "ok": True}
        (directory / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
        return {"ok": True, "filename": spec_.filename, "bytes": 3, "sha256": "abc"}

    monkeypatch.setattr("apps.api.routes.catalog.fetch_source", fake_fetch)
    client = _api(monkeypatch)
    response = client.post("/catalog/sources/prueba-oficial/download")
    assert response.status_code == 200, response.text
    assert response.json() == {"source_key": "prueba-oficial", "rows": 1, "bytes": 3}
    sources = {s["key"]: s for s in client.get("/catalog/sources").json()["sources"]}
    assert sources["prueba-oficial"]["imported"]["row_count"] == 1


def test_bootstrap_reports_each_source(data_dir, monkeypatch):
    good = SourceSpec(
        key="buena", name="Buena", publisher="", region="MX", vigencia="2026-01",
        kind="precios_unitarios", filename="buena.pdf",
        parser=lambda p: iter([{"clave": "B-1", "description": "b", "unit": "M", "price": 1.0}]),
        url="https://ejemplo.gob.mx/buena.pdf",
    )
    manual = SourceSpec(
        key="manual", name="Manual", publisher="", region="MX", vigencia="2026-01",
        kind="precios_unitarios", filename="manual.xlsx", parser=lambda p: iter(()),
        url="https://ejemplo.gob.mx/descargas/",
    )
    monkeypatch.setattr(registry, "SOURCES", {"buena": good, "manual": manual})
    monkeypatch.setattr("apps.api.routes.catalog.SOURCES", {"buena": good, "manual": manual})

    def fake_fetch(spec_, data_dir_, *, client=None):
        if not spec_.url.endswith(".pdf"):
            return {"ok": False, "filename": spec_.filename, "problem": "descárgalo a mano"}
        directory = Path(data_dir_) / "sources"
        directory.mkdir(parents=True, exist_ok=True)
        (directory / spec_.filename).write_bytes(PDF_BYTES)
        return {"ok": True, "filename": spec_.filename, "bytes": 3, "sha256": "abc"}

    monkeypatch.setattr("apps.api.routes.catalog.fetch_source", fake_fetch)
    client = _api(monkeypatch)
    response = client.post("/catalog/sources/bootstrap")
    assert response.status_code == 200, response.text
    results = {r["source_key"]: r for r in response.json()["results"]}
    assert results["buena"] == {"source_key": "buena", "ok": True, "rows": 1}
    assert results["manual"]["ok"] is False and "a mano" in results["manual"]["problem"]
    # Segunda vez: la buena ya está y se salta.
    second = client.post("/catalog/sources/bootstrap").json()["results"]
    again = {r["source_key"]: r for r in second}
    assert again["buena"]["skipped"] == "ya importada"


@pytest.mark.parametrize("path", ["/catalog/base?q=b", "/catalog/base"])
def test_base_browse_and_adopt_endpoints(data_dir, monkeypatch, path):
    client = _api(monkeypatch)
    from klave_engine.costing.catalog_store import get_catalog_store

    store = get_catalog_store(data_dir)
    store.import_reference(
        {"key": "cdmx-prueba", "name": "CDMX prueba", "publisher": "SOBSE", "region": "MX-CMX",
         "vigencia": "2026-06", "kind": "precios_unitarios", "url": ""},
        [{"clave": "IB12BB", "description": "Tubería de cobre 13 mm b", "unit": "M",
          "price": 180.5, "group_clave": "IB12B", "group_description": "Tubos de cobre"}],
    )
    page = client.get(path).json()
    assert page["total"] == 1 and page["rows"][0]["in_taller"] is False
    assert page["rows"][0]["partida"] == "hidraulica"
    assert page["sources"][0]["source_key"] == "cdmx-prueba"
    ref_id = page["rows"][0]["ref_id"]
    adopted = client.post("/catalog/base/adopt", json={"ref_ids": [ref_id]})
    assert adopted.status_code == 201, adopted.text
    assert adopted.json()["created"] == [{"ref_id": ref_id, "code": "IB12BB", "origin": "oficial"}]
    again = client.post("/catalog/base/adopt", json={"ref_ids": [ref_id]}).json()
    assert again["created"] == [] and "ya existe" in again["skipped"][0]["reason"]
    concept = next(c for c in client.get("/catalog").json()["concepts"] if c["code"] == "IB12BB")
    assert concept["origin"] == "oficial" and concept["origin_ref"] == "cdmx-prueba · IB12BB"
    assert client.get("/catalog/base").json()["rows"][0]["in_taller"] is True
