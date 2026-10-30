import json
import logging
import sys

from doctorholiday.logs import JsonFormatter, request_id_var


def _format(message: str, **extra: object) -> dict[str, object]:
    record = logging.makeLogRecord({"name": "test", "levelname": "INFO", "msg": message, **extra})
    line = JsonFormatter().format(record)
    assert "\n" not in line
    return json.loads(line)


def test_entry_is_single_line_json_with_request_id() -> None:
    token = request_id_var.set("3f2c9a4e-8b1d-4c6a-9e2f-7a5b0c1d2e3f")
    try:
        entry = _format("line one\nline two", path="/healthz")
    finally:
        request_id_var.reset(token)

    assert entry["message"] == "line one\nline two"
    assert entry["level"] == "INFO"
    assert entry["logger"] == "test"
    assert entry["requestId"] == "3f2c9a4e-8b1d-4c6a-9e2f-7a5b0c1d2e3f"
    assert entry["path"] == "/healthz"
    assert str(entry["timestamp"]).endswith("Z")


def test_request_id_is_null_outside_requests() -> None:
    assert _format("startup")["requestId"] is None


def test_sensitive_extra_fields_are_redacted() -> None:
    entry = _format(
        "login",
        password="hunter2-sentinel",
        session_id="sid-sentinel",
        context={"mfaSecret": "totp-sentinel", "nested": [{"Authorization": "Bearer x"}]},
        userId="7a5b0c1d-2e3f-4c6a-9e2f-3f2c9a4e8b1d",
    )

    text = json.dumps(entry)
    for sentinel in ("hunter2-sentinel", "sid-sentinel", "totp-sentinel", "Bearer x"):
        assert sentinel not in text
    assert entry["password"] == "[REDACTED]"
    assert entry["userId"] == "7a5b0c1d-2e3f-4c6a-9e2f-3f2c9a4e8b1d"


def test_exception_is_included() -> None:
    try:
        raise ValueError("boom")
    except ValueError:
        entry = _format("failed", exc_info=sys.exc_info())

    assert "ValueError: boom" in str(entry["exception"])
