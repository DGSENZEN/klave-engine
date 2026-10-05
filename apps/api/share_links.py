"""Las ligas para compartir: un proyecto, de sólo lectura, con caducidad.

Un supervisor o un socio abre la liga sin cuenta y ve el plano con sus
elementos y los generadores — nunca el dinero. El token es largo y aleatorio
(``secrets.token_urlsafe``), caduca, se revoca, y sólo abre el proyecto para
el que se emitió. Se guardan en ``data_dir/share_links.json``.
"""

from __future__ import annotations

import json
import secrets
import threading
from datetime import UTC, datetime, timedelta
from pathlib import Path

FILENAME = "share_links.json"
DEFAULT_DAYS = 14
MAX_DAYS = 90
_LOCK = threading.Lock()


def _path(data_dir: Path) -> Path:
    return data_dir / FILENAME


def _read(data_dir: Path) -> dict[str, dict]:
    path = _path(data_dir)
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except ValueError:
        return {}


def _write(data_dir: Path, links: dict[str, dict]) -> None:
    path = _path(data_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(links, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(path)


def create_link(data_dir: Path, project_id: str, actor: str, days: int = DEFAULT_DAYS) -> dict:
    days = max(1, min(int(days), MAX_DAYS))
    now = datetime.now(UTC)
    token = secrets.token_urlsafe(24)
    entry = {
        "token": token, "project_id": project_id, "created_by": actor[:80],
        "created_at": now.isoformat(), "expires_at": (now + timedelta(days=days)).isoformat(),
        "revoked_at": None,
    }
    with _LOCK:
        links = _read(data_dir)
        links[token] = entry
        _write(data_dir, links)
    return entry


def list_links(data_dir: Path, project_id: str) -> list[dict]:
    now = datetime.now(UTC)
    return sorted(
        (
            {**e, "active": _active(e, now)}
            for e in _read(data_dir).values() if e.get("project_id") == project_id
        ),
        key=lambda e: e["created_at"], reverse=True,
    )


def revoke_link(data_dir: Path, project_id: str, token: str) -> bool:
    with _LOCK:
        links = _read(data_dir)
        entry = links.get(token)
        if entry is None or entry.get("project_id") != project_id:
            return False
        entry["revoked_at"] = datetime.now(UTC).isoformat()
        _write(data_dir, links)
    return True


def _active(entry: dict, now: datetime) -> bool:
    if entry.get("revoked_at"):
        return False
    try:
        return datetime.fromisoformat(entry["expires_at"]) > now
    except (KeyError, ValueError):
        return False


def resolve(data_dir: Path, token: str) -> str | None:
    """El proyecto de una liga vigente; None si no existe, caducó o se revocó."""
    if not token or len(token) < 20:
        return None
    entry = _read(data_dir).get(token)
    if entry is None or not _active(entry, datetime.now(UTC)):
        return None
    return str(entry["project_id"])
