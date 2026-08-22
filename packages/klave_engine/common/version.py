"""Engine identity: a fingerprint of the code that produced a run.

A processed project is only as current as the engine that read it. Rather
than a version number someone must remember to bump, the fingerprint is a
hash of the modules that decide what a drawing means — parsing, detection,
costing, the pipeline — so any change to them marks every earlier run as
produced by an older engine, and the UI can say "reprocesar" instead of
silently showing stale numbers.
"""

import hashlib
from functools import lru_cache
from pathlib import Path

ENGINE_VERSION = "0.9"  # human label; the fingerprint is what changes

_ROOT = Path(__file__).resolve().parent.parent
_WATCHED = ("dxf", "detection", "costing", "conversion", "geometry", "graph", "pipeline.py")


@lru_cache(maxsize=1)
def engine_fingerprint() -> str:
    digest = hashlib.sha256()
    for entry in _WATCHED:
        path = _ROOT / entry
        files = sorted(path.rglob("*.py")) if path.is_dir() else [path]
        for file in files:
            if "__pycache__" in file.parts or not file.exists():
                continue
            digest.update(str(file.relative_to(_ROOT)).encode())
            digest.update(file.read_bytes())
    return digest.hexdigest()[:12]


def engine_stamp() -> dict[str, str]:
    return {"version": ENGINE_VERSION, "fingerprint": engine_fingerprint()}
