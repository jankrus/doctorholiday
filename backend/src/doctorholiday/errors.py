"""Error responses in the contract's `Error` shape: `{"error": {"code", "message", "requestId"}}`.

Every error the API returns goes through here (#13). Messages are short generic texts; details go
to the log, never to the client (AGENTS.md rule 3).

Where each error is answered:
- `ApiError`, request validation, `DataConflictError` and the framework's HTTP errors (unknown
  route, wrong method): the exception handlers installed by `install_error_handlers`.
- Body too large or not JSON: `RequestBodyMiddleware`, before anything parses the body.
- Any other exception: `RequestContextMiddleware`, which logs the traceback and answers `500`.
  Not an exception handler, because Starlette runs those outside the middleware that adds
  `X-Request-Id`.
"""

import enum
import logging
from collections.abc import Mapping
from typing import Any

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from doctorholiday.repositories.errors import (
    DataConflictError,
    TimeAlreadyBookedError,
    WorkingHoursOverlapError,
)

logger = logging.getLogger(__name__)


class ErrorCode(enum.StrEnum):
    """The codes in use so far; values from `ErrorCode` in backend/openapi.yaml."""

    VALIDATION_ERROR = "VALIDATION_ERROR"
    PASSWORD_TOO_COMMON = "PASSWORD_TOO_COMMON"  # noqa: S105  # an error code, not a password
    UNAUTHENTICATED = "UNAUTHENTICATED"
    INVALID_CREDENTIALS = "INVALID_CREDENTIALS"
    MFA_REQUIRED = "MFA_REQUIRED"
    FORBIDDEN = "FORBIDDEN"
    NOT_FOUND = "NOT_FOUND"
    METHOD_NOT_ALLOWED = "METHOD_NOT_ALLOWED"
    CONFLICT = "CONFLICT"
    WORKING_HOURS_OVERLAP = "WORKING_HOURS_OVERLAP"
    TIME_NOT_AVAILABLE = "TIME_NOT_AVAILABLE"
    TIME_ALREADY_BOOKED = "TIME_ALREADY_BOOKED"
    ABSENCE_HAS_APPOINTMENTS = "ABSENCE_HAS_APPOINTMENTS"
    APPOINTMENT_LIMIT_REACHED = "APPOINTMENT_LIMIT_REACHED"
    PAYLOAD_TOO_LARGE = "PAYLOAD_TOO_LARGE"
    UNSUPPORTED_MEDIA_TYPE = "UNSUPPORTED_MEDIA_TYPE"
    RATE_LIMITED = "RATE_LIMITED"
    INTERNAL_ERROR = "INTERNAL_ERROR"


# Generic messages for errors that are answered the same way everywhere.
VALIDATION_MESSAGE = "The request is invalid."
INTERNAL_MESSAGE = "Something went wrong. Please try again later."
PAYLOAD_TOO_LARGE_MESSAGE = "The request is too large."
UNSUPPORTED_MEDIA_TYPE_MESSAGE = "The request body must be JSON (application/json)."
WORKING_HOURS_OVERLAP_MESSAGE = "Working hours of one weekday must not overlap."
NOT_FOUND_MESSAGE = "Not found."


class ApiError(Exception):
    """Raise in endpoints and dependencies to answer with an `Error` body.

    Raising rolls back the request transaction (DbSession). An endpoint that must keep its writes,
    e.g. the audit event of a failed login, returns `error_response(...)` instead.
    """

    def __init__(self, status_code: int, code: ErrorCode, message: str) -> None:
        super().__init__(code.value)
        self.status_code = status_code
        self.code = code
        self.message = message


def error_body(code: ErrorCode, message: str, request_id: str) -> dict[str, Any]:
    return {"error": {"code": code.value, "message": message, "requestId": request_id}}


def error_response(
    request: Request,
    status_code: int,
    code: ErrorCode,
    message: str,
    headers: Mapping[str, str] | None = None,
) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        headers=headers,
        content=error_body(code, message, request.state.request_id),
    )


def _api_error(request: Request, exc: ApiError) -> JSONResponse:
    return error_response(request, exc.status_code, exc.code, exc.message)


