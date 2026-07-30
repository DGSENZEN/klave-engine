"""Local scheduler, immutable run publication, and conversion-failure tests."""

import threading
import time
from pathlib import Path
from types import SimpleNamespace

import pytest
from klave_engine.common.config import Settings
from klave_engine.common.errors import ConversionError, ProjectManifestError
from klave_engine.common.io import read_json, write_json
from klave_engine.evals.fixtures import write_demo_project
from klave_engine.ingestion.manifest import ProcessingStatus, load_manifest
from klave_engine.ingestion.project_loader import ingest_project
from klave_engine.pipeline import run_full_pipeline

from apps.api import jobs as jobs_module
from apps.api.dependencies import ProjectStore
from apps.api.jobs import ACTIVE_RUN_FILENAME, Job, JobQueueFullError, JobStore


def _wait_for_job(store: JobStore, project_id: str, root: Path, settings: Settings) -> Job:
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        job = store.get(project_id, root, settings)
        assert job is not None
        if job.state in {"processed", "failed"}:
            return job
        time.sleep(0.02)
    pytest.fail("job did not finish")


def test_scheduler_publishes_one_immutable_run(tmp_path: Path) -> None:
    settings = Settings(data_dir=tmp_path)
    root = tmp_path / "project"
    write_demo_project(root)
    manifest = ingest_project(root)
    jobs = JobStore()

    job, scheduled = jobs.enqueue(manifest.project_id, root, settings)
    assert scheduled is True
    completed = _wait_for_job(jobs, manifest.project_id, root, settings)
    assert completed.state == "processed"

    control = root / settings.processed_dir_name
    pointer = read_json(control / ACTIVE_RUN_FILENAME)
    assert pointer["run_id"] == job.run_id
    run_dir = control / pointer["artifact_dir"]
    assert (run_dir / "detections.json").exists()
    assert not (control / "detections.json").exists()

    project_store = ProjectStore(settings)
    project_store.register(manifest.project_id, root)
    assert project_store.read_artifact(manifest.project_id, "detections.json")


def test_scheduler_deduplicates_active_project_submission(tmp_path: Path, monkeypatch) -> None:
    settings = Settings(data_dir=tmp_path, max_concurrent_jobs=1, max_queued_jobs=0)
    root = tmp_path / "project"
    root.mkdir()
    started = threading.Event()
    release = threading.Event()

    def fake_pipeline(*args, **kwargs):
        started.set()
        assert release.wait(timeout=5)
        return SimpleNamespace(entities=[], detections=[])

    monkeypatch.setattr(jobs_module, "run_full_pipeline", fake_pipeline)
    jobs = JobStore()
    first, scheduled = jobs.enqueue("p_1", root, settings)
    assert scheduled is True
    assert started.wait(timeout=2)
    second, scheduled_again = jobs.enqueue("p_1", root, settings)
    assert scheduled_again is False
    assert second.job_id == first.job_id
    release.set()
    assert _wait_for_job(jobs, "p_1", root, settings).state == "processed"


def test_scheduler_applies_backpressure(tmp_path: Path, monkeypatch) -> None:
    settings = Settings(data_dir=tmp_path, max_concurrent_jobs=1, max_queued_jobs=0)
    first_root = tmp_path / "first"
    second_root = tmp_path / "second"
    first_root.mkdir()
    second_root.mkdir()
    started = threading.Event()
    release = threading.Event()

    def fake_pipeline(*args, **kwargs):
        started.set()
        assert release.wait(timeout=5)
        return SimpleNamespace(entities=[], detections=[])

    monkeypatch.setattr(jobs_module, "run_full_pipeline", fake_pipeline)
    jobs = JobStore()
    jobs.enqueue("p_1", first_root, settings)
    assert started.wait(timeout=2)
    with pytest.raises(JobQueueFullError):
        jobs.enqueue("p_2", second_root, settings)
    release.set()
    assert _wait_for_job(jobs, "p_1", first_root, settings).state == "processed"


def test_scheduler_marks_interrupted_persisted_job_failed(tmp_path: Path) -> None:
    settings = Settings(data_dir=tmp_path)
    root = tmp_path / "project"
    job = Job(project_id="p_1", job_id="job_1", run_id="run_1", state="running")
    write_json(root / "processed" / "latest_job.json", job.to_json())

    recovered = JobStore().get("p_1", root, settings)

    assert recovered is not None
    assert recovered.state == "failed"
    assert recovered.stage == "Interrumpido"
    assert read_json(root / "processed" / "latest_job.json")["state"] == "failed"


def test_pipeline_fails_closed_for_empty_project(tmp_path: Path) -> None:
    root = tmp_path / "empty"
    root.mkdir()

    with pytest.raises(ProjectManifestError, match="No DWG or DXF"):
        run_full_pipeline(root, Settings(data_dir=tmp_path))

    assert load_manifest(root).processing_status == ProcessingStatus.failed


def test_pipeline_fails_closed_for_unconvertible_dwg(tmp_path: Path) -> None:
    root = tmp_path / "dwg"
    drawings = root / "drawings"
    drawings.mkdir(parents=True)
    (drawings / "S-101.dwg").write_bytes(b"AC1018 fake dwg")

    # Conversion is non-fatal, but with no usable DXF the pipeline fails closed.
    with pytest.raises(ConversionError, match="No DXF files are available"):
        run_full_pipeline(root, Settings(data_dir=tmp_path))

    manifest = load_manifest(root)
    assert manifest.processing_status == ProcessingStatus.failed
    assert manifest.errors
