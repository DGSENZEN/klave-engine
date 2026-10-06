"""Entrenar el lector (fuera de línea): ``klave train-reader [--promover]`` o
``uv run --group lector python -m klave_engine.lector.entrenar [<proyecto>…]``.

Sin proyectos, toma todos los procesados bajo la carpeta de datos, menos los
que forman el conjunto revisado por personas (``lector.oro``).

**Los ejemplos y su peso.** Una decisión de una persona pesa 5: propuesta
confirmada, detección confirmada o reasignada (es un elemento, de otra
familia) — elemento; propuesta descartada o detección excluida — no.
Una detección que la regla aceptó pesa 1. Una figura que ninguna regla tomó
y nadie revisó pesa 0.3 como «no»: no es un «no» — entre ellas están justo los
elementos que el lector debe encontrar —, es un «probablemente no».

**La evaluación** deja un proyecto fuera cada vez; con esas predicciones se
fija el umbral (el más bajo con nueve de cada diez propuestas siendo
elementos, contando como «no» lo no revisado: una cota pesimista) y se
guardan los pliegues, para que cada proyecto se califique con el modelo que
no lo vio. **Promover** exige que ningún proyecto baje más de un punto de
precisión y que, en cada conjunto revisado por personas, la precisión no baje
más de un punto ni el alcance más de dos. El modelo guarda umbrales, conteos
y hashes de proyecto; nunca nombres, coordenadas ni texto."""

from __future__ import annotations

import importlib
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

from klave_engine.detection.features import FEATURES_VERSION
from klave_engine.lector import oro as oro_mod
from klave_engine.lector.modelo import ACTIVO, MODELOS, Modelo, opaco
from klave_engine.lector.rasgos import NOMBRES, en_ventana, vector

ESTRUCTURALES = {"castillo", "columna", "trabe", "contratrabe", "dala", "cerramiento",
                 "zapata", "pilote", "muro", "muro_concreto", "losa"}
PRECISION_OBJETIVO = 0.90
MAX_POR_HOJA = 25
TOLERANCIA = 0.01
TOLERANCIA_ALCANCE = 0.02
PESO_PERSONA, PESO_REGLA, PESO_SIN_REVISAR = 5.0, 1.0, 0.3

Fila = tuple[list[float | None], int, float]


def artefactos(proyecto: Path) -> Path:
    """La corrida publicada del proyecto (o ``processed/`` si no hay corridas)."""
    control = proyecto / "processed"
    activo = control / "active_run.json"
    if activo.exists():
        carpeta = control / json.loads(activo.read_text("utf-8")).get("artifact_dir", "")
        if (carpeta / "detections.json").exists():
            return carpeta
    return control


def ejemplos(proyecto: Path) -> list[Fila]:
    """(vector, 1 elemento / 0 no, peso) de un proyecto procesado."""
    from klave_engine.costing.etiquetas import read_labels
    from klave_engine.detection.features import Contexto, features
    from klave_engine.detection.results import Detection
    from klave_engine.dxf.units import DrawingUnits
    from klave_engine.lector.propuestas import clave

    p = artefactos(proyecto)
    dets = [Detection.model_validate(d) for d in json.loads((p / "detections.json").read_text())]
    factor = None
    if (p / "drawing_units.json").exists():
        unidades = (p / "drawing_units.json").read_text()
        factor = DrawingUnits.model_validate_json(unidades).to_meters()
    ctx = Contexto.de(dets, factor)
    out: list[Fila] = []
    revisadas: set[str] = set()
    for lab in read_labels(proyecto / "processed"):
        f = lab.get("features")
        accion = lab.get("action")
        if not f or accion not in ("confirm_proposal", "confirmed", "reassign",
                                   "reject_proposal", "excluded"):
            continue
        y = 1 if accion in ("confirm_proposal", "confirmed", "reassign") else 0
        out.append((vector(f), y, PESO_PERSONA))
        revisadas.add(str(lab.get("key") or ""))
    for d in dets:
        if d.family not in ESTRUCTURALES or (d.display_label or d.detection_id) in revisadas:
            continue
        f = features(d, ctx)
        if en_ventana(f):
            out.append((vector(f), 1, PESO_REGLA))
    cpath = p / "candidates.jsonl"
    if cpath.exists():
        for line in cpath.read_text("utf-8").splitlines():
            if not line:
                continue
            cand = json.loads(line)
            if clave(cand, factor) not in revisadas:
                out.append((vector(cand["features"]), 0, PESO_SIN_REVISAR))
    return out


def dibujos(proyecto: Path) -> list[str]:
    """Los planos del proyecto, como sha256 recortado (nunca su nombre)."""
    path = artefactos(proyecto) / "inputs.json"
    if not path.exists():
        return []
    return sorted({h[:16] for h in json.loads(path.read_text("utf-8")).get("files", {}).values()})


def descubrir(data_dir: Path) -> list[Path]:
    """Cada proyecto procesado bajo la carpeta de datos que tenga candidatos."""
    raices = [data_dir / "uploads", data_dir / "projects"]
    return sorted(
        r for base in raices if base.exists() for r in base.iterdir()
        if r.is_dir() and (artefactos(r) / "candidates.jsonl").exists()
    )


def _sk():
    return importlib.import_module("sklearn.ensemble").HistGradientBoostingClassifier


def _matriz(filas):
    import numpy as np

    return np.array([[np.nan if v is None else v for v in f[0]] for f in filas], dtype=float)


def _ajustar(filas):
    import numpy as np

    clf = _sk()(max_iter=120, max_leaf_nodes=15, random_state=0)
    pesos = np.array([f[2] if len(f) > 2 else 1.0 for f in filas])
    clf.fit(_matriz(filas), np.array([f[1] for f in filas]), sample_weight=pesos)
    return clf


