"""CSRF: mutations must come from our own browser origin."""

from klave_engine.common import config as config_module

from apps.api.auth import middleware


def test_origin_policy(monkeypatch):
    monkeypatch.setenv("KLAVE_WEB_ORIGIN", "https://app.taller.mx")
    monkeypatch.setenv("KLAVE_EXTRA_ORIGINS", "https://staging.taller.mx, https://x.mx/")
    config_module.get_settings.cache_clear()
    assert middleware.origin_allowed("https://app.taller.mx")
    assert middleware.origin_allowed("https://staging.taller.mx")
    assert middleware.origin_allowed("https://x.mx")
    assert middleware.origin_allowed("http://localhost:3000")  # local dev always
    assert middleware.origin_allowed(None)  # curl, tests: no cookie to forge with
    assert not middleware.origin_allowed("https://evil.example")
    config_module.get_settings.cache_clear()


def test_mutations_from_foreign_origins_are_refused(data_dir, monkeypatch):
    from fastapi.testclient import TestClient

    from apps.api.main import create_app

    monkeypatch.setenv("KLAVE_USERS_DATABASE_URL", "postgresql://nobody@127.0.0.1:1/none")
    config_module.get_settings.cache_clear()
    client = TestClient(create_app())
    foreign = client.post(
        "/auth/login",
        json={"email": "a@b.mx", "password": "x" * 8},
        headers={"Origin": "https://evil.example"},
    )
    assert foreign.status_code == 403
    assert foreign.json()["detail"]["error_type"] == "origin_not_allowed"
    # Same-origin browsers and non-browser clients reach the route itself.
    own = client.post(
        "/auth/login",
        json={"email": "a@b.mx", "password": "x" * 8},
        headers={"Origin": "http://localhost:3000"},
    )
    assert own.status_code != 403
    referer_only = client.post(
        "/auth/login",
        json={"email": "a@b.mx", "password": "x" * 8},
        headers={"Referer": "https://evil.example/login"},
    )
    assert referer_only.status_code == 403
    assert client.get("/health", headers={"Origin": "https://evil.example"}).status_code == 200
