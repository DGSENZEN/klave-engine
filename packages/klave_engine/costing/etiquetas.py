"""Las etiquetas: cada decisión de una persona en Revisión, guardada como
dato para el lector que aprende.

Spec «el lector que aprende» §6. Esta es la primera versión: lo que hoy
existe (confirmar, excluir, mapear una variante) con lo que el motor sabía
del elemento en ese momento. Nada las consume todavía; existen para que el
primer piloto ya produzca datos. Se escriben en ``labels.jsonl`` junto a las
revisiones del proyecto; nunca salen de ahí en esta versión.
"""

from __future__ import annotations

import json
from collections.abc import Iterable
from datetime import UTC, datetime
from pathlib import Path

LABELS_FILENAME = "labels.jsonl"
LABELS_VERSION = 1
# Lo que no se guarda de las propiedades de una detección: geometría y
# contornos (la etiqueta describe el elemento, no lo redibuja).
_SKIP = {"polygon", "points", "openings", "point", "coordinate"}


def _scalar_props(props: dict) -> dict:
    out = {}
    for key, value in (props or {}).items():
        if key in _SKIP:
            continue
        if isinstance(value, (str, int, float, bool)) or value is None:
            out[key] = value
    return out


def _detection_snapshot(detection: dict | None) -> dict:
    if not detection:
        return {}
    return {
        "type": detection.get("detection_type"),
        "family": detection.get("family"),
        "mark": detection.get("mark"),
        "label": detection.get("label"),
        "source": (detection.get("evidence") or {}).get("source"),
        "method": (detection.get("evidence") or {}).get("method"),
        "properties": _scalar_props(detection.get("properties") or {}),
    }


def append_labels(control_dir: Path, records: Iterable[dict]) -> int:
    """Añade registros al diario de etiquetas; devuelve cuántos escribió."""
    path = control_dir / LABELS_FILENAME
    path.parent.mkdir(parents=True, exist_ok=True)
    now = datetime.now(UTC).isoformat()
    count = 0
    with path.open("a", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(
                {"labels_version": LABELS_VERSION, "at": now, **record}, ensure_ascii=False
            ) + "\n")
            count += 1
    return count


def detection_labels(
    keys: list[str], verdict: str, actor: str, detections: list, note: str = "",
    meters_factor: float | None = None, action: str = "",
) -> list[dict]:
    """Una etiqueta por elemento revisado, con lo que el motor sabía de él:
    su identidad estable y su vector de rasgos (spec del lector §6)."""
    from klave_engine.costing.referencias import element_id
    from klave_engine.detection.features import FEATURES_VERSION, Contexto, features
    from klave_engine.detection.results import Detection

    dets = [d if isinstance(d, Detection) else Detection.model_validate(d) for d in detections]
    ctx = Contexto.de(dets, meters_factor)
    by_key: dict[str, Detection] = {}
    for d in dets:
        by_key.setdefault(d.display_label or d.detection_id, d)
        by_key.setdefault(d.detection_id, d)
    out = []
    for key in keys:
        det = by_key.get(key)
        record: dict = {
            "kind": "deteccion", "key": key, "verdict": verdict, "note": note[:300],
            "actor": actor, "action": action or verdict,
        }
        if det is not None:
            record.update({
                "element": _detection_snapshot(det.model_dump(mode="json")),
                "element_id": element_id(det, meters_factor),
                "features_version": FEATURES_VERSION,
                "features": features(det, ctx),
                "proposals": {"rule": det.family or det.detection_type.value},
            })
        out.append(record)
    return out


def mapping_label(
    variant_key: str, previous: dict | None, new: dict | None, actor: str, description: str
) -> dict:
    """Una corrección de mapeo: qué proponía el motor y qué decidió la persona."""
    def _brief(m: dict | None) -> dict | None:
        if not m:
            return None
        return {k: m.get(k) for k in ("status", "target_kind", "target_code", "clave", "score")}

    return {"kind": "mapeo", "key": variant_key, "description": description[:300],
            "proposed": _brief(previous), "verdict": _brief(new), "actor": actor}


def read_labels(control_dir: Path) -> list[dict]:
    path = control_dir / LABELS_FILENAME
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]
