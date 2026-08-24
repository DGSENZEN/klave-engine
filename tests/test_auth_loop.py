"""The auth loop end to end: invitations, recovery, sessions, verification,
audit, and workspace scoping — against the throwaway users database with
the outbox mail provider (nothing leaves the machine)."""

import json
import re
from pathlib import Path

import pytest

psycopg = pytest.importorskip("psycopg")

from fastapi.testclient import TestClient  # noqa: E402
from klave_engine.common import config as config_module  # noqa: E402

import apps.api.auth.store as store_module  # noqa: E402
from apps.api.auth.cli import main as cli_main  # noqa: E402
from apps.api.auth.store import UserStore, get_user_store  # noqa: E402
from apps.api.mail import MailContent, MailResult  # noqa: E402

ADMIN_URL = "postgresql://klave_users:klave@127.0.0.1:5433/klave_users"
TEST_URL = "postgresql://klave_users:klave@127.0.0.1:5433/klave_users_test"
WEB = "http://web.test"

ALL_TABLES = (
    "audit_log, auth_tokens, invitations, project_workspace, project_access, "
    "sessions, users, workspaces"
)


def _users_db_running() -> bool:
    try:
        with psycopg.connect(ADMIN_URL, connect_timeout=2):
            return True
    except (psycopg.OperationalError, OSError):
        return False


pytestmark = pytest.mark.skipif(
    not _users_db_running(), reason="users-db is not running (make users-db-up)"
)


@pytest.fixture
def app(data_dir, monkeypatch):
    """Fresh API + empty users database + outbox mail, per test."""
    with psycopg.connect(ADMIN_URL, autocommit=True, connect_timeout=3) as conn:
        if not conn.execute(
            "SELECT 1 FROM pg_database WHERE datname = 'klave_users_test'"
        ).fetchone():
            conn.execute("CREATE DATABASE klave_users_test")
    # Make sure the schema exists, then wipe it so the default workspace is
    # bootstrapped again by the instance the app will use.
    with UserStore(TEST_URL)._connect() as conn:
        conn.execute(f"TRUNCATE {ALL_TABLES} CASCADE")
    monkeypatch.setenv("KLAVE_USERS_DATABASE_URL", TEST_URL)
    monkeypatch.setenv("KLAVE_MAIL_PROVIDER", "outbox")
    monkeypatch.setenv("KLAVE_WEB_ORIGIN", WEB)
    config_module.get_settings.cache_clear()
    monkeypatch.setattr(store_module, "_STORE", None)
    # The credential rate limiter is in-process; every test starts with a
    # clean window so registrations in one test never 429 the next.
    import apps.api.auth.common as common_module

    monkeypatch.setattr(common_module, "_rate_buckets", {})
    from apps.api.main import create_app

    application = create_app()
    yield application
    config_module.get_settings.cache_clear()


def store() -> UserStore:
    instance = get_user_store(TEST_URL)
    instance._has_users_cache = None  # bypass the 5 s protected-mode cache
    return instance


def bootstrap_admin(app) -> TestClient:
    client = TestClient(app)
    created = client.post(
        "/auth/register",
        json={"email": "jefa@taller.mx", "name": "Jefa", "password": "secreta-123"},
    )
    assert created.status_code == 201 and created.json()["role"] == "admin"
    store()
    return client


def outbox_links(data_dir: Path, path_prefix: str) -> list[str]:
    links: list[str] = []
    for file in sorted((data_dir / "outbox").glob("*.json")):
        text = json.loads(file.read_text())["text"]
        links += re.findall(rf"{re.escape(WEB)}{re.escape(path_prefix)}[^\s]+", text)
    return links


def token_of(link: str) -> str:
    return link.split("token=", 1)[1]


# ----------------------------------------------------------------- invitations

