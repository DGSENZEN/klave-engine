"""Sheet images and AI-assisted reading of a project's frames."""

from __future__ import annotations

import threading
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, Request, Response
from fastapi.responses import FileResponse
from klave_engine.common.config import Settings
from klave_engine.detection.frames import SheetFrame
from klave_engine.detection.results import Detection
from klave_engine.dxf.entities import NormalizedEntity
from klave_engine.llm.coverage import coverage_flags
from klave_engine.llm.evidencia import crop_from_frame_render, find_mark_region
from klave_engine.llm.reader import active_model, configured_reader, credentials_available
from klave_engine.llm.service import (
    AiReads,
    failed_codes,
    load_ai_reads,
    render_frame_png,
    run_ai_reading,
    save_ai_reads,
)

from apps.api.auth.common import rate_limit
from apps.api.dependencies import ProjectStore, get_settings, get_store
from apps.api.events import BUS, clean_actor

router = APIRouter(prefix="/projects")
_LOCK = threading.Lock()
_RUNNING: set[str] = set()
_CANCEL: dict[str, threading.Event] = {}


def _control_dir(store: ProjectStore, project_id: str, settings: Settings) -> Path:
    return store.get_root(project_id) / settings.processed_dir_name


@router.get("/{project_id}/renders/{code}.png")
def frame_render(
    project_id: str,
    code: str,
    store: ProjectStore = Depends(get_store),
    settings: Settings = Depends(get_settings),
) -> FileResponse:
    """The frame as an image: what the engineer (and the model) reads."""
    if not code.replace("-", "").replace("_", "").isalnum():
        raise HTTPException(status_code=404, detail={"error_type": "frame_not_found"})
    path = render_frame_png(
        store.artifact_root(project_id), _control_dir(store, project_id, settings), code
    )
    if path is None:
        raise HTTPException(status_code=404, detail={"error_type": "frame_not_found"})
    return FileResponse(path, media_type="image/png")


@router.get("/{project_id}/ai-reads/{code}/{mark}.png")
def ai_read_evidence(
    project_id: str,
    code: str,
    mark: str,
    store: ProjectStore = Depends(get_store),
    settings: Settings = Depends(get_settings),
) -> Response:
    """The crop of the sheet where this mark is written.

    This is what makes an AI reading checkable instead of merely plausible:
    the engineer confirms against the drawing's own ink, not against the
    model's account of itself."""
    if not code.replace("-", "").replace("_", "").isalnum():
        raise HTTPException(status_code=404, detail={"error_type": "frame_not_found"})
    if len(mark) > 40:
        raise HTTPException(status_code=404, detail={"error_type": "mark_not_found"})
    artifact_dir = store.artifact_root(project_id)
    control_dir = _control_dir(store, project_id, settings)
    frames = [SheetFrame.model_validate(f) for f in store.read_artifact(project_id, "frames.json")]
    frame = next((f for f in frames if f.code == code), None)
    if frame is None:
        raise HTTPException(status_code=404, detail={"error_type": "frame_not_found"})

    # What the reading claimed about this mark, so the crop can be chosen where
    # the mark and those values appear together.
    reads = load_ai_reads(control_dir)
    corroborating: list[str] = []
    for reading in reads.readings:
        if reading.frame_code != code:
            continue
        for element in reading.read.elements:
            if element.mark.strip().upper() == mark.strip().upper():
                corroborating = [
                    v for v in (element.section_cm, element.rebar, element.stirrups) if v
                ]
    entities = [
        NormalizedEntity.model_validate(e)
        for e in store.read_artifact(project_id, "normalized_entities.json")
    ]
    region = find_mark_region(entities, frame, mark, corroborating)
    if region is None:
        raise HTTPException(
            status_code=404,
            detail={
                "error_type": "mark_not_found",
                "message": f"«{mark}» no aparece escrito en la hoja {code}.",
            },
        )
    render = render_frame_png(artifact_dir, control_dir, code)
    png = crop_from_frame_render(render, frame, region) if render else None
    if png is None:
        raise HTTPException(status_code=404, detail={"error_type": "render_unavailable"})
    return Response(content=png, media_type="image/png")


