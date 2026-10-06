"""Entrenar el lector (fuera de línea): ``uv run --group lector python -m
klave_engine.lector.entrenar <proyecto> <proyecto>… [--promover]``.

Cada proyecto es una carpeta ya procesada (con ``processed/``). Los ejemplos:
cada detección estructural dentro de la ventana de tamaño de los candidatos
es «elemento»; cada candidato, «no es elemento» — los veredictos de las
reglas. Lo que una persona decidió pesa más: una propuesta confirmada o una
detección confirmada es elemento, una propuesta descartada o una detección
excluida no lo es, y reemplazan el veredicto de la regla.

La evaluación deja un proyecto fuera cada vez; el umbral es el más bajo con
el que, sumando esas predicciones, nueve de cada diez propuestas son
elementos. Una versión nueva sólo queda activa si en ningún proyecto baja
más de un punto la precisión de la activa. El modelo guarda umbrales y
conteos; nunca nombres, coordenadas ni texto."""

from __future__ import annotations

import hashlib
import importlib
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

from klave_engine.lector.modelo import ACTIVO, MODELOS, Modelo
from klave_engine.lector.rasgos import NOMBRES, en_ventana, vector

ESTRUCTURALES = {"castillo", "columna", "trabe", "contratrabe", "dala", "cerramiento",
                 "zapata", "pilote", "muro", "muro_concreto", "losa"}
PRECISION_OBJETIVO = 0.90
MAX_POR_HOJA = 25
TOLERANCIA = 0.01


def _opaco(nombre: str) -> str:
    return hashlib.sha1(nombre.encode()).hexdigest()[:10]


def ejemplos(proyecto: Path) -> list[tuple[list[float | None], int]]:
    """(vector, 1 elemento / 0 no) de un proyecto procesado."""
    from klave_engine.costing.etiquetas import read_labels
    from klave_engine.detection.features import Contexto, features
    from klave_engine.detection.results import Detection
    from klave_engine.dxf.units import DrawingUnits

    p = proyecto / "processed"
    dets = [Detection.model_validate(d) for d in json.loads((p / "detections.json").read_text())]
    factor = None
    if (p / "drawing_units.json").exists():
        unidades = (p / "drawing_units.json").read_text()
        factor = DrawingUnits.model_validate_json(unidades).to_meters()
    ctx = Contexto.de(dets, factor)
    humanos: list[tuple[list[float | None], int]] = []
    revisadas: set[str] = set()
    for lab in read_labels(p):
        f = lab.get("features")
        if not f:
            continue
        accion = lab.get("action")
        if accion in ("confirm_proposal", "confirmed"):
            humanos.append((vector(f), 1))
        elif accion in ("reject_proposal", "excluded"):
            humanos.append((vector(f), 0))
        else:
            continue
        revisadas.add(str(lab.get("key") or ""))
    out = list(humanos)
    for d in dets:
        if d.family not in ESTRUCTURALES or (d.display_label or d.detection_id) in revisadas:
            continue
        f = features(d, ctx)
        if en_ventana(f):
            out.append((vector(f), 1))
    cpath = p / "candidates.jsonl"
    if cpath.exists():
        for line in cpath.read_text("utf-8").splitlines():
            if line:
                out.append((vector(json.loads(line)["features"]), 0))
    return out


def _sk():
    return importlib.import_module("sklearn.ensemble").HistGradientBoostingClassifier


def _matriz(filas):
    import numpy as np

    return np.array([[np.nan if v is None else v for v in x] for x, _ in filas], dtype=float)


def _ajustar(filas):
    import numpy as np

    clf = _sk()(max_iter=200, random_state=0)
    clf.fit(_matriz(filas), np.array([y for _, y in filas]))
    return clf


