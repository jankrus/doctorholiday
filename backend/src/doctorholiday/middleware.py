"""Per-request context: request ID, `X-Request-Id` header and the structured access log."""

import logging
import time
import uuid

from starlette.datastructures import MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from doctorholiday.logs import request_id_var

logger = logging.getLogger("doctorholiday.access")

# Kubernetes probes hit these every few seconds; log them only at DEBUG.
_QUIET_PATHS = frozenset({"/healthz", "/readyz"})


class RequestContextMiddleware:
    """Assigns every HTTP request a fresh UUID.

    A client-supplied `X-Request-Id` is ignored, so clients cannot forge or collide log entries.
    The ID is available as `request.state.request_id` and in every log record of the request.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        request_id = str(uuid.uuid4())
        scope.setdefault("state", {})["request_id"] = request_id
        token = request_id_var.set(request_id)
        started = time.perf_counter()
        status = 500

        async def send_with_request_id(message: Message) -> None:
            nonlocal status
            if message["type"] == "http.response.start":
                status = message["status"]
                MutableHeaders(scope=message)["X-Request-Id"] = request_id
            await send(message)

        try:
            await self.app(scope, receive, send_with_request_id)
        except Exception:
            logger.exception("unhandled exception")
            raise
        finally:
            # Path only: query strings may carry personal data.
            logger.log(
                logging.DEBUG if scope["path"] in _QUIET_PATHS else logging.INFO,
                "request",
                extra={
                    "method": scope["method"],
                    "path": scope["path"],
                    "status": status,
                    "durationMs": round((time.perf_counter() - started) * 1000, 1),
                    "client": scope["client"][0] if scope.get("client") else None,
                },
            )
            request_id_var.reset(token)
