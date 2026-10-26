"""La obra de ejemplo: una obra didáctica por persona, sobre la que corre el
recorrido guiado. Vive aparte de los datos del taller — su id basta para
reconocerla y apartarla en cualquier parte del sistema."""

from __future__ import annotations

from klave_engine.common.ids import slugify

SAMPLE_PREFIX = "obra_de_ejemplo"


def es_obra_de_ejemplo(project_id: str) -> bool:
    return project_id.startswith(SAMPLE_PREFIX)


def sample_project_id(workspace_id: str | None, user_id: str | None) -> str:
    """Sin cuentas (modo abierto) hay una sola; con cuentas, una por persona."""
    if not workspace_id and not user_id:
        return f"{SAMPLE_PREFIX}_local"
    workspace = slugify(workspace_id or "local")[:36] or "local"
    user = slugify(user_id or "local")[:36] or "local"
    return f"{SAMPLE_PREFIX}_{workspace}_{user}"
