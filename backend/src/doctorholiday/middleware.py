"""ASGI middleware.

- `RequestContextMiddleware`: request ID, `X-Request-Id` header, structured access log and the
  generic `500` for unhandled exceptions.
- `RequestBodyMiddleware`: body size limit (`413`) and JSON-only bodies (`415`), checked before
  anything parses the body.
"""

import logging
import time
import uuid

from starlette.datastructures import Headers, MutableHeaders
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from doctorholiday.errors import (
    INTERNAL_MESSAGE,
    PAYLOAD_TOO_LARGE_MESSAGE,
    UNSUPPORTED_MEDIA_TYPE_MESSAGE,
    ErrorCode,
    error_body,
)
from doctorholiday.logs import request_id_var

logger = logging.getLogger("doctorholiday.access")
_body_logger = logging.getLogger(__name__)

# Kubernetes probes hit these every few seconds; log them only at DEBUG.
_QUIET_PATHS = frozenset({"/healthz", "/readyz"})

# The largest valid body in backend/openapi.yaml (a full weekly schedule) is about 2 KB.
MAX_BODY_BYTES = 16 * 1024


class RequestContextMiddleware:
    """Assigns every HTTP request a fresh UUID.

    A client-supplied `X-Request-Id` is ignored, so clients cannot forge or collide log entries.
    The ID is available as `request.state.request_id` and in every log record of the request.

    An exception that no handler answered is logged with its traceback here and answered with the
    generic `500 INTERNAL_ERROR` body, so that response carries `X-Request-Id` too. Starlette's
    own fallback (ServerErrorMiddleware) sits outside every middleware and would answer without
    it.
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
        response_started = False

        async def send_with_request_id(message: Message) -> None:
            nonlocal status, response_started
            if message["type"] == "http.response.start":
                status = message["status"]
                response_started = True
                MutableHeaders(scope=message)["X-Request-Id"] = request_id
            await send(message)

        try:
            await self.app(scope, receive, send_with_request_id)
        except Exception:
            logger.exception("unhandled exception")
            if response_started:
                # Too late for an error body; the server aborts the response.
                raise
            response = JSONResponse(
                error_body(ErrorCode.INTERNAL_ERROR, INTERNAL_MESSAGE, request_id),
                status_code=500,
            )
            await response(scope, receive, send_with_request_id)
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


def _content_length(headers: Headers) -> int | None:
    try:
        return int(headers["content-length"])
    except (KeyError, ValueError):
        return None


def _is_json(content_type: str | None) -> bool:
    """`application/json`, optionally with `charset=utf-8`; nothing else (no `+json` types)."""
    if content_type is None:
        return False
    media_type, *params = (part.strip().lower() for part in content_type.split(";"))
    return media_type == "application/json" and all(
        param.replace('"', "") in ("charset=utf-8", "") for param in params
    )


class RequestBodyMiddleware:
    """Rejects bodies over `MAX_BODY_BYTES` (`413`) and non-empty bodies that are not JSON (`415`).

    Runs inside `RequestContextMiddleware` (needs the request ID) and before routing, so it covers
    every path, also unknown ones. A declared `Content-Length` over the limit is rejected without
    reading; otherwise the body is read up to the limit and handed on unchanged. Requests without a
    body (GET, `POST /logout`) need no `Content-Type`.
    """

    def __init__(self, app: ASGIApp, max_body_bytes: int = MAX_BODY_BYTES) -> None:
        self.app = app
        self.max_body_bytes = max_body_bytes

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        headers = Headers(scope=scope)
        length = _content_length(headers)
        if length is not None and length > self.max_body_bytes:
            await self._reject(scope, receive, send, 413)
            return

        body = bytearray()
        more_body = True
        while more_body:
            message = await receive()
            if message["type"] == "http.disconnect":
                return
            body += message.get("body", b"")
            if len(body) > self.max_body_bytes:
                await self._reject(scope, receive, send, 413)
                return
            more_body = message.get("more_body", False)

        if body and not _is_json(headers.get("content-type")):
            await self._reject(scope, receive, send, 415)
            return

        replayed = False

        async def replay() -> Message:
            nonlocal replayed
            if replayed:
                # After the body, the app only waits for the disconnect.
                return await receive()
            replayed = True
            return {"type": "http.request", "body": bytes(body), "more_body": False}

        await self.app(scope, replay, send)

    @staticmethod
    async def _reject(scope: Scope, receive: Receive, send: Send, status_code: int) -> None:
        if status_code == 413:
            code, message = ErrorCode.PAYLOAD_TOO_LARGE, PAYLOAD_TOO_LARGE_MESSAGE
        else:
            code, message = ErrorCode.UNSUPPORTED_MEDIA_TYPE, UNSUPPORTED_MEDIA_TYPE_MESSAGE
        _body_logger.info("request body rejected", extra={"status": status_code})
        response = JSONResponse(
            error_body(code, message, scope["state"]["request_id"]), status_code=status_code
        )
        await response(scope, receive, send)