def exportar(clf, version: str, umbral: float) -> dict:
    """Los árboles de scikit-learn, como listas de números."""
    arboles = []
    for (pred,) in clf._predictors:
        arboles.append([
            [float(n["value"]), int(n["feature_idx"]), float(n["num_threshold"]),
             bool(n["missing_go_to_left"]), int(n["left"]), int(n["right"]), bool(n["is_leaf"])]
            for n in pred.nodes
        ])
    return {"version": version, "rasgos": list(NOMBRES),
            "base": float(clf._baseline_prediction.ravel()[0]), "arboles": arboles,
            "umbral": umbral, "max_por_hoja": MAX_POR_HOJA}


def _umbral(puntos: list[tuple[float, int]]) -> float:
    """El más bajo con precisión ≥ objetivo sobre todo lo que queda arriba."""
    orden = sorted(puntos, key=lambda t: -t[0])
    mejor, buenos = 1.0, 0
    for i, (score, y) in enumerate(orden, start=1):
        buenos += y
        if buenos / i >= PRECISION_OBJETIVO:
            mejor = score
    return mejor


def evaluar(datos: dict[str, list]) -> tuple[float, dict]:
    """Uno fuera cada vez: umbral común y, por proyecto, precisión y alcance."""
    import numpy as np

    puntos: dict[str, list[tuple[float, int]]] = {}
    for fuera in datos:
        resto = [f for k, filas in datos.items() if k != fuera for f in filas]
        if not datos[fuera] or len({y for _, y in resto}) < 2:
            continue
        clf = _ajustar(resto)
        proba = clf.predict_proba(_matriz(datos[fuera]))[:, 1]
        puntos[fuera] = [(float(s), y) for s, (_, y) in zip(proba, datos[fuera], strict=True)]
    umbral = _umbral([p for ps in puntos.values() for p in ps])
    informe = {}
    for k, ps in puntos.items():
        arriba = [y for s, y in ps if s >= umbral]
        positivos = sum(y for _, y in ps)
        informe[k] = {
            "ejemplos": len(ps), "elementos": positivos, "propuestas": len(arriba),
            "precision": round(float(np.mean(arriba)), 4) if arriba else None,
            "alcance": round(sum(arriba) / positivos, 4) if positivos else None,
        }
    return umbral, informe


def puede_promoverse(nuevo: dict, activo: dict) -> tuple[bool, list[str]]:
    razones = []
    for k, prev in activo.items():
        act = nuevo.get(k)
        if act is None or prev.get("precision") is None:
            continue
        if act.get("precision") is None or act["precision"] < prev["precision"] - TOLERANCIA:
            razones.append(f"{k}: precisión {act.get('precision')} < {prev['precision']}")
    return not razones, razones


def main(argv: list[str]) -> int:
    promover = "--promover" in argv
    proyectos = [Path(a) for a in argv if not a.startswith("--")]
    datos = {_opaco(p.name): ejemplos(p) for p in proyectos}
    umbral, informe = evaluar(datos)
    version = "m-" + datetime.now(UTC).strftime("%Y%m%d-%H%M")
    carpeta = MODELOS / version
    carpeta.mkdir(parents=True, exist_ok=True)
    clf = _ajustar([f for filas in datos.values() for f in filas])
    (carpeta / "modelo.json").write_text(json.dumps(exportar(clf, version, umbral)))
    manifiesto = {"version": version, "umbral": umbral,
                  "precision_objetivo": PRECISION_OBJETIVO,
                  "ejemplos": {k: {"total": len(v), "elementos": sum(y for _, y in v)}
                               for k, v in datos.items()},
                  "evaluacion_uno_fuera": informe}
    (carpeta / "informe.json").write_text(json.dumps(manifiesto, indent=2, ensure_ascii=False))
    print(json.dumps(manifiesto, indent=2, ensure_ascii=False))
    if promover:
        activo = Modelo.activo()
        previo = {}
        if activo is not None:
            previo = json.loads((MODELOS / activo.version / "informe.json").read_text())[
                "evaluacion_uno_fuera"]
        ok, razones = puede_promoverse(informe, previo)
        if not ok:
            print("No se promueve:", "; ".join(razones))
            return 1
        ACTIVO.write_text(version + "\n")
        print("Activo:", version)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
