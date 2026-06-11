"""API dependencies: settings and the project registry/artifact store.

Routes orchestrate; this store locates projects and reads generated artifacts
rather than recomputing them on every request.
"""

from functools import lru_cache
from pathlib import Path
from typing import Any

from fastapi import Depends, HTTPException
from klave_engine.common.config import Settings
from klave_engine.common.io import read_json, write_json
from klave_engine.ingestion.manifest import ProjectManifest, load_manifest

REGISTRY_FILENAME = "projects_registry.json"


@lru_cache
def get_settings() -> Settings:
    return Settings()


class ProjectStore:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.registry_path = settings.data_dir / REGISTRY_FILENAME

    def _registry(self) -> dict[str, str]:
        if not self.registry_path.exists():
            return {}
        return read_json(self.registry_path)

    def register(self, project_id: str, root_path: Path) -> None:
        registry = self._registry()
        registry[project_id] = str(root_path)
        write_json(self.registry_path, registry)

    def list_projects(self) -> dict[str, str]:
        return self._registry()

    def get_root(self, project_id: str) -> Path:
        registry = self._registry()
        if project_id not in registry:
            raise HTTPException(
                status_code=404,
                detail={"error_type": "project_not_found", "project_id": project_id},
            )
        return Path(registry[project_id])

    def get_manifest(self, project_id: str) -> ProjectManifest:
        return load_manifest(self.get_root(project_id), self.settings.processed_dir_name)

    def read_artifact(self, project_id: str, name: str) -> Any:
        path = self.get_root(project_id) / self.settings.processed_dir_name / name
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
        path = self.get_root(project_id) / "reports" / name
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


def get_store(settings: Settings = Depends(get_settings)) -> ProjectStore:
    return ProjectStore(settings)
