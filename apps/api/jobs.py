"""Bounded, durable local scheduling for project processing.

This is intentionally a small single-instance scheduler.  It provides the
operational guarantees the local deployment needs without introducing a queue
server: bounded admission, one active run per project, durable job records,
and immutable run directories.  A future distributed deployment can replace
only this module with a queue adapter because routes deal in ``Job`` records,
not executor details.
"""

import threading
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from klave_engine.common.config import Settings
from klave_engine.common.ids import short_uuid
from klave_engine.common.io import read_json, write_json
from klave_engine.common.logging import get_logger
from klave_engine.ingestion.manifest import ProcessingStatus, load_manifest, save_manifest
from klave_engine.pipeline import run_full_pipeline

from apps.api.events import BUS

logger = get_logger(__name__)

ACTIVE_STATES = {"queued", "running"}
JOBS_DIR_NAME = "jobs"
RUNS_DIR_NAME = "runs"
LATEST_JOB_FILENAME = "latest_job.json"
ACTIVE_RUN_FILENAME = "active_run.json"


class JobQueueFullError(Exception):
    """The local scheduler has reached its configured admission limit."""


@dataclass
class Job:
    project_id: str
    job_id: str
    run_id: str
    state: str = "queued"  # queued | running | processed | failed
    stage: str = "En cola"
    error: str | None = None
    entity_count: int = 0
    detection_count: int = 0
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    def to_json(self) -> dict[str, Any]:
        return {
            "project_id": self.project_id,
            "job_id": self.job_id,
            "run_id": self.run_id,
            "state": self.state,
            "stage": self.stage,
            "error": self.error,
            "entity_count": self.entity_count,
            "detection_count": self.detection_count,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
        }

    @classmethod
    def from_json(cls, value: dict[str, Any]) -> "Job":
        return cls(
            project_id=str(value["project_id"]),
            job_id=str(value["job_id"]),
            run_id=str(value["run_id"]),
            state=str(value.get("state", "failed")),
            stage=str(value.get("stage", "Desconocido")),
            error=value.get("error"),
            entity_count=int(value.get("entity_count", 0)),
            detection_count=int(value.get("detection_count", 0)),
            created_at=datetime.fromisoformat(str(value["created_at"])),
            updated_at=datetime.fromisoformat(str(value["updated_at"])),
        )


