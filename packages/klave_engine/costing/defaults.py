"""Taller defaults: the costing parameters every new project starts from.

A taller prices the same way project after project — its indirectos, its
anticipo, its usual geometric assumptions. Instead of re-typing them per
project, the workspace keeps one ``taller_defaults.json`` that new projects
inherit as their initial ``costing_overrides.json``. Existing projects are
never touched: changing the defaults only affects projects created later.
"""

from datetime import UTC, datetime
from pathlib import Path

from pydantic import BaseModel, Field

from klave_engine.common.io import read_json, write_json
from klave_engine.costing.models import CostingConfig, CostingOverrides
from klave_engine.costing.recompute import save_overrides

DEFAULTS_FILENAME = "taller_defaults.json"


class WorkspaceDefaults(BaseModel):
    config: CostingConfig = Field(default_factory=CostingConfig)
    updated_by: str | None = None
    updated_at: datetime | None = None


def defaults_path(data_dir: Path) -> Path:
    return data_dir / DEFAULTS_FILENAME


def load_workspace_defaults(data_dir: Path) -> WorkspaceDefaults | None:
    path = defaults_path(data_dir)
    if not path.exists():
        return None
    try:
        return WorkspaceDefaults.model_validate(read_json(path))
    except (ValueError, OSError):
        return None


def save_workspace_defaults(
    data_dir: Path, config: CostingConfig, updated_by: str | None
) -> WorkspaceDefaults:
    defaults = WorkspaceDefaults(
        config=config, updated_by=updated_by, updated_at=datetime.now(UTC)
    )
    write_json(defaults_path(data_dir), defaults)
    return defaults


def clear_workspace_defaults(data_dir: Path) -> bool:
    path = defaults_path(data_dir)
    if not path.exists():
        return False
    path.unlink()
    return True


def apply_workspace_defaults(data_dir: Path, control_dir: Path) -> bool:
    """Seed a freshly created project's overrides from the taller defaults.
    Returns whether anything was written."""
    defaults = load_workspace_defaults(data_dir)
    if defaults is None:
        return False
    save_overrides(
        control_dir,
        CostingOverrides(
            config=defaults.config,
            insumo_prices={},
            version=1,
            updated_by="Taller (valores predeterminados)",
            updated_at=datetime.now(UTC),
        ),
    )
    return True
