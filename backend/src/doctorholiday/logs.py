"""Structured JSON logging to stdout (one object per line, no files: read-only root filesystem).

Never pass passwords, session IDs, tokens, MFA secrets or request bodies to a logger (AGENTS.md
rule 3). As a second line of defence, `extra` fields whose name looks sensitive are redacted.
"""

import json
import logging
import re
import sys
from contextvars import ContextVar
from datetime import UTC, datetime
from typing import Any

from doctorholiday.config import LogLevel

request_id_var: ContextVar[str | None] = ContextVar("request_id", default=None)

_SENSITIVE_KEY = re.compile(
    r"pass|secret|token|cookie|session|authorization|mfa|otp|recovery|credential", re.IGNORECASE
)
_REDACTED = "[REDACTED]"
# Attributes every LogRecord has; everything else was passed via `extra`. uvicorn adds
# `color_message`, a copy of the message with ANSI colour codes.
_RECORD_ATTRS = frozenset(logging.makeLogRecord({}).__dict__) | {
    "message",
    "asctime",
    "taskName",
    "color_message",
}


def _redact(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: _REDACTED if _SENSITIVE_KEY.search(str(key)) else _redact(item)
            for key, item in value.items()
        }
    if isinstance(value, list | tuple):
        return [_redact(item) for item in value]
    return value


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        entry: dict[str, Any] = {
            "timestamp": datetime.fromtimestamp(record.created, UTC)
            .isoformat(timespec="milliseconds")
            .replace("+00:00", "Z"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "requestId": request_id_var.get(),
        }
        extra = {key: value for key, value in record.__dict__.items() if key not in _RECORD_ATTRS}
        entry.update(_redact(extra))
        if record.exc_info:
            entry["exception"] = self.formatException(record.exc_info)
        return json.dumps(entry, default=str, ensure_ascii=False)


def configure_logging(level: LogLevel) -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger()
    root.handlers[:] = [handler]
    root.setLevel(level.value)
    # uvicorn's own handlers write plain text; route its records through the root handler.
    for name in ("uvicorn", "uvicorn.error"):
        uvicorn_logger = logging.getLogger(name)
        uvicorn_logger.handlers.clear()
        uvicorn_logger.propagate = True
    # Replaced by RequestContextMiddleware, which logs without query strings.
    logging.getLogger("uvicorn.access").disabled = True
