"""Deterministic ID generation for entities, nodes, edges, and detections."""

import re
import uuid


def sequential_id(prefix: str, index: int, width: int = 6) -> str:
    return f"{prefix}_{index:0{width}d}"


def short_uuid(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:8]}"


def slugify(value: str) -> str:
    return re.sub(r"[^a-zA-Z0-9_-]+", "_", value.strip()).strip("_").lower()


class IdGenerator:
    """Sequential ID generator for one ID namespace (e.g. ``ent``, ``det``)."""

    def __init__(self, prefix: str, start: int = 0) -> None:
        self._prefix = prefix
        self._counter = start

    def next(self) -> str:
        self._counter += 1
        return sequential_id(self._prefix, self._counter)
