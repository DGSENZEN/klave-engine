"""OAuth must return through the public web proxy, never an internal binding URL."""

from urllib.parse import parse_qs, urlsplit

import httpx
from fastapi import FastAPI
from fastapi.testclient import TestClient
from klave_engine.common.config import Settings, get_settings

from apps.api.auth.common import users_dependency
from apps.api.auth.routes import router


def client_with_prefix(prefix="/api"):
    app = FastAPI()
    settings = Settings(
        _env_file=None, web_origin="https://pilot.example", api_public_prefix=prefix,
        auth_google_id="synthetic-client", auth_google_secret="synthetic-secret",
    )
    app.dependency_overrides[get_settings] = lambda: settings
    app.dependency_overrides[users_dependency] = lambda: object()
    app.include_router(router)
    return TestClient(app, base_url="https://app.internal", follow_redirects=False)


def test_google_start_uses_public_prefix_and_cookie_path():
    client = client_with_prefix()
    response = client.get("/auth/google?invite=synthetic-invite")
    query = parse_qs(urlsplit(response.headers["location"]).query)
    assert query["redirect_uri"] == ["https://pilot.example/api/auth/google/callback"]
    cookies = response.headers.get_list("set-cookie")
    assert len(cookies) == 2
    assert all("Path=/api/auth" in cookie for cookie in cookies)


def test_failed_callback_clears_cookies_at_the_same_public_path():
    response = client_with_prefix().get("/auth/google/callback?code=code&state=wrong")
    assert response.headers["location"] == "https://pilot.example/bienvenida?error=google"
    assert all("Path=/api/auth" in cookie for cookie in response.headers.get_list("set-cookie"))


def test_token_exchange_uses_the_same_public_callback(monkeypatch):
    received = {}

    class TokenEndpoint:
        def __init__(self, **_kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            pass

        async def post(self, _url, *, data):
            received.update(data)
            return httpx.Response(400, json={"error": "invalid_grant"})

    monkeypatch.setattr(httpx, "AsyncClient", TokenEndpoint)
    client = client_with_prefix()
    from apps.api.auth.routes import STATE_COOKIE

    client.cookies.set(STATE_COOKIE, "synthetic-state")
    response = client.get("/auth/google/callback?code=code&state=synthetic-state")
    assert response.status_code == 307
    assert received["redirect_uri"] == "https://pilot.example/api/auth/google/callback"


def test_direct_api_deployments_keep_their_existing_callback_path():
    response = client_with_prefix("").get("/auth/google")
    query = parse_qs(urlsplit(response.headers["location"]).query)
    assert query["redirect_uri"] == ["https://app.internal/auth/google/callback"]
    assert "Path=/auth" in response.headers["set-cookie"]
