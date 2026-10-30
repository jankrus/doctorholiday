"""Error responses in the contract's `Error` shape: `{"error": {"code", "message", "requestId"}}`.

Messages are short generic texts; details go to the log, never to the client (AGENTS.md rule 3).
Minimal for now: API errors, request validation and unhandled exceptions. #13 extends it.
"""

import enum
import logging
from collections.abc import Mapping

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

logger = logging.getLogger(__name__)


class ErrorCode(enum.StrEnum):
    """The codes in use so far; values from `ErrorCode` in backend/openapi.yaml."""

    VALIDATION_ERROR = "VALIDATION_ERROR"
    UNAUTHENTICATED = "UNAUTHENTICATED"
    INVALID_CREDENTIALS = "INVALID_CREDENTIALS"
    MFA_REQUIRED = "MFA_REQUIRED"
    FORBIDDEN = "FORBIDDEN"
    RATE_LIMITED = "RATE_LIMITED"
    INTERNAL_ERROR = "INTERNAL_ERROR"


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
        content={
            "error": {
                "code": code.value,
                "message": message,
                "requestId": request.state.request_id,
            }
        },
    )


def _api_error(request: Request, exc: ApiError) -> JSONResponse:
    return error_response(request, exc.status_code, exc.code, exc.message)


def _validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
    # Location and error type only: the error's `input` and `msg` can contain the submitted
    # values, e.g. a password.
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
        "The request is invalid.",
    )


def _internal_error(request: Request, _: Exception) -> JSONResponse:
    # The traceback is logged by RequestContextMiddleware ("unhandled exception").
    return error_response(
        request,
        status.HTTP_500_INTERNAL_SERVER_ERROR,
        ErrorCode.INTERNAL_ERROR,
        "Something went wrong. Please try again later.",
    )


def install_error_handlers(app: FastAPI) -> None:
    app.add_exception_handler(ApiError, _api_error)
    app.add_exception_handler(RequestValidationError, _validation_error)
    app.add_exception_handler(Exception, _internal_error)
