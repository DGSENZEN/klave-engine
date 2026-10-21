"""Application startup repairs interrupted jobs without blocking API availability."""

import warnings

import pytest
from fastapi.testclient import TestClient
from klave_engine.common.config import get_settings
from klave_engine.common.io import read_json, write_json

from apps.api import jobs
from apps.api.dependencies import ProjectStore


def test_create_app_uses_supported_startup_api(data_dir):
    from apps.api.main import create_app

    with warnings.catch_warnings():
        warnings.simplefilter("error", DeprecationWarning)
        create_app()


@pytest.mark.parametrize("state", ["queued", "running"])
def test_entering_client_repairs_persisted_orphan_jobs(data_dir, monkeypatch, state):
    from apps.api.main import create_app

    settings = get_settings()
    root = data_dir / "uploads" / "orphan-project"
    ProjectStore(settings).register("orphan-project", root)
    record = root / settings.processed_dir_name / "latest_job.json"
    write_json(
        record,
        jobs.Job(
            project_id="orphan-project", job_id="job-1", run_id="run-1", state=state
        ).to_json(),
    )
    monkeypatch.setattr(jobs, "JOB_STORE", jobs.JobStore())
    client = TestClient(create_app())
    assert read_json(record)["state"] == state

    with client:
        repaired = read_json(record)
        assert repaired["state"] == "failed"
        assert repaired["stage"] == "Interrumpido"
        assert repaired["error"]


def test_startup_remains_available_when_orphan_repair_fails(data_dir):
    from apps.api.main import create_app

    # The startup sweep cannot read a registry damaged by an interrupted write.
    (data_dir / "projects_registry.json").write_text("{", encoding="utf-8")

    with TestClient(create_app()) as client:
        assert client.get("/health").status_code == 200
