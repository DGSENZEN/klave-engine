"""Safe telemetry boundaries and explicit correlation context."""

import logging

import pytest
from fastapi.testclient import TestClient
from klave_engine.common.bitacora import errores_recientes, redactar

from apps.api.observability import redact_request_path


@pytest.mark.parametrize(
    "path,expected",
    [
        ("/auth/reset/SECRET/next?query=PRIVATE", "/auth/reset/[redacted]/next"),
        ("/auth/verify/SECRET", "/auth/verify/[redacted]"),
        ("/auth/verify/send", "/auth/verify/send"),
        (
            "/auth/invitations/by-token/SECRET/accept",
            "/auth/invitations/by-token/[redacted]/accept",
        ),
        ("/compartido/SECRET/report", "/compartido/[redacted]/report"),
    ],
)
def test_path_redaction(path, expected):
    assert redact_request_path(path) == expected


def test_message_redacts_token_urls_and_existing_secrets():
    message = (
        "failed https://host/auth/reset/SECRET?secret=PRIVATE for a@example.test "
        "Bearer abcdefghijklmnop sk-abcdefghijklmnop"
    )
    clean = redactar(message)
    for secret in ("SECRET", "PRIVATE", "a@example.test", "abcdefghijklmnop"):
        assert secret not in clean


@pytest.mark.parametrize("mode", ["success", "denied", "unmatched", "exception"])
def test_request_logs_and_error_records_redact_tokens(data_dir, caplog, mode):
    from apps.api.main import create_app

    app = create_app()

    @app.get("/auth/reset/{token}/probe")
    def probe(token: str):
        if mode == "exception":
            raise RuntimeError("failed /auth/verify/SECRET?code=PRIVATE")
        return {"ok": True}

    client = TestClient(app, raise_server_exceptions=False)
    caplog.set_level(logging.INFO)
    if mode == "denied":
        response = client.post(
            "/auth/reset/SECRET?code=PRIVATE", headers={"origin": "https://bad.test"}
        )
        assert response.status_code == 403
    else:
        path = "/auth/reset/SECRET/" + ("missing" if mode == "unmatched" else "probe")
        response = client.get(path + "?code=PRIVATE")
        assert response.status_code == {"success": 200, "unmatched": 404, "exception": 500}[mode]
    assert response.headers.get("x-request-id")
    logs = "\n".join(r.getMessage() for r in caplog.records if r.name.startswith("klave"))
    assert "SECRET" not in logs and "PRIVATE" not in logs
    if mode == "exception":
        rows = errores_recientes(data_dir)
        assert len(rows) == 1
        assert "SECRET" not in str(rows) and "PRIVATE" not in str(rows)


def test_context_binding_is_nested_and_resets_after_exception():
    from klave_engine.common.diagnostics import DiagnosticContext, bind_context, current_context

    original = current_context()
    with bind_context(DiagnosticContext(request_id="outer", workspace_id="ws-a")):
        assert current_context().request_id == "outer"
        with pytest.raises(RuntimeError), bind_context(DiagnosticContext(request_id="inner")):
            assert current_context().workspace_id == ""
            raise RuntimeError("controlled")
        assert current_context().request_id == "outer"
    assert current_context() == original


def test_request_identity_comes_from_session():
    from starlette.requests import Request

    from apps.api.observability import context_from_request

    request = Request(
        {
            "type": "http",
            "headers": [(b"x-actor", b"FORGED"), (b"x-workspace-id", b"FOREIGN")],
            "state": {"request_id": "ref-1", "user": {"user_id": "u1", "workspace_id": "ws-a"}},
        }
    )
    context = context_from_request(request, project_id="p1")
    assert (context.request_id, context.workspace_id, context.user_id, context.project_id) == (
        "ref-1",
        "ws-a",
        "u1",
        "p1",
    )


def test_lifecycle_schema_and_logging_failure(caplog, monkeypatch):
    import json

    from klave_engine.common import diagnostics

    context = diagnostics.DiagnosticContext(request_id="ref-1")
    caplog.set_level(logging.INFO)
    diagnostics.emit_job_event("job_started", context, outcome="running", stage="processing")
    event = json.loads(next(r.message for r in caplog.records if r.name == "klave.jobs"))
    assert event["schema_version"] == 1 and event["request_id"] == "ref-1"
    assert event["ts"].endswith("+00:00")
    assert set(event) == {
        "schema_version",
        "ts",
        "event",
        "outcome",
        "stage",
        "error_code",
        "request_id",
        "workspace_id",
        "user_id",
        "project_id",
        "job_id",
        "run_id",
    }
    before = len(caplog.records)
    diagnostics.emit_job_event("arbitrary-secret", context, outcome="running")
    assert len(caplog.records) == before

    def broken(*args, **kwargs):
        raise OSError("broken logger")

    monkeypatch.setattr(logging.getLogger("klave.jobs"), "info", broken)
    diagnostics.emit_job_event("job_started", context, outcome="running")


def test_log_filter_keeps_request_id_and_attaches_context():
    from klave_engine.common.diagnostics import DiagnosticContext, bind_context
    from klave_engine.common.logging import _RequestIdFilter, request_id_var

    token = request_id_var.set("ref-1")
    try:
        record = logging.makeLogRecord({"msg": "safe"})
        assert _RequestIdFilter().filter(record)
        assert record.request_id == "ref-1"
        with bind_context(DiagnosticContext(workspace_id="ws-a", user_id="u1")):
            _RequestIdFilter().filter(record)
            assert record.workspace_id == "ws-a" and record.user_id == "u1"
    finally:
        request_id_var.reset(token)


def test_request_completion_log_retains_authenticated_context(data_dir, caplog):
    from fastapi import Request
    from klave_engine.common.logging import _RequestIdFilter

    from apps.api.main import create_app

    app = create_app()

    @app.get("/auth/context/{project_id}")
    def context_route(request: Request, project_id: str):
        request.state.user = {"user_id": "u1", "workspace_id": "ws-a"}
        return {"ok": True}

    caplog.set_level(logging.INFO)
    filter_ = _RequestIdFilter()
    caplog.handler.addFilter(filter_)
    try:
        response = TestClient(app).get("/auth/context/p1", headers={"x-request-id": "ref-1"})
        assert response.status_code == 200
        record = next(r for r in caplog.records if r.name == "klave.request")
        assert (record.request_id, record.workspace_id, record.user_id, record.project_id) == (
            "ref-1",
            "ws-a",
            "u1",
            "p1",
        )
    finally:
        caplog.handler.removeFilter(filter_)


@pytest.mark.parametrize("broken_boundary", ["logger", "writer"])
def test_broken_api_diagnostics_preserve_support_response(data_dir, monkeypatch, broken_boundary):
    from apps.api import main

    app = main.create_app()

    @app.get("/auth/diagnostic-failure")
    def probe():
        raise RuntimeError("controlled product failure")

    def broken(*args, **kwargs):
        raise OSError("controlled diagnostic failure")

    if broken_boundary == "writer":
        monkeypatch.setattr(main, "anotar_error", broken)
    else:
        monkeypatch.setattr(main.logger, "log", broken)
        monkeypatch.setattr(main.logger, "error", broken)
    response = TestClient(app, raise_server_exceptions=False).get(
        "/auth/diagnostic-failure", headers={"x-request-id": "ref-api-failure"}
    )
    assert response.status_code == 500
    assert response.headers["x-request-id"] == "ref-api-failure"
    assert response.json()["request_id"] == "ref-api-failure"
