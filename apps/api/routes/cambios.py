"""Las revisiones de un proyecto (cada lectura guardada) y qué cambió entre
dos de ellas, por concepto y por elemento, con su libro de aditivas y
deductivas."""

from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException
from fastapi.responses import Response
from klave_engine.common.config import Settings
from klave_engine.common.ids import slugify
from klave_engine.common.io import read_json, write_json
from klave_engine.costing.cambios import Cambios, comparar
from klave_engine.costing.models import CostReport
from klave_engine.detection.results import Detection
from pydantic import BaseModel, Field

from apps.api.dependencies import ProjectStore, get_settings, get_store
from apps.api.events import clean_actor

router = APIRouter(prefix="/projects")

LABELS_FILE = "revisiones.json"


class EtiquetaBody(BaseModel):
    label: str = Field(min_length=1, max_length=60)


def _control(store: ProjectStore, settings: Settings, project_id: str) -> Path:
    return store.get_root(project_id) / settings.processed_dir_name


def _read(path: Path) -> dict | list | None:
    try:
        return read_json(path)
    except (OSError, ValueError):
        return None


def revisiones(store: ProjectStore, settings: Settings, project_id: str) -> list[dict]:
    """Cada lectura guardada del proyecto, de la más vieja a la más nueva."""
    control = _control(store, settings, project_id)
    labels = _read(control / LABELS_FILE) or {}
    active = store.active_run_id(project_id)
    out: list[dict] = []
    runs = control / "runs"
    for run in sorted(runs.iterdir()) if runs.is_dir() else []:
        if not (run / "detections.json").exists() or not (run / "cost_report.json").exists():
            continue
        engine = _read(run / "engine.json") or {}
        inputs = _read(run / "inputs.json")
        out.append({
            "run_id": run.name,
            "processed_at": (engine or {}).get("processed_at") or "",
            "engine": (engine or {}).get("fingerprint") or "",
            "inputs": (inputs or {}).get("files") if isinstance(inputs, dict) else None,
            "label": (labels or {}).get(run.name, "") if isinstance(labels, dict) else "",
            "active": run.name == active,
        })
    out.sort(key=lambda r: r["processed_at"] or r["run_id"])
    for i, r in enumerate(out):
        prev = out[i - 1] if i else None
        r["mismo_plano_que_anterior"] = (
            None if prev is None or prev["inputs"] is None or r["inputs"] is None
            else prev["inputs"] == r["inputs"]
        )
        r["misma_version_que_anterior"] = (
            None if prev is None or not prev["engine"] or not r["engine"]
            else prev["engine"] == r["engine"]
        )
        if not r["label"]:
            fecha = r["processed_at"][:10]
            r["label"] = f"Lectura del {fecha}" if fecha else r["run_id"]
    return out


@router.get("/{project_id}/revisiones")
def list_revisiones(
    project_id: str,
    store: ProjectStore = Depends(get_store),
    settings: Settings = Depends(get_settings),
) -> dict:
    return {"revisiones": revisiones(store, settings, project_id)}


@router.put("/{project_id}/revisiones/{run_id}")
def label_revision(
    project_id: str,
    run_id: str,
    body: EtiquetaBody,
    x_actor: Annotated[str | None, Header()] = None,
    store: ProjectStore = Depends(get_store),
    settings: Settings = Depends(get_settings),
) -> dict:
    """«Rev C», «Proyecto ejecutivo», «Anteproyecto»: el nombre que usa la obra."""
    if run_id not in {r["run_id"] for r in revisiones(store, settings, project_id)}:
        raise HTTPException(status_code=404, detail={"error_type": "revision_not_found"})
    control = _control(store, settings, project_id)
    labels = _read(control / LABELS_FILE)
    labels = labels if isinstance(labels, dict) else {}
    labels[run_id] = body.label.strip()
    write_json(control / LABELS_FILE, labels)
    clean_actor(x_actor)
    return {"run_id": run_id, "label": labels[run_id]}


def _cargar(
    store: ProjectStore, settings: Settings, project_id: str, run: dict
) -> tuple[list[Detection], CostReport]:
    control = _control(store, settings, project_id)
    folder = control / "runs" / run["run_id"]
    dets = [Detection.model_validate(d) for d in (read_json(folder / "detections.json") or [])]
    if run["active"]:
        # La lectura vigente con los precios de hoy (el recálculo del taller).
        report = CostReport.model_validate(store.read_artifact(project_id, "cost_report.json"))
    else:
        report = CostReport.model_validate(read_json(folder / "cost_report.json"))
    return dets, report


def calcular_cambios(
    store: ProjectStore, settings: Settings, project_id: str,
    antes: str | None, despues: str | None,
) -> tuple[Cambios, dict, dict]:
    revs = revisiones(store, settings, project_id)
    if len(revs) < 2:
        raise HTTPException(
            status_code=409,
            detail={"error_type": "one_revision",
                    "message": "Hace falta una segunda lectura: sube la revisión del plano."},
        )
    by_id = {r["run_id"]: r for r in revs}
    if despues is None:
        despues = next((r["run_id"] for r in revs if r["active"]), revs[-1]["run_id"])
    if antes is None:
        idx = [r["run_id"] for r in revs].index(despues) if despues in by_id else len(revs) - 1
        antes = revs[idx - 1]["run_id"] if idx > 0 else revs[0]["run_id"]
    if antes not in by_id or despues not in by_id:
        raise HTTPException(status_code=404, detail={"error_type": "revision_not_found"})
    if antes == despues:
        raise HTTPException(
            status_code=422,
            detail={"error_type": "same_revision", "message": "Elige dos lecturas distintas."},
        )
    ra, rd = by_id[antes], by_id[despues]
    da, rep_a = _cargar(store, settings, project_id, ra)
    dd, rep_d = _cargar(store, settings, project_id, rd)
    mismo = None if ra["inputs"] is None or rd["inputs"] is None else ra["inputs"] == rd["inputs"]
    misma = None if not ra["engine"] or not rd["engine"] else ra["engine"] == rd["engine"]
    return (
        comparar(antes, despues, da, dd, rep_a, rep_d, mismo_plano=mismo, misma_version=misma),
        ra, rd,
    )


@router.get("/{project_id}/cambios")
def get_cambios(
    project_id: str,
    antes: str | None = None,
    despues: str | None = None,
    store: ProjectStore = Depends(get_store),
    settings: Settings = Depends(get_settings),
) -> dict:
    cambios, ra, rd = calcular_cambios(store, settings, project_id, antes, despues)
    return {**cambios.model_dump(), "antes_label": ra["label"], "despues_label": rd["label"]}


@router.get("/{project_id}/cambios.xlsx")
def get_cambios_xlsx(
    project_id: str,
    antes: str | None = None,
    despues: str | None = None,
    store: ProjectStore = Depends(get_store),
    settings: Settings = Depends(get_settings),
) -> Response:
    from klave_engine.costing.exports import build_cambios_workbook

    cambios, ra, rd = calcular_cambios(store, settings, project_id, antes, despues)
    _da, rep_d = _cargar(store, settings, project_id, rd)
    manifest = store.get_manifest(project_id)
    content = build_cambios_workbook(
        cambios, rep_d, antes_label=ra["label"], despues_label=rd["label"],
        project_id=project_id, web_origin=settings.web_origin,
    )
    filename = f"aditivas_deductivas_{slugify(manifest.project_name)[:40]}.xlsx"
    return Response(
        content=content,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