def test_invitation_lifecycle(app, data_dir):
    admin = bootstrap_admin(app)
    created = admin.post(
        "/auth/invitations", json={"email": "Ana@Taller.MX", "role": "member"}
    )
    assert created.status_code == 201, created.text
    body = created.json()
    assert body["email"] == "ana@taller.mx" and body["state"] == "open"
    assert body["delivered"] is False and body["mail_enabled"] is False  # outbox is honest
    link = body["link"]
    assert link.startswith(f"{WEB}/invitacion?token=")
    assert outbox_links(data_dir, "/invitacion") == [link]

    anonymous = TestClient(app)
    info = anonymous.get(f"/auth/invitations/by-token/{token_of(link)}")
    assert info.status_code == 200
    assert info.json()["state"] == "open" and info.json()["inviter_name"] == "Jefa"

    accepted = anonymous.post(
        f"/auth/invitations/by-token/{token_of(link)}/accept",
        json={"name": "Ana", "password": "otra-secreta-99"},
    )
    assert accepted.status_code == 201, accepted.text
    user = accepted.json()
    assert user["status"] == "active" and user["role"] == "member"
    assert user["email_verified"] is True  # the inbox proved the address
    assert anonymous.get("/projects").status_code == 200  # signed in by accepting

    # Closed invitations cannot be accepted twice.
    again = anonymous.post(
        f"/auth/invitations/by-token/{token_of(link)}/accept",
        json={"name": "Ana", "password": "otra-secreta-99"},
    )
    assert again.status_code == 410

    listed = admin.get("/auth/invitations").json()["invitations"]
    assert listed[0]["state"] == "accepted"
    actions = [e["action"] for e in admin.get("/auth/audit").json()["entries"]]
    assert "invitation_accepted" in actions and "invitation_created" in actions

    # Existing accounts are not invitable; share the project instead.
    duplicate = admin.post("/auth/invitations", json={"email": "ana@taller.mx"})
    assert duplicate.status_code == 409


def test_invitation_revoke_and_resend(app):
    admin = bootstrap_admin(app)
    first = admin.post("/auth/invitations", json={"email": "luis@taller.mx"}).json()
    resent = admin.post(f"/auth/invitations/{first['invite_id']}/resend")
    assert resent.status_code == 200
    new_token = token_of(resent.json()["link"])
    anonymous = TestClient(app)
    # The old token died with the resend; the new one is live.
    assert anonymous.get(f"/auth/invitations/by-token/{token_of(first['link'])}").status_code == 404
    assert anonymous.get(f"/auth/invitations/by-token/{new_token}").json()["state"] == "open"

    assert admin.delete(f"/auth/invitations/{first['invite_id']}").status_code == 200
    assert anonymous.get(f"/auth/invitations/by-token/{new_token}").json()["state"] == "revoked"
    blocked = anonymous.post(
        f"/auth/invitations/by-token/{new_token}/accept",
        json={"name": "Luis", "password": "clave-segura-1"},
    )
    assert blocked.status_code == 410
    # A revoked invitation stays revoked; a fresh one must be created instead.
    assert admin.post(f"/auth/invitations/{first['invite_id']}/resend").status_code == 404


def test_invitation_grants_apply_on_accept(app):
    bootstrap_admin(app)
    users = store()
    workspace_id = str(users.default_workspace()["workspace_id"])
    invite, token = users.create_invitation(
        workspace_id=workspace_id, email="eli@taller.mx", role="member",
        project_grants=[{"project_id": "proj_a", "role": "editor"}], invited_by=None,
    )
    invite = users.get_invitation_by_token(token)
    user = users.accept_invitation(invite, name="Eli", password="clave-segura-1")
    assert users.project_role("proj_a", str(user["user_id"])) == "editor"
    assert users.get_invitation_by_token(token)["state"] == "accepted"
    with pytest.raises(ValueError):
        users.accept_invitation(invite, name="Eli", password="clave-segura-1")


# -------------------------------------------------------------------- recovery

