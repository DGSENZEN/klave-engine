"""Who may call each route that writes. ``tests/test_route_policy.py`` walks
every mutating route of the app and fails on any with no declared policy.

Policies:
- ``project``: under /projects/{project_id}/…, enforced by the middleware.
- ``catalog_admin``: under /catalog, enforced by ``catalog_write_rule``.
- ``workspace_admin``: /workspace writes, admin of the taller.
- ``self``: the caller's own account, or a token they hold.
- ``project_in_body``: outside /projects, the route calls ``require_project_role``.
- ``shared_mapping``: aliases and variant mappings (``auth.shared_mappings``).
- ``exempt``: named, with its reason.
"""

from __future__ import annotations

from typing import Literal

from apps.api.routes.catalog_rules import CATALOG_EXEMPT, SHARED_MAPPING_ROUTES

Policy = Literal[
    "project", "catalog_admin", "workspace_admin", "self", "project_in_body",
    "shared_mapping", "exempt",
]  # fmt: skip

# (METHOD, route path) → (policy, why). Everything a prefix rule can't decide.
ROUTE_POLICY_EXCEPTIONS: dict[tuple[str, str], tuple[Policy, str]] = {
    # Accounts: the caller's own, or a token they were handed.
    ("POST", "/auth/register"): ("self", "crea la cuenta de quien llama"),
    ("POST", "/auth/login"): ("self", "abre la sesión de quien llama"),
    ("POST", "/auth/logout"): ("self", "cierra la sesión de quien llama"),
    ("POST", "/auth/logout-all"): ("self", "cierra todas las sesiones de quien llama"),
    ("POST", "/auth/recover"): ("self", "pide un enlace al propio correo"),
    ("POST", "/auth/reset/{token}"): ("self", "el token es la autorización"),
    ("POST", "/auth/verify/send"): ("self", "verifica el propio correo"),
    ("POST", "/auth/verify/{token}"): ("self", "el token es la autorización"),
    ("POST", "/auth/email"): ("self", "cambia el propio correo"),
    ("PUT", "/auth/me"): ("self", "cambia el propio nombre"),
    ("PUT", "/auth/me/recorrido"): ("self", "el progreso propio del recorrido"),
    ("DELETE", "/auth/me/recorrido"): ("self", "reinicia el recorrido propio"),
    ("POST", "/auth/password"): ("self", "cambia la propia contraseña"),
    ("DELETE", "/auth/sessions/{session_id}"): ("self", "cierra una sesión propia"),
    ("POST", "/auth/google/unlink"): ("self", "desvincula la propia cuenta de Google"),
    ("POST", "/auth/invitations/by-token/{token}/accept"): (
        "self", "el token de la invitación es la autorización",
    ),
    # Team management: require_admin inside each route.
    ("PUT", "/auth/users/{user_id}/status"): ("workspace_admin", "require_admin"),
    ("PUT", "/auth/users/{user_id}/role"): ("workspace_admin", "require_admin"),
    ("POST", "/auth/users/{user_id}/recovery-link"): ("workspace_admin", "require_admin"),
    ("POST", "/auth/invitations"): ("workspace_admin", "require_admin"),
    ("DELETE", "/auth/invitations/{invite_id}"): ("workspace_admin", "require_admin"),
    ("POST", "/auth/invitations/{invite_id}/resend"): ("workspace_admin", "require_admin"),
    # New projects belong to whoever creates them.
    ("POST", "/projects"): ("exempt", "importa una carpeta del servidor; 404 en producción"),
    ("POST", "/projects/upload"): ("exempt", "crea un proyecto nuevo de quien sube"),
    ("POST", "/projects/demo"): ("exempt", "crea la obra de ejemplo propia"),
    ("POST", "/disciplines/preview"): ("exempt", "clasifica nombres de archivo, no guarda"),
    # Outside /projects but about one: they call require_project_role.
    ("POST", "/copilot/aplicar"): ("project_in_body", "editor; admin si escribe el catálogo"),
    ("POST", "/copilot/ask"): ("project_in_body", "lector del proyecto que pregunta"),
}


def policy_for(method: str, path: str) -> Policy | None:
    key = (method, path)
    if key in SHARED_MAPPING_ROUTES:
        return "shared_mapping"
    if key in CATALOG_EXEMPT:
        return "exempt"
    if key in ROUTE_POLICY_EXCEPTIONS:
        return ROUTE_POLICY_EXCEPTIONS[key][0]
    if path.startswith("/catalog/") or path == "/catalog":
        return "catalog_admin"
    if path.startswith("/projects/{project_id}"):
        return "project"
    if path.startswith("/workspace/") or path == "/workspace":
        return "workspace_admin"
    return None
