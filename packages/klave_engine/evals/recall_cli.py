"""`python -m klave_engine.evals.recall_cli` — medir y preparar conteos.

    plantilla <project_id>   escribe evals/conteos/<id>.json para llenar a mano
    medir [<drawing_id>]     mide el recall contra los conteos ya llenados
"""

from __future__ import annotations

import json
import sys

from klave_engine.common.config import get_settings
from klave_engine.costing.models import CostReport
from klave_engine.detection.results import Detection
from klave_engine.evals.recall import (
    CONTEOS_DIR,
    ConteoDeObra,
    ReporteRecall,
    medir,
    plantilla_de_conteo,
)


def _artefactos(project_id: str) -> tuple[list[Detection], CostReport | None]:
    settings = get_settings()
    raiz = settings.data_dir / "uploads" / project_id
    control = raiz / settings.processed_dir_name
    activo = control / "active_run.json"
    if not activo.exists():
        raise SystemExit(f"{project_id}: no tiene una corrida publicada.")
    corrida = control / "runs" / json.loads(activo.read_text())["run_id"]
    detections = [
        Detection.model_validate(d)
        for d in json.loads((corrida / "detections.json").read_text())
    ]
    reporte = None
    for candidato in (control / "cost_report_override.json", corrida / "cost_report.json"):
        if candidato.exists():
            reporte = CostReport.model_validate(json.loads(candidato.read_text()))
            break
    return detections, reporte


def _imprimir(reporte: ReporteRecall) -> None:
    print(f"\n{reporte.drawing_id} — contó {reporte.contado_por or '—'}")
    cabecera = (
        f"{'familia':16} {'dibujados':>9} {'detectados':>10} {'recall':>7}"
        f"  {'IC 95%':>13}  importe"
    )
    print(cabecera)
    for f in sorted(reporte.familias, key=lambda x: (x.recall, -x.importe)):
        ic = f"{f.intervalo[0]:.2f}–{f.intervalo[1]:.2f}"
        importe = f"${f.importe:,.0f}" if f.importe else "—"
        aviso = "  ← revisar" if f.recall < 0.85 else ""
        print(
            f"{f.familia:16} {f.dibujados:9} {f.detectados:10} {f.recall:7.2f}  {ic:>13}  "
            f"{importe:>12}{aviso}"
        )
    print(f"\nrecall global (por pieza): {reporte.recall_global:.2f}")
    print(f"recall ponderado por dinero: {reporte.recall_ponderado:.2f}")
    if reporte.dinero_no_visto:
        print(f"dinero que el motor no vio, aprox: ${reporte.dinero_no_visto:,.0f}")


def main(argv: list[str]) -> int:
    if len(argv) < 2 or argv[1] not in ("plantilla", "medir"):
        print(__doc__)
        return 2

    CONTEOS_DIR.mkdir(parents=True, exist_ok=True)

    if argv[1] == "plantilla":
        if len(argv) < 3:
            print("falta el project_id")
            return 2
        project_id = argv[2]
        detections, _ = _artefactos(project_id)
        familias = sorted({d.family for d in detections if d.family})
        plantilla = plantilla_de_conteo(project_id, familias)
        destino = CONTEOS_DIR / f"{project_id}.json"
        destino.write_text(
            json.dumps(plantilla.a_json(), ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        print(f"escrito {destino}")
        print(
            "Llénalo contando sobre el plano y corre: "
            f"uv run python -m klave_engine.evals.recall_cli medir {project_id}"
        )
        return 0

    objetivo = argv[2] if len(argv) > 2 else None
    archivos = sorted(CONTEOS_DIR.glob("*.json"))
    if objetivo:
        archivos = [a for a in archivos if a.stem == objetivo]
    if not archivos:
        print(
            "No hay conteos que medir. Genera uno con:\n"
            "  uv run python -m klave_engine.evals.recall_cli plantilla <project_id>"
        )
        return 1

    fallo = False
    for archivo in archivos:
        conteo = ConteoDeObra.desde_json(archivo)
        if not any(c.dibujados for c in conteo.conteos):
            print(f"{archivo.name}: sin contar todavía (todos en cero).")
            continue
        detections, reporte_costos = _artefactos(conteo.drawing_id)
        reporte = medir(conteo, detections, reporte_costos)
        _imprimir(reporte)
        if reporte.recall_ponderado < 0.85:
            fallo = True
    return 1 if fallo else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