def test_recovery_by_admin_link(app):
    admin = bootstrap_admin(app)
    member = TestClient(app)
    member.post(
        "/auth/register",
        json={"email": "ana@taller.mx", "name": "Ana", "password": "olvidada-123"},
    )
    ana = store().get_by_email("ana@taller.mx")
    admin.put(f"/auth/users/{ana['user_id']}/status", json={"status": "active"})
    member.post("/auth/login", json={"email": "ana@taller.mx", "password": "olvidada-123"})
    assert member.get("/projects").status_code == 200

    # Without a mail provider, the forgot-password endpoint says so instead of
    # pretending, and issues nothing.
    recover = TestClient(app).post("/auth/recover", json={"email": "ana@taller.mx"})
    assert recover.status_code == 200 and recover.json()["mail_enabled"] is False

    issued = admin.post(f"/auth/users/{ana['user_id']}/recovery-link")
    assert issued.status_code == 200
    token = token_of(issued.json()["link"])

    fresh = TestClient(app)
    info = fresh.get(f"/auth/reset/{token}").json()
    assert info["valid"] is True
    assert info["email"].startswith("an") and "@taller.mx" in info["email"]
    done = fresh.post(f"/auth/reset/{token}", json={"password": "nueva-clave-456"})
    assert done.status_code == 200
    assert fresh.get("/projects").status_code == 200  # signed in after reset
    assert member.get("/projects").status_code == 401  # old session revoked
    spent = fresh.post(f"/auth/reset/{token}", json={"password": "otra-clave-larga-7"})
    assert spent.status_code == 410  # the link only works once
    login = TestClient(app).post(
        "/auth/login", json={"email": "ana@taller.mx", "password": "nueva-clave-456"}
    )
    assert login.status_code == 200
    actions = [e["action"] for e in admin.get("/auth/audit").json()["entries"]]
    assert "recovery_link_issued" in actions and "password_reset" in actions


def test_recovery_by_mail_when_provider_configured(app, monkeypatch):
    """With a real provider the emailed link works; enumeration stays blind."""
    sent: list[tuple[str, MailContent]] = []

    class FakeMailer:
        enabled = True
        provider = "smtp"

        def send(self, to, content):
            sent.append((to, content))
            return MailResult(delivered=True, provider="smtp")

    import apps.api.auth.recovery as recovery_module

    monkeypatch.setattr(recovery_module, "get_mailer", lambda settings: FakeMailer())
    bootstrap_admin(app)
    anonymous = TestClient(app)
    unknown = anonymous.post("/auth/recover", json={"email": "nadie@taller.mx"})
    known = anonymous.post("/auth/recover", json={"email": "jefa@taller.mx"})
    assert unknown.json() == known.json() == {"ok": True, "mail_enabled": True}
    resets = [m for m in sent if m[1].subject.startswith("Restablece")]
    assert len(resets) == 1 and resets[0][0] == "jefa@taller.mx"
    link = re.search(rf"{WEB}/restablecer\?token=\S+", resets[0][1].text).group(0)
    done = anonymous.post(f"/auth/reset/{token_of(link)}", json={"password": "clave-nueva-789"})
    assert done.status_code == 200
    assert anonymous.get("/auth/session").json()["user"]["email"] == "jefa@taller.mx"


def test_email_verification_from_outbox(app, data_dir):
    admin = bootstrap_admin(app)
    assert admin.get("/auth/session").json()["user"]["email_verified"] is False
    links = outbox_links(data_dir, "/verificar")
    assert len(links) == 1
    confirmed = TestClient(app).post(f"/auth/verify/{token_of(links[0])}")
    assert confirmed.status_code == 200 and confirmed.json()["changed"] is False
    assert admin.get("/auth/session").json()["user"]["email_verified"] is True
    # Re-sending for a verified address is a no-op, not a new token.
    assert admin.post("/auth/verify/send").json().get("already_verified") is True


# -------------------------------------------------------------------- sessions

def test_sessions_list_revoke_and_remember(app):
    admin = bootstrap_admin(app)
    phone = TestClient(app, headers={"user-agent": "KlaveMobile/1.0"})
    phone.post(
        "/auth/login",
        json={"email": "jefa@taller.mx", "password": "secreta-123", "remember": True},
    )
    sessions = admin.get("/auth/sessions").json()["sessions"]
    assert len(sessions) == 2
    current = next(s for s in sessions if s["current"])
    other = next(s for s in sessions if not s["current"])
    assert current["remember"] is False and other["remember"] is True
    assert other["user_agent"] == "KlaveMobile/1.0"

    assert admin.delete(f"/auth/sessions/{other['session_id']}").status_code == 200
    assert phone.get("/projects").status_code == 401
    assert admin.get("/projects").status_code == 200

    phone.post("/auth/login", json={"email": "jefa@taller.mx", "password": "secreta-123"})
    closed = admin.post("/auth/logout-all").json()
    assert closed["sessions_revoked"] == 1
    assert admin.get("/projects").status_code == 200  # the current session stays
    assert phone.get("/projects").status_code == 401


