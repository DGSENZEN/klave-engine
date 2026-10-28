"""La regla de acceso a un proyecto, en un solo lugar.

El middleware la aplica a todo lo que vive bajo ``/projects/...``. Hay rutas
fuera de ese prefijo que reciben un proyecto en el cuerpo o en la consulta
(el copiloto, los alias del catálogo con recálculo): ésas la llaman con
``require_project_role``. Antes no la llamaban, y una cuenta de un taller
podía leer o mover el presupuesto de otro.
"""

from __future__ import annotations

from typing import Any

from fastapi import HTTPException, Request
from klave_engine.common.config import get_settings

from apps.api.auth.store import ROLE_RANK, get_user_store


def project_access_problem(
    store: Any, user: dict, project_id: str, required: str
) -> tuple[int, str, str] | None:
    """None si ``user`` tiene ``required`` sobre el proyecto; si no, el
    (estado, tipo de error, mensaje) con que se niega."""
    # A stale grant must never open a project belonging to another taller.
    if store.project_workspace_id(project_id) != str(user["workspace_id"]):
        return 403, "forbidden_project", "Proyecto de otro taller."
    if user["role"] == "admin":
        return None
    role = store.project_role(project_id, str(user["user_id"]))
    if role is None or ROLE_RANK[role] < ROLE_RANK[required]:
        return 403, "forbidden_project", "No tienes acceso suficiente a este proyecto."
    return None


def require_project_role(request: Request, project_id: str, required: str = "viewer") -> None:
    """Para rutas fuera de /projects que tocan un proyecto. En modo local sin
    cuentas (el middleware dejó ``user`` en None) no hay a quién negar."""
    if not project_id:
        return
    user = getattr(request.state, "user", None)
    if user is None:
        return
    store = get_user_store(get_settings().users_database_url)
    problem = project_access_problem(store, user, project_id, required)
    if problem is not None:
        status, error_type, message = problem
        raise HTTPException(
            status_code=status, detail={"error_type": error_type, "message": message}
        )


CATALOG_ADMIN_MESSAGE = "Esta operación del catálogo requiere un administrador del taller."


def is_taller_admin(request: Request) -> bool:
    """¿Quien llama administra su taller? Falso en modo local sin cuentas:
    quien necesite dejar pasar ese modo lo pregunta aparte."""
    user = getattr(request.state, "user", None)
    return user is not None and user.get("role") == "admin"


def require_taller_admin(request: Request, message: str = CATALOG_ADMIN_MESSAGE) -> None:
    """Lo que sólo decide un administrador del taller. En modo local sin
    cuentas no hay a quién negar."""
    user = getattr(request.state, "user", None)
    if user is not None and user.get("role") != "admin":
        raise HTTPException(
            status_code=403, detail={"error_type": "admin_required", "message": message}
        )


def viewer_project_role(request: Request, project_id: str) -> str | None:
    """El rol del que mira: «admin» del taller, o su rol en el proyecto.

    En modo abierto no hay cuentas y el rol es None — el frontend lo lee
    como «todos pueden», la misma libertad local-first de siempre."""
    user = getattr(request.state, "user", None)
    if user is None:
        return None
    if user.get("role") == "admin":
        return "admin"
    try:
        store = get_user_store(get_settings().users_database_url)
        return store.project_role(project_id, str(user["user_id"]))
    except Exception:  # noqa: BLE001 — sin base de usuarios, sin veredicto
        return None
