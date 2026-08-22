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
