"""The recovery client must remain usable after authenticating over loopback."""

import httpx

from deploy import recovery_scenario as scenario


def test_login_client_lifecycle_and_secure_cookie_forwarding(monkeypatch):
    original_client = httpx.Client

    def response(request):
        if request.url.path == "/auth/login":
            return httpx.Response(
                200,
                json={
                    "user_id": "synthetic-user",
                    "email": "admin@pilot.example",
                    "name": "Pilot administrator",
                    "role": "admin",
                    "status": "active",
                    "picture": None,
                    "email_verified": False,
                    "pending_email": None,
                    "has_password": True,
                    "has_google": False,
                },
                headers={"set-cookie": "klave_session=synthetic; Secure; HttpOnly; Path=/"},
            )
        assert request.headers["Cookie"] == "klave_session=synthetic"
        return httpx.Response(200, json={"mode": "protected"})

    monkeypatch.setattr(
        scenario.httpx,
        "Client",
        lambda **kwargs: original_client(
            **kwargs,
            transport=httpx.MockTransport(response),
        ),
    )
    with scenario.login("http://127.0.0.1:18000", "admin@pilot.example") as client:
        assert client.get("/auth/session").json() == {"mode": "protected"}
    assert client.is_closed
