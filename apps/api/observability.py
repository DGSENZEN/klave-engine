"""Request ids and request timing.

Every request gets an id: bound into every log line emitted while serving
it (``rid=…``), echoed back as ``X-Request-Id`` so an error report from a
user pinpoints the exact logs, and honoured when a proxy already assigned
one. Each response logs method, path, status and duration.
"""

from __future__ import annotations

import re
import time
import uuid

from klave_engine.common.logging import get_logger, request_id_var
from starlette.types import ASGIApp, Message, Receive, Scope, Send

logger = get_logger("klave.request")

_SAFE_ID = re.compile(r"^[A-Za-z0-9._-]{4,64}$")
# The event stream stays open for minutes by design; logging it as a slow
# request every time would only bury real slowness.
_QUIET_PATHS = re.compile(r"^/(events|projects/[^/]+/events)$")


class RequestIdMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        incoming = next(
            (v.decode("latin-1") for k, v in scope.get("headers", []) if k == b"x-request-id"),
            None,
        )
        request_id = incoming if incoming and _SAFE_ID.match(incoming) else uuid.uuid4().hex[:12]
        token = request_id_var.set(request_id)
        started = time.perf_counter()
        status_holder = {"status": 0}

        async def send_with_id(message: Message) -> None:
            if message["type"] == "http.response.start":
                status_holder["status"] = message["status"]
                headers = list(message.get("headers", []))
                headers.append((b"x-request-id", request_id.encode("latin-1")))
                message = {**message, "headers": headers}
            await send(message)

        try:
            await self.app(scope, receive, send_with_id)
        finally:
            path = scope.get("path", "")
            if not _QUIET_PATHS.match(path):
                logger.info(
                    "%s %s -> %s in %.0f ms",
                    scope.get("method", "?"),
                    path,
                    status_holder["status"] or "?",
                    (time.perf_counter() - started) * 1000,
                )
            request_id_var.reset(token)
