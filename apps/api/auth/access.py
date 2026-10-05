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
    if user["role"] == "admin":
        # Los administradores pasan cualquier rol, pero sólo en su taller.
        if store.project_workspace_id(project_id) != str(user["workspace_id"]):
            return 403, "forbidden_project", "Proyecto de otro taller."
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
