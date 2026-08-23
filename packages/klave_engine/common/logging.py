"""Structured-ish logging on top of the standard library.

Stage events are logged as `event key=value key=value` lines so the pipeline
can be debugged from logs alone.
"""

import logging
from contextvars import ContextVar
from typing import Any

_CONFIGURED = False

# The id of the request being served, injected into every log line emitted
# while handling it — one grep follows one request across the stack.
request_id_var: ContextVar[str] = ContextVar("klave_request_id", default="-")


class _RequestIdFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = request_id_var.get()
        return True


def configure_logging(level: str = "INFO") -> None:
    global _CONFIGURED
    if _CONFIGURED:
        return
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s rid=%(request_id)s %(message)s",
    )
    for handler in logging.getLogger().handlers:
        handler.addFilter(_RequestIdFilter())
    _CONFIGURED = True


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)


def log_stage(logger: logging.Logger, event: str, **fields: Any) -> None:
    """Log a pipeline stage event with structured key=value fields."""
    parts = " ".join(f"{key}={value}" for key, value in fields.items())
    logger.info("%s %s", event, parts)


def redact_email(email: str | None) -> str:
    """"ana@taller.mx" → "a***@taller.mx": enough to recognise, never to harvest."""
    if not email or "@" not in email:
        return "***"
    local, _, domain = email.partition("@")
    return f"{local[:1]}***@{domain}"
