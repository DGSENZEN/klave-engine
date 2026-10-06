"""La actividad de un proyecto, guardada: quién hizo qué y cuándo.

El bus de eventos vive en memoria y sirve a quien está conectado; para medir
un piloto («¿cuántas horas le tomó a la oficina?») hace falta lo que pasó,
después. Cada evento de proyecto se agrega a ``processed/actividad.jsonl``:
tipo, persona, hora y un detalle corto — nunca el dibujo. Escribir nunca
detiene una petición ni un proceso."""

from __future__ import annotations

import json
import threading
from datetime import UTC, datetime
from pathlib import Path

ACTIVIDAD_FILENAME = "actividad.jsonl"
_LOCK = threading.Lock()


def registrar(control_dir: Path, tipo: str, actor: str | None, datos: dict | None = None,
              at: str | None = None) -> None:
    try:
        registro = {"at": at or datetime.now(UTC).isoformat(), "tipo": tipo,
                    "actor": actor or "", "datos": _corto(datos or {})}
        control_dir.mkdir(parents=True, exist_ok=True)
        with _LOCK, (control_dir / ACTIVIDAD_FILENAME).open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(registro, ensure_ascii=False) + "\n")
    except Exception:  # noqa: BLE001 — medir nunca rompe nada
        pass


def leer(control_dir: Path) -> list[dict]:
    path = control_dir / ACTIVIDAD_FILENAME
    if not path.exists():
        return []
    out = []
    for line in path.read_text("utf-8").splitlines():
        try:
            out.append(json.loads(line))
        except ValueError:
            continue
    return out


def _corto(datos: dict) -> dict:
    """Sólo escalares cortos: la acción, el detalle, el formato, el estado."""
    out = {}
    for k, v in datos.items():
        if k in ("summary", "client_id"):
            continue
        if isinstance(v, (str, int, float, bool)) or v is None:
            out[k] = v[:200] if isinstance(v, str) else v
    return out
