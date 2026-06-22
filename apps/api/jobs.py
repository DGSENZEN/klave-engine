"""In-process job store for async project processing.

Single-workspace, local-first: a simple in-memory registry is enough to drive
the web UI's processing-progress screen. The background task runs the pipeline
and updates the job; the frontend polls ``GET /projects/{id}/status``.
"""

import threading
import traceback
from dataclasses import dataclass, field
from pathlib import Path

from klave_engine.common.config import Settings
from klave_engine.common.logging import get_logger
from klave_engine.pipeline import run_full_pipeline

logger = get_logger(__name__)


@dataclass
class Job:
    project_id: str
    state: str = "queued"  # queued | running | processed | failed
    stage: str = "En cola"
    error: str | None = None
    entity_count: int = 0
    detection_count: int = 0


@dataclass
class JobStore:
    _jobs: dict[str, Job] = field(default_factory=dict)
    _lock: threading.Lock = field(default_factory=threading.Lock)

    def get(self, project_id: str) -> Job | None:
        with self._lock:
            return self._jobs.get(project_id)

    def start(self, project_id: str) -> Job:
        with self._lock:
            job = Job(project_id=project_id, state="queued", stage="En cola")
            self._jobs[project_id] = job
            return job

    def _set(self, project_id: str, **fields: object) -> None:
        with self._lock:
            job = self._jobs.get(project_id)
            if job is None:
                return
            for key, value in fields.items():
                setattr(job, key, value)

    def run(self, project_id: str, root: Path, settings: Settings) -> None:
        """Execute the full pipeline, recording progress and any failure."""
        self._set(project_id, state="running", stage="Procesando dibujo")
        try:
            result = run_full_pipeline(root, settings)
            self._set(
                project_id,
                state="processed",
                stage="Completado",
                entity_count=len(result.entities),
                detection_count=len(result.detections),
            )
        except Exception as exc:  # noqa: BLE001 - surface any failure to the UI
            logger.exception("Processing failed for %s", project_id)
            self._set(
                project_id,
                state="failed",
                stage="Error",
                error=f"{type(exc).__name__}: {exc}",
            )
            traceback.print_exc()


JOB_STORE = JobStore()