def _validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
    # Location and error type only: the error's `input`, `msg` and `ctx` can contain the submitted
    # values (e.g. a password) or parser internals (position of a JSON syntax error).
    logger.info(
        "request validation failed",
        extra={
            "fields": [
                {"loc": [str(part) for part in error["loc"]], "type": error["type"]}
                for error in exc.errors()
            ]
        },
    )
    return error_response(
        request,
        status.HTTP_422_UNPROCESSABLE_CONTENT,
        ErrorCode.VALIDATION_ERROR,
        VALIDATION_MESSAGE,
    )


def _data_conflict(request: Request, exc: DataConflictError) -> JSONResponse:
    # The database rejected a write (constraint). Endpoints that need a more specific answer catch
    # the error themselves; this is the safe default.
    logger.info("data conflict", extra={"conflict": type(exc).__name__})
    if isinstance(exc, TimeAlreadyBookedError):
        code, message = ErrorCode.TIME_ALREADY_BOOKED, "This time is no longer available."
    elif isinstance(exc, WorkingHoursOverlapError):
        code, message = ErrorCode.WORKING_HOURS_OVERLAP, WORKING_HOURS_OVERLAP_MESSAGE
    else:
        code, message = (
            ErrorCode.CONFLICT,
            "The data has changed in the meantime. Please reload and try again.",
        )
    return error_response(request, status.HTTP_409_CONFLICT, code, message)


# HTTP errors raised by Starlette/FastAPI themselves, e.g. by the router. Their `detail` is never
# returned: it is framework text, and for a 405 it names the method.
_HTTP_ERRORS: Mapping[int, tuple[ErrorCode, str]] = {
    status.HTTP_401_UNAUTHORIZED: (ErrorCode.UNAUTHENTICATED, "Please log in."),
    status.HTTP_403_FORBIDDEN: (ErrorCode.FORBIDDEN, "You are not allowed to do this."),
    status.HTTP_404_NOT_FOUND: (ErrorCode.NOT_FOUND, NOT_FOUND_MESSAGE),
    status.HTTP_405_METHOD_NOT_ALLOWED: (
        ErrorCode.METHOD_NOT_ALLOWED,
        "This method is not allowed here.",
    ),
    status.HTTP_413_CONTENT_TOO_LARGE: (ErrorCode.PAYLOAD_TOO_LARGE, PAYLOAD_TOO_LARGE_MESSAGE),
    status.HTTP_415_UNSUPPORTED_MEDIA_TYPE: (
        ErrorCode.UNSUPPORTED_MEDIA_TYPE,
        UNSUPPORTED_MEDIA_TYPE_MESSAGE,
    ),
    status.HTTP_422_UNPROCESSABLE_CONTENT: (ErrorCode.VALIDATION_ERROR, VALIDATION_MESSAGE),
    status.HTTP_429_TOO_MANY_REQUESTS: (
        ErrorCode.RATE_LIMITED,
        "Too many attempts. Please try again later.",
    ),
}
# Headers of an HTTP error that may reach the client; everything else is dropped.
_HTTP_ERROR_HEADERS = frozenset({"allow", "retry-after"})


def _http_error(request: Request, exc: StarletteHTTPException) -> JSONResponse:
    mapped = _HTTP_ERRORS.get(exc.status_code)
    if mapped is None:
        # Nothing in the app raises other statuses; if a library does, answer generically.
        logger.error("unmapped HTTP error", extra={"status": exc.status_code})
        return error_response(
            request,
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            ErrorCode.INTERNAL_ERROR,
            INTERNAL_MESSAGE,
        )
    code, message = mapped
    headers = {
        name: value
        for name, value in (exc.headers or {}).items()
        if name.lower() in _HTTP_ERROR_HEADERS
    }
    return error_response(request, exc.status_code, code, message, headers=headers)


def install_error_handlers(app: FastAPI) -> None:
    app.add_exception_handler(ApiError, _api_error)
    app.add_exception_handler(RequestValidationError, _validation_error)
    app.add_exception_handler(DataConflictError, _data_conflict)
    # Also catches fastapi.HTTPException, a subclass.
    app.add_exception_handler(StarletteHTTPException, _http_error)


def not_found() -> ApiError:
    """Unknown, or someone else's: the same answer, so IDs cannot be probed (AGENTS.md rule 2)."""
    return ApiError(status.HTTP_404_NOT_FOUND, ErrorCode.NOT_FOUND, NOT_FOUND_MESSAGE)
