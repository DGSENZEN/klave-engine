"""Project creation names the obra, not the file."""

from pathlib import Path

from klave_engine.common import config as config_module

from apps.api import jobs as jobs_module
from apps.api.routes import projects as projects_module


def test_upload_takes_name_and_client(data_dir, monkeypatch):
    from fastapi.testclient import TestClient

    from apps.api.main import create_app

    monkeypatch.setenv("KLAVE_USERS_DATABASE_URL", "postgresql://nobody@127.0.0.1:1/none")
    config_module.get_settings.cache_clear()
    # Processing is a background job; the test only checks the manifest.
    fake = jobs_module.Job(project_id="x", job_id="j", run_id="r")
    monkeypatch.setattr(projects_module.JOB_STORE, "enqueue", lambda *a, **k: (fake, True))
    client = TestClient(create_app())
    dxf = Path("data/demo/demo_project_001/drawings/S-101.dxf")
    if not dxf.exists():
        from klave_engine.evals.fixtures import write_demo_project

        write_demo_project(data_dir / "demo_src")
        dxf = data_dir / "demo_src" / "drawings" / "S-101.dxf"
    with dxf.open("rb") as handle:
        response = client.post(
            "/projects/upload",
            files=[("files", ("S-101.dxf", handle, "application/dxf"))],
            data={"project_name": "  Torre   Reforma  ", "client": "Constructora GAYA"},
        )
    assert response.status_code == 202, response.text
    project_id = response.json()["project_id"]
    assert project_id.startswith("torre")
    info = client.get(f"/projects/{project_id}").json()
    assert info["project_name"] == "Torre Reforma" and info["client"] == "Constructora GAYA"


def test_upload_does_not_convert_inside_the_request(data_dir, monkeypatch):
    """Convertir un DWG tarda minutos y, dentro de la petición, congelaba
    todo el servidor: la subida responde en cuanto guarda y encola; la
    conversión es del trabajo."""
    from fastapi.testclient import TestClient
    from klave_engine.conversion import dwg_to_dxf, libredwg

    from apps.api.main import create_app

    config_module.get_settings.cache_clear()

    def no_aqui(*_a, **_k):
        raise AssertionError("la subida no debe convertir")

    monkeypatch.setattr(libredwg, "convert_dwg_to_dxf", no_aqui)
    monkeypatch.setattr(dwg_to_dxf, "convert_dwg_to_dxf", no_aqui)
    encolados = []
    fake = jobs_module.Job(project_id="x", job_id="j", run_id="r")
    def encolar(pid, *_a, **_k):
        encolados.append(pid)
        return fake, True

    monkeypatch.setattr(projects_module.JOB_STORE, "enqueue", encolar)
    client = TestClient(create_app())
    response = client.post(
        "/projects/upload",
        files=[("files", ("planta.dwg", b"AC1032" + b"\0" * 64, "application/acad"))],
        data={"project_name": "Juego grande"},
    )
    assert response.status_code == 202, response.text
    assert encolados == [response.json()["project_id"]]


def test_la_conversion_dice_cual_va(tmp_path, monkeypatch):
    from klave_engine.common.config import Settings
    from klave_engine.conversion import dwg_to_dxf
    from klave_engine.conversion.dwg_to_dxf import ConversionResult, ConversionStatus
    from klave_engine.ingestion.project_loader import ingest_project

    drawings = tmp_path / "drawings"
    drawings.mkdir()
    for name in ("a.dwg", "b.dwg", "c.dxf"):
        (drawings / name).write_bytes(b"x")
    manifest = ingest_project(tmp_path, project_name="p", processed_dir_name="processed")

    def falso(source, output_dir, _oda, _settings):
        return ConversionResult(source_path=str(source), output_path=str(source),
                                status=ConversionStatus.failed, error_message="ilegible")

    monkeypatch.setattr(dwg_to_dxf, "_convert_one", falso)
    avance: list[str] = []
    dwg_to_dxf.convert_project(manifest, Settings(), avance.append)
    assert avance == ["Convirtiendo planos (1 de 2): a.dwg", "Convirtiendo planos (2 de 2): b.dwg"]
