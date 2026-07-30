"""JSON artifact IO helpers."""

import json
import os
import tempfile
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
    return _atomic_write_text(
        path, json.dumps(_jsonable(data), indent=2, default=str)
    )


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_text(path: Path, text: str) -> Path:
    return _atomic_write_text(path, text)


def _atomic_write_text(path: Path, text: str) -> Path:
    """Atomically replace a UTF-8 text artifact on the same filesystem.

    Readers see either the prior complete artifact or the new complete artifact;
    they never observe a partially written JSON/report file.  ``os.replace`` is
    atomic when source and destination are on the same filesystem, hence the
    temporary file lives beside the destination.
    """
    parent = ensure_dir(path.parent)
    fd, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=parent)
    temp_path = Path(temp_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as out:
            out.write(text)
            out.flush()
            os.fsync(out.fileno())
        os.replace(temp_path, path)
        # Persist the directory entry as well as the file contents where the
        # platform supports directory fsync (Linux/macOS).
        try:
            directory_fd = os.open(parent, os.O_RDONLY)
        except OSError:
            return path
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    except Exception:
        temp_path.unlink(missing_ok=True)
        raise
    return path
