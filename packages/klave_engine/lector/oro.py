"""El conjunto revisado por personas: figuras de un plano que alguien calificó
una por una — elemento o no —, propuestas o no por el lector. Es la vara con
que se mide cada versión (como el gold mide al motor); su proyecto nunca
entra al entrenamiento.

``python -m klave_engine.lector.oro capturar <proyecto> <nombre>`` lo toma de
las decisiones del proyecto (Revisión → Propuestas, con «calificar todas»);
``evals/lector/<nombre>.json`` guarda clave, rasgos y veredicto — sin
coordenadas ni nombres."""

from __future__ import annotations

import json
import sys
from pathlib import Path

from klave_engine.lector.modelo import Modelo, opaco
from klave_engine.lector.rasgos import vector

ORO = Path(__file__).resolve().parents[3] / "evals" / "lector"
ACCIONES = {"confirm_proposal": 1, "reject_proposal": 0}


def project_id(proyecto: Path) -> str:
    manifest = proyecto / "processed" / "project_manifest.json"
    if manifest.exists():
        return str(json.loads(manifest.read_text("utf-8")).get("project_id") or proyecto.name)
    return proyecto.name


def decisiones(proyecto: Path) -> dict[str, dict]:
    """La última decisión de una persona por propuesta."""
    from klave_engine.costing.etiquetas import read_labels

    out: dict[str, dict] = {}
    for lab in read_labels(proyecto / "processed"):
        if lab.get("kind") == "propuesta" and lab.get("action") in ACCIONES and lab.get("features"):
            out[str(lab["key"])] = {"key": lab["key"], "features": lab["features"],
                                    "y": ACCIONES[lab["action"]]}
    return out


def capturar(proyecto: Path, nombre: str, destino: Path = ORO) -> Path:
    items = sorted(decisiones(proyecto).values(), key=lambda i: i["key"])
    if not items:
        raise SystemExit("El proyecto no tiene figuras calificadas por una persona.")
    destino.mkdir(parents=True, exist_ok=True)
    path = destino / f"{nombre}.json"
    path.write_text(json.dumps({
        "nombre": nombre, "proyecto": opaco(project_id(proyecto)),
        "elementos": sum(i["y"] for i in items), "items": items,
    }, indent=1, ensure_ascii=False))
    return path


def cargar(destino: Path = ORO) -> list[dict]:
    return [json.loads(p.read_text("utf-8")) for p in sorted(destino.glob("*.json"))]


def evaluar(modelo: Modelo, oro: dict) -> dict:
    """Precisión y alcance al umbral del modelo, contra lo que dijo la gente."""
    propuestas = elementos = aciertos = 0
    for item in oro["items"]:
        sube = modelo.puntuar(vector(item["features"])) >= modelo.umbral
        propuestas += sube
        elementos += item["y"]
        aciertos += sube and item["y"] == 1
    return {
        "items": len(oro["items"]), "elementos": elementos, "propuestas": propuestas,
        "precision": round(aciertos / propuestas, 4) if propuestas else None,
        "alcance": round(aciertos / elementos, 4) if elementos else None,
    }


if __name__ == "__main__":
    if len(sys.argv) == 4 and sys.argv[1] == "capturar":
        print(capturar(Path(sys.argv[2]), sys.argv[3]))
    else:
        raise SystemExit("uso: python -m klave_engine.lector.oro capturar <proyecto> <nombre>")