@dataclass
class JobStore:
    _jobs: dict[str, Job] = field(default_factory=dict)
    _lock: threading.Lock = field(default_factory=threading.Lock)
    _executor: ThreadPoolExecutor | None = None

    def get(self, project_id: str, root: Path, settings: Settings) -> Job | None:
        """Return the latest job, recovering interrupted work after restart."""
        with self._lock:
            cached = self._jobs.get(project_id)
        if cached is not None:
            return cached

        path = self._control_dir(root, settings) / LATEST_JOB_FILENAME
        if not path.exists():
            return None
        try:
            job = Job.from_json(read_json(path))
        except (KeyError, TypeError, ValueError):
            logger.warning("Ignoring invalid persisted job record at %s", path)
            return None
        if job.project_id != project_id:
            logger.warning("Ignoring mismatched persisted job record at %s", path)
            return None
        if job.state in ACTIVE_STATES:
            job.state = "failed"
            job.stage = "Interrumpido"
            job.error = "El servidor se reinició antes de terminar el procesamiento."
            job.updated_at = datetime.now(UTC)
            self._persist(job, root, settings)
        with self._lock:
            self._jobs[project_id] = job
        return job

    def enqueue(self, project_id: str, root: Path, settings: Settings) -> tuple[Job, bool]:
        """Schedule a run, or return the already-active run for idempotency."""
        existing = self.get(project_id, root, settings)
        if existing is not None and existing.state in ACTIVE_STATES:
            return existing, False

        with self._lock:
            active_count = sum(job.state in ACTIVE_STATES for job in self._jobs.values())
            capacity = max(1, settings.max_concurrent_jobs) + max(0, settings.max_queued_jobs)
            if active_count >= capacity:
                raise JobQueueFullError("Processing queue is at capacity")
            job = Job(
                project_id=project_id,
                job_id=short_uuid("job"),
                run_id=short_uuid("run"),
            )
            self._jobs[project_id] = job
            if self._executor is None:
                self._executor = ThreadPoolExecutor(
                    max_workers=max(1, settings.max_concurrent_jobs),
                    thread_name_prefix="klave-processing",
                )

        self._persist(job, root, settings)
        BUS.publish("job_updated", project_id=project_id, data=job.to_json())
        assert self._executor is not None
        self._executor.submit(self._run, job.project_id, root, settings)
        return job, True

    def _run(self, project_id: str, root: Path, settings: Settings) -> None:
        job = self._update(
            project_id, root, settings, state="running", stage="Procesando dibujo", error=None
        )
        if job is None:
            return
        control_dir = self._control_dir(root, settings)
        run_dir = control_dir / RUNS_DIR_NAME / job.run_id
        try:
            run_dir.mkdir(parents=True, exist_ok=False)
            result = run_full_pipeline(
                root,
                settings,
                artifact_dir=run_dir,
                reports_dir=run_dir / "reports",
            )
            # Publish exactly once, after every artifact/report has been
            # written. Readers resolve this atomically replaced pointer.
            write_json(
                control_dir / ACTIVE_RUN_FILENAME,
                {
                    "run_id": job.run_id,
                    "artifact_dir": str(run_dir.relative_to(control_dir)),
                    "reports_dir": str((run_dir / "reports").relative_to(control_dir)),
                    "published_at": datetime.now(UTC).isoformat(),
                },
            )
            # A full run incorporates the persisted costing inputs. Any older
            # derived report is no longer evidence-compatible with this run.
            (control_dir / "cost_report_override.json").unlink(missing_ok=True)
            BUS.publish("run_published", project_id=project_id, data={"run_id": job.run_id})
            self._update(
                project_id,
                root,
                settings,
                state="processed",
                stage="Completado",
                entity_count=len(result.entities),
                detection_count=len(result.detections),
            )
        except Exception:  # noqa: BLE001 - convert all pipeline failures into durable job state
            logger.exception("Processing failed for %s", project_id)
            self._mark_manifest_failed(root, settings)
            self._update(
                project_id,
                root,
                settings,
                state="failed",
                stage="Error",
                error="No se pudo procesar el dibujo. Revisa el archivo e inténtalo de nuevo.",
            )

    def _update(
        self, project_id: str, root: Path, settings: Settings, **fields: object
    ) -> Job | None:
        with self._lock:
            job = self._jobs.get(project_id)
            if job is None:
                return None
            for key, value in fields.items():
                setattr(job, key, value)
            job.updated_at = datetime.now(UTC)
        self._persist(job, root, settings)
        BUS.publish("job_updated", project_id=project_id, data=job.to_json())
        return job

    @staticmethod
    def _control_dir(root: Path, settings: Settings) -> Path:
        return root / settings.processed_dir_name

    def _persist(self, job: Job, root: Path, settings: Settings) -> None:
        control_dir = self._control_dir(root, settings)
        write_json(control_dir / JOBS_DIR_NAME / f"{job.job_id}.json", job.to_json())
        write_json(control_dir / LATEST_JOB_FILENAME, job.to_json())

    @staticmethod
    def _mark_manifest_failed(root: Path, settings: Settings) -> None:
        try:
            manifest = load_manifest(root, settings.processed_dir_name)
            manifest.processing_status = ProcessingStatus.failed
            save_manifest(manifest, settings.processed_dir_name)
        except Exception:  # noqa: BLE001 - preserve the original processing error
            logger.exception("Could not persist failed processing status for %s", root)


JOB_STORE = JobStore()
