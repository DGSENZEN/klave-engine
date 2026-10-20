"""Service references are usable by browsers without exposing invitation secrets."""

import asyncio
import logging

from fastapi.testclient import TestClient

from apps.api.observability import RequestIdMiddleware


def test_browser_can_read_service_reference(data_dir):
    from apps.api.main import create_app

    with TestClient(create_app()) as client:
        response = client.get("/health", headers={"Origin": "http://localhost:3000"})
    assert response.headers["x-request-id"]
    exposed = response.headers["access-control-expose-headers"].lower()
    assert "x-request-id" in exposed
    assert "content-disposition" in exposed


def test_invitation_secret_is_absent_from_request_logs(caplog):
    async def app(scope, receive, send):
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b"ok"})

    async def unused():
        return {}

    async def sink(message):
        pass

    with caplog.at_level(logging.INFO, logger="klave.request"):
        asyncio.run(RequestIdMiddleware(app)(
            {"type": "http", "method": "POST", "headers": [],
             "path": "/auth/invitations/by-token/private-invitation-secret/accept"},
            unused, sink,
        ))
    assert "by-token" in caplog.text
    assert "private-invitation-secret" not in caplog.text


def test_unhandled_failure_has_a_browser_readable_reference(data_dir):
    from apps.api.main import create_app

    app = create_app()

    @app.get("/auth/support-reference-error")
    def broken():
        raise RuntimeError("synthetic failure")

    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.get(
            "/auth/support-reference-error",
            headers={"Origin": "http://localhost:3000"},
        )
    assert response.status_code == 500
    assert response.json()["request_id"]
    assert response.headers["x-request-id"] == response.json()["request_id"]
    assert response.headers["access-control-allow-origin"] == "http://localhost:3000"
