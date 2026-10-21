"""Best-effort application logs with scoped context and bounded redaction."""

import logging
import traceback
from contextvars import ContextVar
from typing import Any

from klave_engine.common.diagnostics import current_context, safe_log, sanitize_path, sanitize_text

_CONFIGURED = False
request_id_var: ContextVar[str] = ContextVar("klave_request_id", default="-")


class _RequestIdFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        context = current_context()
        record.request_id = context.request_id or request_id_var.get()
        for key in ("workspace_id", "user_id", "project_id", "job_id", "run_id"):
            setattr(record, key, getattr(context, key))
        # Discard raw arguments and exception tuples before any handler can
        # re-render unsanitized exception text (including Uvicorn's handlers).
        try:
            record.msg = sanitize_text(record.getMessage(), 8000)
            record.args = ()
            if record.exc_info:
                record.exc_text = sanitize_text(
                    "".join(traceback.format_exception(*record.exc_info)), 8000
                )
                record.exc_info = None
            elif record.exc_text:
                record.exc_text = sanitize_text(record.exc_text, 8000)
            if record.stack_info:
                record.stack_info = sanitize_text(record.stack_info, 8000)
        except Exception:  # noqa: BLE001 — malformed log values remain diagnostic-only
            record.msg, record.args = "Diagnostic record could not be formatted", ()
            record.exc_info, record.exc_text, record.stack_info = None, None, None
        return True


class _AccessLogFilter(logging.Filter):
    """Keep Uvicorn's five arguments intact for its access formatter."""

    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.args, tuple) and len(record.args) == 5:
            address, method, path, version, status = record.args
            record.args = (address, method, sanitize_path(str(path)), version, status)
        else:
            # An unexpected access-record shape must not bypass redaction.
            record.msg, record.args = "Access diagnostic record omitted", ()
            return False
        return True


class _SafeLogger(logging.LoggerAdapter):
    """Contain handler failures for existing application logging call sites."""

    def log(self, level: int, msg: Any, *args: Any, **kwargs: Any) -> None:
        try:
            super().log(level, msg, *args, **kwargs)
        except Exception:  # noqa: BLE001 — logging cannot change application outcomes
            pass


def configure_logging(level: str = "INFO") -> None:
    global _CONFIGURED
    if _CONFIGURED:
        return
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format=(
            "%(asctime)s %(levelname)s %(name)s rid=%(request_id)s "
            "ws=%(workspace_id)s uid=%(user_id)s job=%(job_id)s "
            "run=%(run_id)s %(message)s"
        ),
    )
    for handler in logging.getLogger().handlers:
        handler.addFilter(_RequestIdFilter())
    # Uvicorn has non-propagating handlers: filter the logger itself before
    # any of them formats the original exception Starlette re-raises.
    logging.getLogger("uvicorn.error").addFilter(_RequestIdFilter())
    logging.getLogger("uvicorn.access").addFilter(_AccessLogFilter())
    _CONFIGURED = True


def get_logger(name: str) -> logging.LoggerAdapter:
    logger = logging.getLogger(name)
    if not any(isinstance(f, _RequestIdFilter) for f in logger.filters):
        logger.addFilter(_RequestIdFilter())
    return _SafeLogger(logger, {})


def log_stage(logger: logging.Logger | logging.LoggerAdapter, event: str, **fields: Any) -> None:
    parts = " ".join(f"{key}={value}" for key, value in fields.items())
    safe_log(logger, logging.INFO, "%s %s", event, parts)


def redact_email(email: str | None) -> str:
    """Keep only enough of an email address for an operator to recognize it."""
    if not email or "@" not in email:
        return "***"
    local, _, domain = email.partition("@")
    return f"{local[:1]}***@{domain}"
