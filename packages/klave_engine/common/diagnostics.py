"""Safe diagnostic values shared by HTTP and worker boundaries."""

from __future__ import annotations

import json
import logging
import re
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import asdict, dataclass, fields
from datetime import UTC, datetime
from typing import Any

_TOKEN_PATH = re.compile(r"(/by-token/|/compartido/|/auth/reset/|/auth/verify/)([^/\s?\#\"\'<>]+)")
_SECRET = re.compile(
    r"(AIza[0-9A-Za-z_\-]{10,}|sk-[A-Za-z0-9_\-]{10,}|Bearer\s+[A-Za-z0-9._\-]{10,})"
)
_EMAIL = re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b")
_QUERY = re.compile(r"\?[^\s\"\'<>]*")


def _mask_token(match: re.Match[str]) -> str:
    prefix, token = match.groups()
    if prefix == "/auth/verify/" and token == "send":
        return match.group(0)
    return prefix + "[redacted]"


def sanitize_path(path: str) -> str:
    return _TOKEN_PATH.sub(_mask_token, path.split("?", 1)[0].split("#", 1)[0])


def sanitize_text(text: str, limit: int = 600) -> str:
    clean = _TOKEN_PATH.sub(_mask_token, text)
    clean = _QUERY.sub("", clean)
    clean = _SECRET.sub("«clave»", clean)
    return _EMAIL.sub("«correo»", clean)[:limit]


@dataclass(frozen=True)
class DiagnosticContext:
    request_id: str = ""
    workspace_id: str = ""
    user_id: str = ""
    project_id: str = ""
    job_id: str = ""
    run_id: str = ""

    def __post_init__(self) -> None:
        for item in fields(self):
            value = getattr(self, item.name)
            if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9._:-]{0,128}", value):
                object.__setattr__(self, item.name, "")

    @classmethod
    def from_record(cls, value: Any) -> DiagnosticContext:
        if not isinstance(value, dict):
            return cls()
        if any(not isinstance(v, str) for v in value.values()):
            return cls()
        return cls(**{f.name: value.get(f.name, "") for f in fields(cls)})


_context: ContextVar[DiagnosticContext | None] = ContextVar(
    "klave_diagnostic_context", default=None
)


def current_context() -> DiagnosticContext:
    return _context.get() or DiagnosticContext()


@contextmanager
def bind_context(context: DiagnosticContext) -> Iterator[None]:
    token = _context.set(context)
    try:
        yield
    finally:
        _context.reset(token)


def safe_log(
    logger: logging.Logger | logging.LoggerAdapter, level: int, message: str, *args: object
) -> None:
    """Instrumentation failure must not become a product failure."""
    try:
        logger.log(level, message, *args)
    except Exception:  # noqa: BLE001 — best-effort diagnostic boundary
        pass


_EVENTS = {
    "job_admitted": "queued",
    "job_started": "running",
    "job_stage_changed": "running",
    "job_completed": "succeeded",
    "job_failed": "failed",
    "job_interrupted": "failed",
}
_STAGES = {
    "",
    "queued",
    "processing",
    "converting",
    "reading",
    "completed",
    "failed",
    "interrupted",
}
_ERROR_CODES = {"", "conversion_failed", "processing_failed", "processing_interrupted"}


def emit_job_event(
    event: str,
    context: DiagnosticContext,
    *,
    outcome: str,
    stage: str = "",
    duration_ms: float | None = None,
    error_code: str = "",
) -> None:
    try:
        if _EVENTS.get(event) != outcome or stage not in _STAGES or error_code not in _ERROR_CODES:
            return
        record = {
            "schema_version": 1,
            "ts": datetime.now(UTC).isoformat(),
            "event": event,
            "outcome": outcome,
            "stage": stage,
            "error_code": error_code,
            **asdict(context),
        }
        if duration_ms is not None:
            record["duration_ms"] = max(0.0, duration_ms)
        logging.getLogger("klave.jobs").info(json.dumps(record, ensure_ascii=False))
    except Exception:  # noqa: BLE001 — observing never changes the job result
        pass