def _arboles(clf) -> dict:
    return {
        "base": float(clf._baseline_prediction.ravel()[0]),
        "arboles": [
            [[float(n["value"]), int(n["feature_idx"]), float(n["num_threshold"]),
              bool(n["missing_go_to_left"]), int(n["left"]), int(n["right"]), bool(n["is_leaf"])]
             for n in pred.nodes]
            for (pred,) in clf._predictors
        ],
    }


def exportar(
    clf, version: str, umbral: float, pliegues: dict | None = None,
    planos: dict[str, list[str]] | None = None,
) -> dict:
    """Los árboles de scikit-learn, como listas de números."""
    return {"version": version, "rasgos": list(NOMBRES), "features_version": FEATURES_VERSION,
            "completo": _arboles(clf),
            "pliegues": {k: _arboles(c) for k, c in (pliegues or {}).items()},
            "dibujos": planos or {},
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


def evaluar(datos: dict[str, list]) -> tuple[float, dict, dict]:
    """Uno fuera cada vez: umbral común, por proyecto precisión y alcance, y
    los pliegues (el modelo que no vio cada proyecto)."""
    import numpy as np

    puntos: dict[str, list[tuple[float, int]]] = {}
    pliegues = {}
    for fuera in datos:
        resto = [f for k, filas in datos.items() if k != fuera for f in filas]
        if not datos[fuera] or len({f[1] for f in resto}) < 2:
            continue
        clf = _ajustar(resto)
        pliegues[fuera] = clf
        proba = clf.predict_proba(_matriz(datos[fuera]))[:, 1]
        puntos[fuera] = [(float(s), f[1]) for s, f in zip(proba, datos[fuera], strict=True)]
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
    return umbral, informe, pliegues


def puede_promoverse(
    nuevo: dict, activo: dict, oro_nuevo: dict | None = None, oro_activo: dict | None = None,
) -> tuple[bool, list[str]]:
    razones = []
    for k, prev in activo.items():
        act = nuevo.get(k)
        if act is None or prev.get("precision") is None:
            continue
        if act.get("precision") is None or act["precision"] < prev["precision"] - TOLERANCIA:
            razones.append(f"proyecto {k}: precisión {act.get('precision')} < {prev['precision']}")
    for nombre, prev in (oro_activo or {}).items():
        act = (oro_nuevo or {}).get(nombre) or {}
        for metrica, tol in (("precision", TOLERANCIA), ("alcance", TOLERANCIA_ALCANCE)):
            if prev.get(metrica) is None:
                continue
            if act.get(metrica) is None or act[metrica] < prev[metrica] - tol:
                razones.append(f"revisado «{nombre}»: {metrica} {act.get(metrica)} "
                               f"< {prev[metrica]}")
    return not razones, razones


def entrenar(proyectos: list[Path], promover: bool = False, salida=print) -> int:
    conjuntos = oro_mod.cargar()
    excluidos = {o["proyecto"] for o in conjuntos}
    datos = {}
    planos: dict[str, list[str]] = {}
    for p in proyectos:
        k = opaco(oro_mod.project_id(p))
        if k in excluidos:
            salida(f"{p.name}: conjunto revisado por personas — no entra al entrenamiento")
            continue
        datos[k] = ejemplos(p)
        planos[k] = dibujos(p)
    if len(datos) < 2:
        salida("Hacen falta al menos dos proyectos con candidatos para entrenar y evaluar.")
        return 1
    umbral, informe, pliegues = evaluar(datos)
    version = "m-" + datetime.now(UTC).strftime("%Y%m%d-%H%M")
    carpeta = MODELOS / version
    carpeta.mkdir(parents=True, exist_ok=True)
    clf = _ajustar([f for filas in datos.values() for f in filas])
    modelo = exportar(clf, version, umbral, pliegues, planos)
    (carpeta / "modelo.json").write_text(json.dumps(modelo))
    nuevo = Modelo.cargar(carpeta)
    oro_nuevo = {o["nombre"]: oro_mod.evaluar(nuevo, o) for o in conjuntos}
    manifiesto = {
        "version": version, "umbral": umbral, "precision_objetivo": PRECISION_OBJETIVO,
        "pesos": {"persona": PESO_PERSONA, "regla": PESO_REGLA, "sin_revisar": PESO_SIN_REVISAR},
        "ejemplos": {k: {"total": len(v), "elementos": sum(f[1] for f in v),
                         "decisiones": sum(1 for f in v if f[2] == PESO_PERSONA)}
                     for k, v in datos.items()},
        "evaluacion_uno_fuera": informe, "revisado_por_personas": oro_nuevo,
    }
    (carpeta / "informe.json").write_text(json.dumps(manifiesto, indent=2, ensure_ascii=False))
    salida(json.dumps(manifiesto, indent=2, ensure_ascii=False))
    if promover:
        activo = Modelo.activo()
        previo, oro_previo = {}, {}
        if activo is not None:
            previo = json.loads((MODELOS / activo.version / "informe.json").read_text())[
                "evaluacion_uno_fuera"]
            oro_previo = {o["nombre"]: oro_mod.evaluar(activo, o) for o in conjuntos}
        ok, razones = puede_promoverse(informe, previo, oro_nuevo, oro_previo)
        if not ok:
            salida("No se promueve: " + "; ".join(razones))
            return 1
        ACTIVO.write_text(version + "\n")
        salida(f"Activo: {version}")
    return 0


def main(argv: list[str]) -> int:
    from klave_engine.common.config import get_settings

    proyectos = [Path(a) for a in argv if not a.startswith("--")]
    return entrenar(proyectos or descubrir(get_settings().data_dir), "--promover" in argv)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
