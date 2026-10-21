"""Bounded, durable local scheduling for project processing.

This is intentionally a small single-instance scheduler.  It provides the
operational guarantees the local deployment needs without introducing a queue
server: bounded admission, one active run per project, durable job records,
and immutable run directories.  A future distributed deployment can replace
only this module with a queue adapter because routes deal in ``Job`` records,
not executor details.
"""

import logging
import threading
import time
import traceback
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass, field, replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from klave_engine.common.bitacora import ErrorRegistrado, anotar_error, redactar
from klave_engine.common.config import Settings
from klave_engine.common.diagnostics import (
    DiagnosticContext,
    bind_context,
    emit_job_event,
    safe_log,
)
from klave_engine.common.errors import ConversionError
from klave_engine.common.ids import short_uuid
from klave_engine.common.io import read_json, write_json
from klave_engine.common.logging import get_logger, request_id_var
from klave_engine.costing.versions import snapshot_before_reprocess
from klave_engine.ingestion.manifest import ProcessingStatus, load_manifest, save_manifest
from klave_engine.pipeline import run_full_pipeline

from apps.api.events import BUS
from apps.api.retention import prune_project_storage

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
    diagnostic_context: DiagnosticContext = field(default_factory=DiagnosticContext)
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

    def to_record(self) -> dict[str, Any]:
        return {**self.to_json(), "diagnostic_context": asdict(self.diagnostic_context)}

    @classmethod
    def from_json(cls, value: dict[str, Any]) -> "Job":
        return cls(
            project_id=str(value["project_id"]),
            diagnostic_context=DiagnosticContext.from_record(value.get("diagnostic_context")),
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
            self._emit(
                job,
                "job_interrupted",
                outcome="failed",
                stage="interrupted",
                error_code="processing_interrupted",
            )
            self._record_failure(
                job,
                settings,
                "processing_interrupted",
                "interrupted",
                RuntimeError("Processing interrupted by server restart"),
            )
        with self._lock:
            self._jobs[project_id] = job
        return job

    def enqueue(
        self,
        project_id: str,
        root: Path,
        settings: Settings,
        *,
        context: DiagnosticContext | None = None,
    ) -> tuple[Job, bool]:
        """Schedule a run, or return the already-active run for idempotency."""
        self.get(project_id, root, settings)  # hydrate from disk before deciding

        with self._lock:
            # Decide under the lock: two concurrent enqueues for the same
            # project must produce one run, not two.
            current = self._jobs.get(project_id)
            if current is not None and current.state in ACTIVE_STATES:
                return current, False
            active_count = sum(job.state in ACTIVE_STATES for job in self._jobs.values())
            capacity = max(1, settings.max_concurrent_jobs) + max(0, settings.max_queued_jobs)
            if active_count >= capacity:
                raise JobQueueFullError("Processing queue is at capacity")
            job = Job(
                project_id=project_id,
                job_id=short_uuid("job"),
                run_id=short_uuid("run"),
            )
            job.diagnostic_context = replace(
                context or DiagnosticContext(),
                project_id=project_id,
                job_id=job.job_id,
                run_id=job.run_id,
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
        self._emit(job, "job_admitted", outcome="queued", stage="queued")
        self._executor.submit(self._run, job.project_id, root, settings)
        return job, True

    def repair_orphans(self, registry: dict[str, Path], settings: Settings) -> int:
        """At startup, mark every job a crash left mid-flight as failed, so
        the home never shows a "Procesando…" that no worker is working on.
        ``get`` does this lazily per project; this does it for all at once."""
        repaired = 0
        for project_id, root in registry.items():
            job = self.get(project_id, root, settings)
            if job is not None and job.error and job.stage == "Interrumpido":
                repaired += 1
        if repaired:
            logger.warning(
                "%d trabajos interrumpidos por un reinicio se marcaron fallidos", repaired
            )
        return repaired

    def _run(self, project_id: str, root: Path, settings: Settings) -> None:
        with self._lock:
            current = self._jobs.get(project_id)
        if current is None:
            return
        token = request_id_var.set(current.diagnostic_context.request_id or "-")
        try:
            with bind_context(current.diagnostic_context):
                self._run_bound(project_id, root, settings)
        finally:
            request_id_var.reset(token)

    def _run_bound(self, project_id: str, root: Path, settings: Settings) -> None:
        job = self._update(
            project_id, root, settings, state="running", stage="Procesando dibujo", error=None
        )
        if job is None:
            return
        started = time.perf_counter()
        stage = "processing"
        self._emit(job, "job_started", outcome="running", stage=stage)

        def progress(text: str) -> None:
            nonlocal stage
            self._update(project_id, root, settings, stage=text)
            mapped = (
                "converting"
                if text.startswith("Convirtiendo planos")
                else "reading"
                if text.startswith("Leyendo el dibujo")
                else "processing"
            )
            if mapped != stage:
                stage = mapped
                self._emit(
                    job,
                    "job_stage_changed",
                    outcome="running",
                    stage=stage,
                    duration_ms=(time.perf_counter() - started) * 1000,
                )

        control_dir = self._control_dir(root, settings)
        run_dir = control_dir / RUNS_DIR_NAME / job.run_id
        try:
            run_dir.mkdir(parents=True, exist_ok=False)
            from apps.api.tenancy import store_for_project

            result = run_full_pipeline(
                root,
                settings,
                artifact_dir=run_dir,
                reports_dir=run_dir / "reports",
                catalog_store=store_for_project(settings, project_id),
                progreso=progress,
            )
            # The presupuesto as it stood becomes an automatic version, so the
            # engineer can compare this corrida with the last one line by line.
            try:
                snapshot_before_reprocess(control_dir, None)
            except Exception:  # noqa: BLE001 — a failed snapshot must not block the run
                safe_log(
                    logger,
                    logging.WARNING,
                    "No se pudo guardar la versión previa de %s",
                    project_id,
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
            # The project just gained a run; old ones beyond the retention go.
            try:
                prune_project_storage(
                    control_dir, keep_runs=settings.keep_runs, keep_jobs=settings.keep_jobs
                )
            except Exception:  # noqa: BLE001 — cleanup must never fail a publish
                safe_log(
                    logger,
                    logging.WARNING,
                    "No se pudo depurar el almacenamiento de %s",
                    project_id,
                )
            self._update(
                project_id,
                root,
                settings,
                state="processed",
                stage="Completado",
                entity_count=len(result.entities),
                detection_count=len(result.detections),
            )
            # Ya publicado: con la persona viendo su proyecto, se dibujan los
            # croquis de los generadores para que la primera exportación no espere.
            self._emit(
                job,
                "job_completed",
                outcome="succeeded",
                stage="completed",
                duration_ms=(time.perf_counter() - started) * 1000,
            )
            try:
                from apps.api.routes.exports import precalentar_croquis

                precalentar_croquis(project_id, settings)
            except Exception:  # noqa: BLE001 — prewarming cannot invalidate a published run
                safe_log(logger, logging.WARNING, "Export prewarming failed for %s", project_id)
        except ConversionError as exc:
            # Ninguna hoja se pudo convertir: se dice por qué, no un error genérico.
            safe_log(
                logger,
                logging.WARNING,
                "Conversion failed for %s: %s",
                project_id,
                redactar(str(exc)),
            )
            self._mark_manifest_failed(root, settings)
            self._update(
                project_id,
                root,
                settings,
                state="failed",
                stage="Error",
                error=redactar(str(exc), 400),
            )
            self._record_failure(job, settings, "conversion_failed", stage, exc)
            self._emit(
                job,
                "job_failed",
                outcome="failed",
                stage=stage,
                error_code="conversion_failed",
                duration_ms=(time.perf_counter() - started) * 1000,
            )
        except Exception as exc:  # noqa: BLE001 — persist unexpected processing failures
            safe_log(logger, logging.ERROR, "Processing failed for %s", project_id)
            self._mark_manifest_failed(root, settings)
            self._update(
                project_id,
                root,
                settings,
                state="failed",
                stage="Error",
                error="No se pudo procesar el dibujo. Revisa el archivo e inténtalo de nuevo.",
            )
            self._record_failure(job, settings, "processing_failed", stage, exc)
            self._emit(
                job,
                "job_failed",
                outcome="failed",
                stage=stage,
                error_code="processing_failed",
                duration_ms=(time.perf_counter() - started) * 1000,
            )

    @staticmethod
    def _emit(job: Job, event: str, **fields: Any) -> None:
        try:
            emit_job_event(event, job.diagnostic_context, **fields)
        except Exception:  # noqa: BLE001 — includes broken diagnostic adapters
            pass

    @staticmethod
    def _record_failure(
        job: Job, settings: Settings, code: str, stage: str, exc: Exception
    ) -> None:
        context = job.diagnostic_context
        try:
            anotar_error(
                settings.data_dir,
                ErrorRegistrado(
                    ts=datetime.now(UTC).isoformat(),
                    request_id=context.request_id,
                    workspace=context.workspace_id,
                    user_id=context.user_id,
                    project_id=job.project_id,
                    job_id=job.job_id,
                    run_id=job.run_id,
                    ruta="/projects/{project_id}/process",
                    metodo="WORKER",
                    tipo=type(exc).__name__,
                    mensaje=redactar(str(exc)),
                    traza=redactar("".join(traceback.format_tb(exc.__traceback__)[-4:]), 2400),
                    operation="processing",
                    error_code=code,
                    stage=stage,
                ),
            )
        except Exception:  # noqa: BLE001 — failure reporting cannot replace durable job state
            pass

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
        write_json(control_dir / JOBS_DIR_NAME / f"{job.job_id}.json", job.to_record())
        write_json(control_dir / LATEST_JOB_FILENAME, job.to_record())

    @staticmethod
    def _mark_manifest_failed(root: Path, settings: Settings) -> None:
        try:
            manifest = load_manifest(root, settings.processed_dir_name)
            manifest.processing_status = ProcessingStatus.failed
            save_manifest(manifest, settings.processed_dir_name)
        except Exception:  # noqa: BLE001 - preserve the original processing error
            safe_log(logger, logging.ERROR, "Could not persist failed processing status")


JOB_STORE = JobStore()
