"""Structured-ish logging on top of the standard library.

Stage events are logged as `event key=value key=value` lines so the pipeline
can be debugged from logs alone.
"""

import logging
from typing import Any

_CONFIGURED = False


def configure_logging(level: str = "INFO") -> None:
    global _CONFIGURED
    if _CONFIGURED:
        return
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
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
