"""Private durable origin metadata and isolated worker context."""

from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace

import pytest
from klave_engine.common.config import get_settings
from klave_engine.common.diagnostics import DiagnosticContext, current_context
from klave_engine.common.io import read_json

from apps.api import jobs


class HeldExecutor:
    def submit(self, *args):
        self.pending = args


@pytest.fixture
def local_jobs(data_dir, monkeypatch):
    from apps.api import tenancy

    monkeypatch.setattr(tenancy, "store_for_project", lambda *_: None)
    monkeypatch.setattr(jobs, "snapshot_before_reprocess", lambda *_: None)
    monkeypatch.setattr(jobs, "prune_project_storage", lambda *a, **k: None)
    import apps.api.routes.exports as exports

    monkeypatch.setattr(exports, "precalentar_croquis", lambda *_: None)
    store = jobs.JobStore(_executor=HeldExecutor())
    settings = get_settings()
    settings.max_queued_jobs = 10
    return store, settings, data_dir


def origin(user="u1", workspace="ws-a", request="ref-1"):
    return DiagnosticContext(request_id=request, workspace_id=workspace, user_id=user)


def test_private_context_roundtrip_and_legacy_records(local_jobs):
    store, settings, root = local_jobs
    job, created = store.enqueue("p1", root, settings, context=origin())
    assert created
    assert "diagnostic_context" not in job.to_json()
    record = read_json(root / settings.processed_dir_name / "latest_job.json")
    assert record["diagnostic_context"]["request_id"] == "ref-1"
    assert record["diagnostic_context"]["job_id"] == job.job_id
    assert jobs.Job.from_json(record).diagnostic_context == job.diagnostic_context
    assert jobs.Job.from_json(job.to_json()).diagnostic_context == DiagnosticContext()
    record["diagnostic_context"] = ["malformed"]
    assert jobs.Job.from_json(record).diagnostic_context == DiagnosticContext()


def test_active_job_reuse_preserves_origin_and_public_events(local_jobs, monkeypatch):
    store, settings, root = local_jobs
    events = []
    monkeypatch.setattr(jobs.BUS, "publish", lambda *a, **k: events.append(k))
    first, _ = store.enqueue("p1", root, settings, context=origin())
    duplicate, created = store.enqueue("p1", root, settings, context=origin("u2", "ws-b"))
    assert not created and duplicate is first
    assert duplicate.diagnostic_context.user_id == "u1"
    assert all("diagnostic_context" not in item.get("data", {}) for item in events)


@pytest.mark.parametrize("fail_first", [False, True])
def test_reused_worker_context_is_bound_and_reset(local_jobs, monkeypatch, fail_first):
    store, settings, root = local_jobs
    seen = []

    def pipeline(*args, **kwargs):
        seen.append(current_context())
        if fail_first and len(seen) == 1:
            raise RuntimeError("controlled")
        return SimpleNamespace(entities=[], detections=[])

    monkeypatch.setattr(jobs, "run_full_pipeline", pipeline)
    with ThreadPoolExecutor(max_workers=1) as worker:
        for index, user in enumerate(("u1", "u2")):
            project = f"p{index}"
            path = root / project
            store.enqueue(
                project, path, settings, context=origin(user, f"ws-{index}", f"ref-{index}")
            )
            worker.submit(store._run, project, path, settings).result(timeout=5)
            assert worker.submit(current_context).result(timeout=5) == DiagnosticContext()
    assert [c.user_id for c in seen] == ["u1", "u2"]
    assert [c.workspace_id for c in seen] == ["ws-0", "ws-1"]
    assert all(c.job_id and c.run_id for c in seen)


def test_all_http_admission_calls_capture_request_origin(data_dir, monkeypatch):
    """Exercise upload, process and add-sheets through their real HTTP routes."""
    from fastapi.testclient import TestClient
    from klave_engine.evals.fixtures import write_demo_project

    from apps.api.main import create_app
    from apps.api.routes import projects

    source = data_dir / "synthetic"
    write_demo_project(source)
    drawing = (source / "drawings" / "S-101.dxf").read_bytes()
    captured = []

    def enqueue(pid, *args, **kwargs):
        captured.append((pid, kwargs.get("context")))
        return jobs.Job(project_id=pid, job_id="job-1", run_id="run-1"), True

    monkeypatch.setattr(projects.JOB_STORE, "enqueue", enqueue)
    client = TestClient(create_app())
    headers = {"x-request-id": "ref-http", "x-actor": "FORGED"}
    response = client.post(
        "/projects/upload",
        headers=headers,
        files=[("files", ("one.dxf", drawing, "application/dxf"))],
    )
    assert response.status_code == 202, response.text
    pid = response.json()["project_id"]
    response = client.post(f"/projects/{pid}/process", headers=headers)
    assert response.status_code == 202, response.text
    response = client.post(
        f"/projects/{pid}/files",
        headers=headers,
        files=[("files", ("two.dxf", drawing, "application/dxf"))],
    )
    assert response.status_code == 202, response.text
    assert len(captured) == 3
    for project, context in captured:
        assert context.request_id == "ref-http" and context.project_id == project
        assert context.user_id == ""  # Open-mode X-Actor is not an authenticated identity.


def lifecycle(caplog):
    import json

    return [json.loads(r.getMessage()) for r in caplog.records if r.name == "klave.jobs"]


