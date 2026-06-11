"""JSON artifact IO helpers."""

import json
from pathlib import Path
from typing import Any

from pydantic import BaseModel


def ensure_dir(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path


def _jsonable(data: Any) -> Any:
    if isinstance(data, BaseModel):
        return data.model_dump(mode="json")
    if isinstance(data, list):
        return [_jsonable(item) for item in data]
    if isinstance(data, dict):
        return {key: _jsonable(value) for key, value in data.items()}
    return data


def write_json(path: Path, data: Any) -> Path:
    """Write a JSON artifact. Accepts pydantic models, lists of models, or plain data."""
    ensure_dir(path.parent)
    path.write_text(json.dumps(_jsonable(data), indent=2, default=str), encoding="utf-8")
    return path


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_text(path: Path, text: str) -> Path:
    ensure_dir(path.parent)
    path.write_text(text, encoding="utf-8")
    return path