def test_password_change_keeps_current_session(app):
    admin = bootstrap_admin(app)
    other = TestClient(app)
    other.post("/auth/login", json={"email": "jefa@taller.mx", "password": "secreta-123"})
    changed = admin.post(
        "/auth/password", json={"current_password": "secreta-123", "new_password": "otra-clave-456"}
    )
    assert changed.status_code == 200 and changed.json()["sessions_revoked"] == 1
    assert admin.get("/projects").status_code == 200
    assert other.get("/projects").status_code == 401


# ------------------------------------------------------ admin loop guards

def test_admin_guards_and_profile(app):
    admin = bootstrap_admin(app)
    me = admin.get("/auth/session").json()["user"]
    demote = admin.put(f"/auth/users/{me['user_id']}/role", json={"role": "member"})
    assert demote.status_code == 422
    assert (
        admin.put(f"/auth/users/{me['user_id']}/status", json={"status": "disabled"}).status_code
        == 422
    )
    renamed = admin.put("/auth/me", json={"name": "Jefa Torres"})
    assert renamed.status_code == 200 and renamed.json()["name"] == "Jefa Torres"
    profile = admin.get("/auth/me").json()
    assert profile["workspace"]["slug"] == "taller" and profile["has_password"] is True
    # Google-only accounts must set a password before unlinking; password
    # accounts without Google have nothing to unlink either.
    assert admin.post("/auth/google/unlink").status_code == 422


# ------------------------------------------------------------ workspaces

def test_workspace_scoping_and_cli_bootstrap(app, capsys):
    admin = bootstrap_admin(app)
    users = store()
    users.register_project("proj_taller", str(users.default_workspace()["workspace_id"]))

    assert cli_main(["create-workspace", "otro", "Otro taller"]) == 0
    assert cli_main(["invite-admin", "otro", "jefe@otro.mx"]) == 0
    link = re.search(rf"{WEB}/invitacion\?token=\S+", capsys.readouterr().out).group(0)
    otro = TestClient(app)
    joined = otro.post(
        f"/auth/invitations/by-token/{token_of(link)}/accept",
        json={"name": "Jefe", "password": "clave-otro-123"},
    )
    assert joined.status_code == 201 and joined.json()["role"] == "admin"
    assert otro.get("/auth/session").json()["workspace"]["slug"] == "otro"

    # Each admin sees only their own taller's people and activity.
    assert {u["email"] for u in admin.get("/auth/users").json()["users"]} == {"jefa@taller.mx"}
    assert {u["email"] for u in otro.get("/auth/users").json()["users"]} == {"jefe@otro.mx"}
    otro_audit = otro.get("/auth/audit").json()["entries"]
    assert all(e["detail"].get("email") != "jefa@taller.mx" for e in otro_audit)

    # Admin powers stop at the workspace boundary (middleware, before routing).
    assert otro.get("/projects/proj_taller").status_code == 403
    assert admin.get("/projects/proj_taller").status_code == 404  # own taller, not on disk
    jefe = users.get_by_email("jefe@otro.mx")
    cross = admin.put(f"/auth/users/{jefe['user_id']}/role", json={"role": "member"})
    assert cross.status_code == 404
    assert cli_main(["create-workspace", "otro", "Duplicado"]) == 1


def test_weak_passwords_are_refused_with_the_reason():
    from apps.api.auth.passwords import password_problem

    assert password_problem("corta1234") is not None  # 9 chars
    assert "más usadas" in (password_problem("1234567890") or "")
    assert "repetidos" in (password_problem("aaaaaaaaaaaa") or "")
    assert "correo" in (password_problem("ana.lopez-2026", "ana.lopez@taller.mx") or "")
    assert password_problem("mole-poblano-42", "ana@taller.mx") is None