@router.get("/{project_id}/ai-reads")
def get_ai_reads(
    project_id: str,
    store: ProjectStore = Depends(get_store),
    settings: Settings = Depends(get_settings),
) -> dict:
    reads = load_ai_reads(_control_dir(store, project_id, settings))
    payload = reads.model_dump()
    payload["available"] = credentials_available(settings.ai_provider)
    payload["running"] = project_id in _RUNNING
    payload["model"] = active_model(settings.ai_provider, settings.ai_model) or ""
    payload["cobertura"] = _cobertura(store, project_id, payload.get("readings") or [])
    # Which sheets a retry would ask for again: the page offers exactly those,
    # so a saturated provider never costs the sheets that did come back.
    payload["failed"] = failed_codes(reads)
    return payload


def _cobertura(store: ProjectStore, project_id: str, readings: list[dict]) -> list[dict]:
    """The coverage audit against the active run's detections; an absent or
    older artifact simply yields no flags."""
    if not readings:
        return []
    try:
        detections = [
            Detection.model_validate(d)
            for d in store.read_artifact(project_id, "detections.json")
        ]
        frames = [
            SheetFrame.model_validate(f)
            for f in store.read_artifact(project_id, "frames.json")
        ]
    except HTTPException:
        return []
    return [f.model_dump() for f in coverage_flags(readings, detections, frames)]


@router.post("/{project_id}/ai-read", status_code=202)
def start_ai_read(
    project_id: str,
    request: Request,
    only_failed: bool = False,
    x_actor: Annotated[str | None, Header()] = None,
    store: ProjectStore = Depends(get_store),
    settings: Settings = Depends(get_settings),
) -> dict:
    """Render every frame and read it with the model, in the background.
    Refuses honestly when no credentials are configured.

    ``only_failed=true`` resumes: the sheets already read are kept as they
    are and only the failures are asked for again."""
    rate_limit(request, "ai_read", max_attempts=10, window_seconds=3600.0)
    control_dir = _control_dir(store, project_id, settings)
    if not credentials_available(settings.ai_provider):
        raise HTTPException(
            status_code=409,
            detail={
                "error_type": "ai_not_configured",
                "message": "La lectura con IA no está activada en este servidor; pide a tu "
                "administrador que la configure.",
            },
        )
    artifact_dir = store.artifact_root(project_id)
    if not (artifact_dir / "normalized_entities.json").exists():
        raise HTTPException(
            status_code=409,
            detail={"error_type": "not_processed", "message": "Procesa el proyecto primero."},
        )
    with _LOCK:
        if project_id in _RUNNING:
            raise HTTPException(
                status_code=409,
                detail={"error_type": "ai_read_running", "message": "Ya hay una lectura en curso."},
            )
        _RUNNING.add(project_id)
        cancel = _CANCEL[project_id] = threading.Event()
    if not only_failed:
        save_ai_reads(control_dir, AiReads(status="running"))
    actor = clean_actor(x_actor)

    def job() -> None:
        try:
            reads = run_ai_reading(
                artifact_dir, control_dir,
                configured_reader(settings.ai_provider, settings.ai_model),
                run_id=artifact_dir.name,
                should_stop=cancel.is_set,
                model=active_model(settings.ai_provider, settings.ai_model) or "",
                only_failed=only_failed,
            )
            BUS.publish(
                "ai_read_finished",
                project_id,
                actor=actor,
                data={
                    "status": reads.status,
                    "readings": len(reads.readings),
                    "failed": len(failed_codes(reads)),
                },
            )
        finally:
            with _LOCK:
                _RUNNING.discard(project_id)
                _CANCEL.pop(project_id, None)

    threading.Thread(target=job, name=f"ai-read-{project_id}", daemon=True).start()
    return {"project_id": project_id, "status": "running"}


@router.post("/{project_id}/ai-read/cancel")
def cancel_ai_read(
    project_id: str,
    store: ProjectStore = Depends(get_store),
) -> dict:
    """Stop after the sheet being read; what was already read stays."""
    store.get_root(project_id)  # 404 for unknown projects
    with _LOCK:
        cancel = _CANCEL.get(project_id)
        if cancel is None:
            raise HTTPException(
                status_code=409,
                detail={"error_type": "ai_read_not_running", "message": "No hay lectura en curso."},
            )
        cancel.set()
    return {"project_id": project_id, "status": "cancelling"}
