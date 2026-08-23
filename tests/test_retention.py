"""Retention: a project keeps its recent runs, its active run, and nothing else."""

import time
from pathlib import Path

from klave_engine.common.io import write_json

from apps.api.retention import prune_project_storage


def _make_run(control: Path, name: str, age: int) -> None:
    run = control / "runs" / name
    (run / "reports").mkdir(parents=True)
    (run / "detections.json").write_text("[]")
    (control / "croquis" / name).mkdir(parents=True)
    stamp = time.time() - age
    import os

    os.utime(run, (stamp, stamp))


def test_prune_keeps_the_active_run_and_the_newest_n(tmp_path):
    control = tmp_path
    for index, name in enumerate(["run_a", "run_b", "run_c", "run_d", "run_e"]):
        _make_run(control, name, age=(5 - index) * 1000)  # run_e newest
    write_json(control / "active_run.json", {"run_id": "run_b", "artifact_dir": "runs/run_b"})
    (control / "jobs").mkdir()
    for index in range(15):
        (control / "jobs" / f"job_{index:02d}.json").write_text("{}")

    removed = prune_project_storage(control, keep_runs=2, keep_jobs=10)
    kept = sorted(p.name for p in (control / "runs").iterdir())
    # Newest two (run_d, run_e) plus the active run_b survive.
    assert kept == ["run_b", "run_d", "run_e"]
    assert removed["runs"] == 2
    assert sorted(p.name for p in (control / "croquis").iterdir()) == ["run_b", "run_d", "run_e"]
    assert len(list((control / "jobs").iterdir())) == 10
    # Idempotent: a second pass removes nothing.
    assert prune_project_storage(control, keep_runs=2, keep_jobs=10) == {
        "runs": 0, "croquis": 0, "jobs": 0,
    }


def test_prune_survives_an_empty_project(tmp_path):
    assert prune_project_storage(tmp_path) == {"runs": 0, "croquis": 0, "jobs": 0}


def test_delete_with_purge_removes_the_files_and_stays_inside_uploads(data_dir, monkeypatch):
    from fastapi.testclient import TestClient
    from klave_engine.common import config as config_module

    from apps.api.main import create_app

    monkeypatch.setenv("KLAVE_USERS_DATABASE_URL", "postgresql://nobody@127.0.0.1:1/none")
    config_module.get_settings.cache_clear()
    client = TestClient(create_app())

    root = data_dir / "uploads" / "proyecto_x"
    (root / "drawings").mkdir(parents=True)
    (root / "drawings" / "a.dxf").write_text("0\nEOF\n")
    write_json(root / "project_manifest.json", {
        "project_id": "proyecto_x", "project_name": "Proyecto X",
        "processing_status": "uploaded", "source_files": [],
    })
    from apps.api.dependencies import ProjectStore

    ProjectStore(config_module.get_settings()).register("proyecto_x", root)

    kept = client.delete("/projects/proyecto_x")
    assert kept.status_code == 200 and kept.json()["purged"] is False
    assert root.exists()  # without purge the files stay

    ProjectStore(config_module.get_settings()).register("proyecto_x", root)
    gone = client.delete("/projects/proyecto_x?purge=true")
    assert gone.status_code == 200 and gone.json()["purged"] is True
    assert not root.exists()