def test_lifecycle_order_stages_and_duration(local_jobs, monkeypatch, caplog):
    import logging

    store, settings, root = local_jobs
    caplog.set_level(logging.INFO)

    def pipeline(*args, **kwargs):
        for text in (
            "Convirtiendo planos (1 de 2): PRIVATE.dwg",
            "Convirtiendo planos (2 de 2): PRIVATE.dwg",
            "Leyendo el dibujo",
        ):
            kwargs["progreso"](text)
        return SimpleNamespace(entities=[], detections=[])

    class ImmediateExecutor:
        def submit(self, fn, *args):
            fn(*args)

    store._executor = ImmediateExecutor()
    monkeypatch.setattr(jobs, "run_full_pipeline", pipeline)
    store.enqueue("p1", root, settings, context=origin())
    events = lifecycle(caplog)
    assert [e["event"] for e in events] == [
        "job_admitted",
        "job_started",
        "job_stage_changed",
        "job_stage_changed",
        "job_completed",
    ]
    assert [e["stage"] for e in events] == [
        "queued",
        "processing",
        "converting",
        "reading",
        "completed",
    ]
    assert events[-1]["duration_ms"] >= 0
    assert "PRIVATE" not in str(events)


@pytest.mark.parametrize("conversion", [False, True])
def test_worker_failures_are_recorded_once_with_origin(local_jobs, monkeypatch, caplog, conversion):
    import logging

    from klave_engine.common.bitacora import errores_recientes
    from klave_engine.common.errors import ConversionError

    store, settings, root = local_jobs
    caplog.set_level(logging.INFO)

    def pipeline(*args, **kwargs):
        kwargs["progreso"]("Convirtiendo planos (1 de 1): PRIVATE.dwg")
        raise (ConversionError if conversion else RuntimeError)(
            "bad /auth/reset/SECRET?code=PRIVATE"
        )

    monkeypatch.setattr(jobs, "run_full_pipeline", pipeline)
    job, _ = store.enqueue("p1", root, settings, context=origin())
    store._run("p1", root, settings)
    assert job.state == "failed"
    rows = errores_recientes(settings.data_dir, workspace="ws-a")
    assert len(rows) == 1
    row = rows[0]
    assert (row["request_id"], row["user_id"], row["job_id"], row["run_id"]) == (
        "ref-1",
        "u1",
        job.job_id,
        job.run_id,
    )
    assert row["error_code"] == ("conversion_failed" if conversion else "processing_failed")
    assert row["stage"] == "converting"
    assert "SECRET" not in str(rows)
    assert len([e for e in lifecycle(caplog) if e["event"] == "job_failed"]) == 1


def test_recovery_records_interruption_once(local_jobs, caplog):
    import logging

    from klave_engine.common.bitacora import errores_recientes

    store, settings, root = local_jobs
    store.enqueue("p1", root, settings, context=origin())
    caplog.set_level(logging.INFO)
    restarted = jobs.JobStore()
    assert restarted.get("p1", root, settings).state == "failed"
    restarted.get("p1", root, settings)
    jobs.JobStore().get("p1", root, settings)
    assert len([e for e in lifecycle(caplog) if e["event"] == "job_interrupted"]) == 1
    rows = errores_recientes(settings.data_dir)
    assert len(rows) == 1 and rows[0]["error_code"] == "processing_interrupted"


def test_post_publication_prewarm_failure_keeps_job_completed(local_jobs, monkeypatch, caplog):
    import logging

    import apps.api.routes.exports as exports

    store, settings, root = local_jobs
    caplog.set_level(logging.INFO)
    monkeypatch.setattr(
        jobs, "run_full_pipeline", lambda *a, **k: SimpleNamespace(entities=[], detections=[])
    )

    def broken(*args):
        raise RuntimeError("controlled prewarm failure")

    monkeypatch.setattr(exports, "precalentar_croquis", broken)
    job, _ = store.enqueue("p1", root, settings, context=origin())
    store._run("p1", root, settings)
    assert job.state == "processed"
    assert [e["event"] for e in lifecycle(caplog)][-1] == "job_completed"
    assert not any(e["event"] == "job_failed" for e in lifecycle(caplog))


@pytest.mark.parametrize("pipeline_fails", [False, True])
def test_telemetry_failure_does_not_hide_real_persistence_failure(
    local_jobs, monkeypatch, pipeline_fails
):
    store, settings, root = local_jobs

    def broken(*args, **kwargs):
        raise OSError("controlled write failure")

    monkeypatch.setattr(jobs, "emit_job_event", broken)
    monkeypatch.setattr(jobs, "anotar_error", broken)

    def pipeline(*args, **kwargs):
        if pipeline_fails:
            raise RuntimeError("controlled pipeline failure")
        return SimpleNamespace(entities=[], detections=[])

    monkeypatch.setattr(jobs, "run_full_pipeline", pipeline)
    job, _ = store.enqueue("p1", root, settings, context=origin())
    store._run("p1", root, settings)
    assert job.state == ("failed" if pipeline_fails else "processed")
    monkeypatch.setattr(store, "_persist", broken)
    with pytest.raises(OSError, match="controlled write failure"):
        store.enqueue("p2", root / "p2", settings, context=origin())
