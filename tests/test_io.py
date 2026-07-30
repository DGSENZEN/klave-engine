"""Artifact persistence guarantees."""

import json
from pathlib import Path

from klave_engine.common.io import write_json, write_text


def test_atomic_json_write_replaces_complete_document(tmp_path: Path) -> None:
    path = tmp_path / "processed" / "artifact.json"
    write_json(path, {"generation": 1})
    write_json(path, {"generation": 2, "items": [1, 2, 3]})

    assert json.loads(path.read_text(encoding="utf-8")) == {
        "generation": 2,
        "items": [1, 2, 3],
    }
    assert not list(path.parent.glob(".artifact.json.*.tmp"))


def test_atomic_text_write_replaces_complete_document(tmp_path: Path) -> None:
    path = tmp_path / "reports" / "summary.md"
    write_text(path, "old")
    write_text(path, "new complete report")

    assert path.read_text(encoding="utf-8") == "new complete report"
