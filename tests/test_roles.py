"""Quién puede cambiar qué: el catálogo es del administrador del taller; los
alias y los mapeos de variantes se agregan en revisión y se cambian o se
quitan con un administrador. Ver docs/superpowers/specs/2026-10-23-role-enforcement-design.md."""

import pytest
from fastapi import HTTPException
from starlette.requests import Request

from apps.api.auth import access


class Usuarios:
    """La base de usuarios en memoria: Admin administra el taller; en el proyecto
    de prueba Olga es propietaria, Ana editora y Beto lector."""

    last_known_has_users = True

    def __init__(self, pid: str = "obra"):
        self.pid = pid
        self.usuarios = {
            quien: {"user_id": quien, "name": quien.capitalize(), "status": "active",
                    "role": "admin" if quien == "admin" else "member", "workspace_id": "ws-a"}
            for quien in ("admin", "olga", "ana", "beto")
        }  # fmt: skip
        self.roles = {"olga": "owner", "ana": "editor", "beto": "viewer"}
        self.auditoria: list[dict] = []

    def has_users(self):
        return True

    def get_session_user(self, token):
        user = self.usuarios.get(token or "")
        return dict(user) if user else None

    def project_workspace_id(self, project_id):
        return "ws-a"

    def project_role(self, project_id, user_id):
        return self.roles.get(user_id) if project_id == self.pid else None

    def record_audit(self, **entry):
        self.auditoria.append(entry)


def peticion(user: dict | None) -> Request:
    return Request({"type": "http", "headers": [], "state": {"user": user}})


@pytest.fixture
def usuarios(monkeypatch):
    store = Usuarios()
    monkeypatch.setattr(access, "get_user_store", lambda _url: store)
    return store


def test_require_taller_admin_open_mode_passes():
    access.require_taller_admin(peticion(None))


def test_require_taller_admin_member_403(usuarios):
    with pytest.raises(HTTPException) as exc:
        access.require_taller_admin(peticion(usuarios.usuarios["ana"]))
    assert exc.value.status_code == 403
    assert exc.value.detail["error_type"] == "admin_required"
    assert exc.value.detail["message"] == access.CATALOG_ADMIN_MESSAGE


def test_require_taller_admin_admin_passes(usuarios):
    access.require_taller_admin(peticion(usuarios.usuarios["admin"]))


def test_is_taller_admin(usuarios):
    assert access.is_taller_admin(peticion(usuarios.usuarios["admin"])) is True
    assert access.is_taller_admin(peticion(usuarios.usuarios["olga"])) is False
    assert access.is_taller_admin(peticion(None)) is False


def test_viewer_project_role_matches_tablero(usuarios):
    assert access.viewer_project_role(peticion(usuarios.usuarios["admin"]), "obra") == "admin"
    assert access.viewer_project_role(peticion(usuarios.usuarios["ana"]), "obra") == "editor"
    assert access.viewer_project_role(peticion(usuarios.usuarios["beto"]), "otra") is None
    assert access.viewer_project_role(peticion(None), "obra") is None
