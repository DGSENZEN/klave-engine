"""Private durable origin metadata and isolated worker context."""
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
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
    monkeypatch.setattr(tenancy, 'store_for_project', lambda *_: None)
    monkeypatch.setattr(jobs, 'snapshot_before_reprocess', lambda *_: None)
    monkeypatch.setattr(jobs, 'prune_project_storage', lambda *a, **k: None)
    import apps.api.routes.exports as exports
    monkeypatch.setattr(exports, 'precalentar_croquis', lambda *_: None)
    store = jobs.JobStore(_executor=HeldExecutor())
    settings = get_settings()
    settings.max_queued_jobs = 10
    return store, settings, data_dir


def origin(user='u1', workspace='ws-a', request='ref-1'):
    return DiagnosticContext(request_id=request, workspace_id=workspace, user_id=user)


def test_private_context_roundtrip_and_legacy_records(local_jobs):
    store, settings, root = local_jobs
    job, created = store.enqueue('p1', root, settings, context=origin())
    assert created
    assert 'diagnostic_context' not in job.to_json()
    record = read_json(root / settings.processed_dir_name / 'latest_job.json')
    assert record['diagnostic_context']['request_id'] == 'ref-1'
    assert record['diagnostic_context']['job_id'] == job.job_id
    assert jobs.Job.from_json(record).diagnostic_context == job.diagnostic_context
    assert jobs.Job.from_json(job.to_json()).diagnostic_context == DiagnosticContext()
    record['diagnostic_context'] = ['malformed']
    assert jobs.Job.from_json(record).diagnostic_context == DiagnosticContext()


def test_active_job_reuse_preserves_origin_and_public_events(local_jobs, monkeypatch):
    store, settings, root = local_jobs
    events = []
    monkeypatch.setattr(jobs.BUS, 'publish', lambda *a, **k: events.append(k))
    first, _ = store.enqueue('p1', root, settings, context=origin())
    duplicate, created = store.enqueue('p1', root, settings, context=origin('u2', 'ws-b'))
    assert not created and duplicate is first
    assert duplicate.diagnostic_context.user_id == 'u1'
    assert all('diagnostic_context' not in item.get('data', {}) for item in events)


@pytest.mark.parametrize('fail_first', [False, True])
def test_reused_worker_context_is_bound_and_reset(local_jobs, monkeypatch, fail_first):
    store, settings, root = local_jobs
    seen = []

    def pipeline(*args, **kwargs):
        seen.append(current_context())
        if fail_first and len(seen) == 1:
            raise RuntimeError('controlled')
        return SimpleNamespace(entities=[], detections=[])

    monkeypatch.setattr(jobs, 'run_full_pipeline', pipeline)
    with ThreadPoolExecutor(max_workers=1) as worker:
        for index, user in enumerate(('u1', 'u2')):
            project = f'p{index}'
            path = root / project
            store.enqueue(project, path, settings,
                          context=origin(user, f'ws-{index}', f'ref-{index}'))
            worker.submit(store._run, project, path, settings).result(timeout=5)
            assert worker.submit(current_context).result(timeout=5) == DiagnosticContext()
    assert [c.user_id for c in seen] == ['u1', 'u2']
    assert [c.workspace_id for c in seen] == ['ws-0', 'ws-1']
    assert all(c.job_id and c.run_id for c in seen)


def test_all_http_admission_calls_capture_request_origin(data_dir, monkeypatch):
    """Exercise upload, process and add-sheets through their real HTTP routes."""
    from fastapi.testclient import TestClient
    from klave_engine.evals.fixtures import write_demo_project

    from apps.api.main import create_app
    from apps.api.routes import projects

    source = data_dir / 'synthetic'
    write_demo_project(source)
    drawing = (source / 'drawings' / 'S-101.dxf').read_bytes()
    captured = []

    def enqueue(pid, *args, **kwargs):
        captured.append((pid, kwargs.get('context')))
        return jobs.Job(project_id=pid, job_id='job-1', run_id='run-1'), True

    monkeypatch.setattr(projects.JOB_STORE, 'enqueue', enqueue)
    client = TestClient(create_app())
    headers = {'x-request-id': 'ref-http', 'x-actor': 'FORGED'}
    response = client.post('/projects/upload', headers=headers,
                           files=[('files', ('one.dxf', drawing, 'application/dxf'))])
    assert response.status_code == 202, response.text
    pid = response.json()['project_id']
    response = client.post(f'/projects/{pid}/process', headers=headers)
    assert response.status_code == 202, response.text
    response = client.post(f'/projects/{pid}/files', headers=headers,
                           files=[('files', ('two.dxf', drawing, 'application/dxf'))])
    assert response.status_code == 202, response.text
    assert len(captured) == 3
    for project, context in captured:
        assert context.request_id == 'ref-http' and context.project_id == project
        assert context.user_id == ''  # Open-mode X-Actor is not an authenticated identity.
