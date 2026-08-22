"""Sheet images and AI-assisted reading of a project's frames."""

from __future__ import annotations

import threading
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException
from fastapi.responses import FileResponse
from klave_engine.common.config import Settings
from klave_engine.llm.reader import anthropic_reader, credentials_available
from klave_engine.llm.service import (
    AiReads,
    load_ai_reads,
    render_frame_png,
    run_ai_reading,
    save_ai_reads,
)

from apps.api.dependencies import ProjectStore, get_settings, get_store
from apps.api.events import BUS, clean_actor

router = APIRouter(prefix="/projects")
_LOCK = threading.Lock()
_RUNNING: set[str] = set()


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


@router.get("/{project_id}/ai-reads")
def get_ai_reads(
    project_id: str,
    store: ProjectStore = Depends(get_store),
    settings: Settings = Depends(get_settings),
) -> dict:
    reads = load_ai_reads(_control_dir(store, project_id, settings))
    payload = reads.model_dump()
    payload["available"] = credentials_available()
    payload["running"] = project_id in _RUNNING
    payload["model"] = "claude-opus-5"
    return payload


@router.post("/{project_id}/ai-read", status_code=202)
def start_ai_read(
    project_id: str,
    x_actor: Annotated[str | None, Header()] = None,
    store: ProjectStore = Depends(get_store),
    settings: Settings = Depends(get_settings),
) -> dict:
    """Render every frame and read it with the model, in the background.
    Refuses honestly when no credentials are configured."""
    control_dir = _control_dir(store, project_id, settings)
    if not credentials_available():
        raise HTTPException(
            status_code=409,
            detail={
                "error_type": "ai_not_configured",
                "message": "La lectura con IA no está configurada en este servidor: falta "
                "ANTHROPIC_API_KEY (o un perfil de `ant auth login`).",
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
    save_ai_reads(control_dir, AiReads(status="running"))
    actor = clean_actor(x_actor)

    def job() -> None:
        try:
            reads = run_ai_reading(
                artifact_dir, control_dir, anthropic_reader(), run_id=artifact_dir.name
            )
            BUS.publish(
                "ai_read_finished",
                project_id,
                actor=actor,
                data={"status": reads.status, "readings": len(reads.readings)},
            )
        finally:
            with _LOCK:
                _RUNNING.discard(project_id)

    threading.Thread(target=job, name=f"ai-read-{project_id}", daemon=True).start()
    return {"project_id": project_id, "status": "running"}
