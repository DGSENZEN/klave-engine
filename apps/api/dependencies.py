"""API dependencies: settings and the project registry/artifact store.

Routes orchestrate; this store locates projects and reads generated artifacts
rather than recomputing them on every request.
"""

import threading
from pathlib import Path
from typing import Any

from fastapi import Depends, HTTPException
from klave_engine.common.config import Settings, get_settings
from klave_engine.common.io import read_json, write_json
from klave_engine.ingestion.manifest import ProjectManifest, load_manifest

__all__ = ["ProjectStore", "get_settings", "get_store", "project_recompute_lock"]

# Serializes the read-check-write of a project's costing state so concurrent
# recomputes (parameter edits, review changes) cannot interleave.
_RECOMPUTE_LOCKS: dict[str, threading.Lock] = {}
_RECOMPUTE_LOCKS_GUARD = threading.Lock()


def project_recompute_lock(project_id: str) -> threading.Lock:
    with _RECOMPUTE_LOCKS_GUARD:
        return _RECOMPUTE_LOCKS.setdefault(project_id, threading.Lock())

REGISTRY_FILENAME = "projects_registry.json"

# The registry is a read-modify-write JSON file; concurrent registrations
# from parallel uploads must not drop each other's entries.
_REGISTRY_LOCK = threading.Lock()


class ProjectStore:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.registry_path = settings.data_dir / REGISTRY_FILENAME

    def _registry(self) -> dict[str, str]:
        if not self.registry_path.exists():
            return {}
        return read_json(self.registry_path)

    def register(self, project_id: str, root_path: Path) -> None:
        root_path = self.managed_root(root_path)
        with _REGISTRY_LOCK:
            registry = self._registry()
            registry[project_id] = str(root_path)
            write_json(self.registry_path, registry)

    def unregister(self, project_id: str) -> None:
        """Remove a project from the registry; its files stay on disk."""
        with _REGISTRY_LOCK:
            registry = self._registry()
            if registry.pop(project_id, None) is not None:
                write_json(self.registry_path, registry)

    def managed_root(self, root_path: Path) -> Path:
        """Resolve a project path and ensure it remains inside managed data.

        The API can import local folders for the local-first workflow, but it
        must never turn an arbitrary server path into a readable project.
        """
        root = root_path.resolve()
        data_dir = self.settings.data_dir.resolve()
        try:
            root.relative_to(data_dir)
        except ValueError as exc:
            raise HTTPException(
                status_code=400,
                detail={
                    "error_type": "unmanaged_project_root",
                    "hint": "Project folders must be located inside KLAVE_DATA_DIR.",
                },
            ) from exc
        return root

    def list_projects(self) -> dict[str, str]:
        return self._registry()

    def get_root(self, project_id: str) -> Path:
        registry = self._registry()
        if project_id not in registry:
            raise HTTPException(
                status_code=404,
                detail={"error_type": "project_not_found", "project_id": project_id},
            )
        return self.managed_root(Path(registry[project_id]))

    def get_manifest(self, project_id: str) -> ProjectManifest:
        return load_manifest(self.get_root(project_id), self.settings.processed_dir_name)

    def read_artifact(self, project_id: str, name: str) -> Any:
        root = self.get_root(project_id)
        control_dir = root / self.settings.processed_dir_name
        # Cost recomputation is a derived scenario over an immutable detection
        # run, so it publishes its own atomic artifact instead of mutating the
        # run that supplied its evidence.
        override = control_dir / "cost_report_override.json"
        path = (
            override
            if name == "cost_report.json" and override.exists()
            else self.artifact_root(project_id) / name
        )
        if not path.exists():
            raise HTTPException(
                status_code=404,
                detail={
                    "error_type": "artifact_not_found",
                    "project_id": project_id,
                    "artifact": name,
                    "hint": "Run POST /projects/{project_id}/process first",
                },
            )
        return read_json(path)

    def read_report(self, project_id: str, name: str) -> str:
        path = self._reports_root(project_id) / name
        if not path.exists():
            raise HTTPException(
                status_code=404,
                detail={
                    "error_type": "report_not_found",
                    "project_id": project_id,
                    "report": name,
                },
            )
        return path.read_text(encoding="utf-8")

    def artifact_root(self, project_id: str) -> Path:
        root = self.get_root(project_id)
        control_dir = root / self.settings.processed_dir_name
        active = self._active_run_dir(control_dir, "artifact_dir")
        return active or control_dir

    def _reports_root(self, project_id: str) -> Path:
        root = self.get_root(project_id)
        control_dir = root / self.settings.processed_dir_name
        active = self._active_run_dir(control_dir, "reports_dir")
        return active or root / "reports"

    @staticmethod
    def _active_run_dir(control_dir: Path, field: str) -> Path | None:
        pointer = control_dir / "active_run.json"
        if not pointer.exists():
            return None
        try:
            value = read_json(pointer)[field]
            candidate = (control_dir / str(value)).resolve()
            candidate.relative_to(control_dir.resolve())
        except (KeyError, OSError, ValueError, TypeError):
            return None
        return candidate if candidate.is_dir() else None


def get_store(settings: Settings = Depends(get_settings)) -> ProjectStore:
    return ProjectStore(settings)
