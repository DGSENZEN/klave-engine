"""Storage retention: a project keeps its recent history, not every byte ever.

Each reprocess writes a full run (~100 MB on a real set) plus croquis per
run and a job record; nineteen test runs cost 2 GB. After every publish the
project prunes itself:

- ``runs/``: the active run always stays; beyond it the newest ``keep_runs``
  survive, the rest go (their ``reports/`` go with them).
- ``croquis/<run_id>``: only for runs that still exist.
- ``jobs/``: the newest ``keep_jobs`` records.

Presupuesto versions are self-contained snapshots and are never touched.
"""

from __future__ import annotations

import shutil
from pathlib import Path

from klave_engine.common.io import read_json
from klave_engine.common.logging import get_logger, log_stage

logger = get_logger(__name__)

RUNS_DIR = "runs"
CROQUIS_DIR = "croquis"
JOBS_DIR = "jobs"


def _active_run_id(control_dir: Path) -> str | None:
    pointer = control_dir / "active_run.json"
    if not pointer.exists():
        return None
    try:
        return str(read_json(pointer).get("run_id") or "") or None
    except (OSError, ValueError):
        return None


def prune_project_storage(
    control_dir: Path, *, keep_runs: int = 3, keep_jobs: int = 10
) -> dict[str, int]:
    """Prune one project's control dir; returns what was removed."""
    removed = {"runs": 0, "croquis": 0, "jobs": 0}
    active = _active_run_id(control_dir)

    runs_dir = control_dir / RUNS_DIR
    if runs_dir.is_dir():
        runs = sorted(
            (p for p in runs_dir.iterdir() if p.is_dir()),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )
        keep = {p.name for p in runs[: max(keep_runs, 1)]}
        if active:
            keep.add(active)
        for run in runs:
            if run.name not in keep:
                shutil.rmtree(run, ignore_errors=True)
                removed["runs"] += 1

    croquis_dir = control_dir / CROQUIS_DIR
    if croquis_dir.is_dir():
        alive = {p.name for p in (control_dir / RUNS_DIR).iterdir()} if runs_dir.is_dir() else set()
        for per_run in croquis_dir.iterdir():
            if per_run.is_dir() and per_run.name not in alive:
                shutil.rmtree(per_run, ignore_errors=True)
                removed["croquis"] += 1

    jobs_dir = control_dir / JOBS_DIR
    if jobs_dir.is_dir():
        jobs = sorted(
            (p for p in jobs_dir.iterdir() if p.is_file()),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )
        for job in jobs[max(keep_jobs, 1):]:
            job.unlink(missing_ok=True)
            removed["jobs"] += 1

    if any(removed.values()):
        log_stage(logger, "project_storage_pruned", control_dir=str(control_dir), **removed)
    return removed
