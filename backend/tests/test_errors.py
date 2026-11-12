"""Error handling (#13): every error is the generic `Error` body with a matching request ID."""

import json
import logging
import re
import uuid
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi import APIRouter, FastAPI, HTTPException
from fastapi.testclient import TestClient
from httpx2 import Response

from doctorholiday.config import LogLevel
from doctorholiday.errors import ApiError, ErrorCode
from doctorholiday.logs import configure_logging
from doctorholiday.middleware import MAX_BODY_BYTES
from doctorholiday.repositories.errors import (
    DataConflictError,
    EmailAlreadyRegisteredError,
    TimeAlreadyBookedError,
)
from doctorholiday.validation import RequestModel

OPENAPI = Path(__file__).resolve().parents[1] / "openapi.yaml"

# What must never reach a client: framework, parser and Python internals.
LEAKS = (
    "Traceback",
    'File "',
    ".py",
    "detail",
    "Expecting",
    "line 1",
    "column",
    "JSONDecodeError",
    "pydantic",
    "fastapi",
    "starlette",
    "uvicorn",
    "internal detail",
)


def assert_error(response: Response, status: int, code: str) -> None:
    """The contract's `Error` shape, nothing else, with `requestId` = `X-Request-Id`."""
    assert response.status_code == status
    assert response.headers["content-type"] == "application/json"
    body = response.json()
    assert set(body) == {"error"}
    assert set(body["error"]) == {"code", "message", "requestId"}
    assert body["error"]["code"] == code
    assert len(body["error"]["message"]) <= 200
    assert body["error"]["requestId"] == response.headers["X-Request-Id"]
    assert uuid.UUID(body["error"]["requestId"]).version == 4
    for leak in LEAKS:
        assert leak not in response.text


class Probe(RequestModel):
    name: str


@pytest.fixture
def probe(app: FastAPI) -> Iterator[TestClient]:
    @app.post("/probe-body")
    def probe_body(body: Probe) -> dict[str, str]:
        return {"name": body.name}

    @app.post("/probe-empty", status_code=204)
    def probe_empty() -> None:
        return None

    @app.get("/probe-query")
    def probe_query(limit: int = 10) -> dict[str, int]:
        return {"limit": limit}

    @app.get("/probe-boom")
    def probe_boom() -> None:
        raise RuntimeError("internal detail /srv/app/secret.py")

    @app.get("/probe-api-error")
    def probe_api_error() -> None:
        raise ApiError(403, ErrorCode.FORBIDDEN, "You are not allowed to do this.")

    @app.get("/probe-http-error")
    def probe_http_error() -> None:
        raise HTTPException(status_code=401, detail="internal detail")

    @app.get("/probe-teapot")
    def probe_teapot() -> None:
        raise HTTPException(status_code=418, detail="internal detail")

    @app.get("/probe-conflict/{kind}")
    def probe_conflict(kind: str) -> None:
        errors: dict[str, DataConflictError] = {
            "time": TimeAlreadyBookedError(),
            "email": EmailAlreadyRegisteredError("internal detail"),
        }
        raise errors[kind]

    # raise_server_exceptions=False: the app must answer the 500 itself, like in production.
    with TestClient(app, raise_server_exceptions=False) as client:
        yield client


def _post_json(client: TestClient, path: str, content: bytes | str) -> Response:
    return client.post(path, content=content, headers={"Content-Type": "application/json"})


def test_error_codes_are_in_the_contract() -> None:
    contract = OPENAPI.read_text(encoding="utf-8")
    enum = re.search(r"^    ErrorCode:\n(?:      .*\n)+", contract, re.MULTILINE)
    assert enum is not None
    contract_codes = set(re.findall(r"^        - ([A-Z_]+)$", enum.group(0), re.MULTILINE))
    assert {code.value for code in ErrorCode} <= contract_codes


# ---------- Validation ----------


def test_valid_body_passes(probe: TestClient) -> None:
    response = probe.post("/probe-body", json={"name": "x"})

    assert response.status_code == 200
    assert response.json() == {"name": "x"}


def test_invalid_json_has_no_parser_internals(
    probe: TestClient, caplog: pytest.LogCaptureFixture
) -> None:
    with caplog.at_level(logging.INFO):
        response = _post_json(probe, "/probe-body", b'{"name": "x",,}')

    assert_error(response, 422, "VALIDATION_ERROR")
    (record,) = [r for r in caplog.records if r.getMessage() == "request validation failed"]
    assert record.fields[0]["type"] == "json_invalid"


@pytest.mark.parametrize(
    "body",
    [
        {"name": "x", "role": "ADMIN"},
        {},
        {"name": 1},
        ["name"],
    ],
    ids=["unknown-field", "missing-field", "wrong-type", "not-an-object"],
)
def test_schema_violations(probe: TestClient, body: object) -> None:
    assert_error(probe.post("/probe-body", json=body), 422, "VALIDATION_ERROR")


def test_validation_log_has_no_submitted_values(
    probe: TestClient, caplog: pytest.LogCaptureFixture
) -> None:
    with caplog.at_level(logging.INFO):
        probe.post("/probe-body", json={"name": "x", "password": "value-sentinel"})

    assert "value-sentinel" not in caplog.text
    (record,) = [r for r in caplog.records if r.getMessage() == "request validation failed"]
    assert record.fields == [{"loc": ["body", "password"], "type": "extra_forbidden"}]


def test_unknown_query_parameter(probe: TestClient, caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.INFO):
        response = probe.get("/probe-query?limit=5&email=patient@example.org")

    assert_error(response, 422, "VALIDATION_ERROR")
    # Only the app's own records; the test client logs the URL it requests.
    app_log = " ".join(
        f"{r.getMessage()} {r.__dict__}"
        for r in caplog.records
        if r.name.startswith("doctorholiday")
    )
    assert "unknown query parameters" in app_log
    assert "email" not in app_log


def test_declared_query_parameter_passes(probe: TestClient) -> None:
    assert probe.get("/probe-query?limit=5").json() == {"limit": 5}


def test_query_parameters_of_included_routers(app: FastAPI) -> None:
    # Like the real API routers, which are included with a prefix.
    router = APIRouter(prefix="/probe-router")

    @router.get("/items")
    def items(limit: int = 10) -> dict[str, int]:
        return {"limit": limit}

    app.include_router(router)
    with TestClient(app) as client:
        assert client.get("/probe-router/items?limit=3").json() == {"limit": 3}
        assert_error(client.get("/probe-router/items?offset=3"), 422, "VALIDATION_ERROR")


# ---------- Body size and Content-Type ----------


def test_oversized_body(probe: TestClient) -> None:
    response = _post_json(probe, "/probe-body", json.dumps({"name": "x" * MAX_BODY_BYTES}))

    assert_error(response, 413, "PAYLOAD_TOO_LARGE")


def test_oversized_body_without_content_length(probe: TestClient) -> None:
    def chunks() -> Iterator[bytes]:
        yield b'{"name": "'
        for _ in range(MAX_BODY_BYTES // 1024 + 1):
            yield b"x" * 1024
        yield b'"}'

    response = probe.post(
        "/probe-body", content=chunks(), headers={"Content-Type": "application/json"}
    )

    assert "content-length" not in response.request.headers
    assert_error(response, 413, "PAYLOAD_TOO_LARGE")


def test_body_at_the_limit_passes(probe: TestClient) -> None:
    padding = MAX_BODY_BYTES - len(json.dumps({"name": ""}))
    body = json.dumps({"name": "x" * padding})
    assert len(body) == MAX_BODY_BYTES

    assert _post_json(probe, "/probe-body", body).status_code == 200


def test_body_limit_applies_to_unknown_paths(probe: TestClient) -> None:
    assert_error(
        _post_json(probe, "/nowhere", b"x" * (MAX_BODY_BYTES + 1)), 413, "PAYLOAD_TOO_LARGE"
    )


@pytest.mark.parametrize(
    "content_type",
    [
        None,
        "text/plain",
        "application/x-www-form-urlencoded",
        "application/merge-patch+json",
        "application/json; charset=latin-1",
    ],
)
def test_body_must_be_json(probe: TestClient, content_type: str | None) -> None:
    headers = {} if content_type is None else {"Content-Type": content_type}

    response = probe.post("/probe-body", content=b'{"name": "x"}', headers=headers)

    assert_error(response, 415, "UNSUPPORTED_MEDIA_TYPE")


@pytest.mark.parametrize("content_type", ["application/json", "Application/JSON; charset=UTF-8"])
def test_json_content_types(probe: TestClient, content_type: str) -> None:
    response = probe.post(
        "/probe-body", content=b'{"name": "x"}', headers={"Content-Type": content_type}
    )

    assert response.status_code == 200


def test_request_without_body_needs_no_content_type(probe: TestClient) -> None:
    assert probe.post("/probe-empty").status_code == 204


# ---------- Mapped errors ----------


def test_unknown_route(probe: TestClient) -> None:
    assert_error(probe.get("/does-not-exist"), 404, "NOT_FOUND")


def test_wrong_method(probe: TestClient) -> None:
    response = probe.delete("/healthz")

    assert_error(response, 405, "METHOD_NOT_ALLOWED")
    assert response.headers["Allow"] == "GET"


def test_api_error(probe: TestClient) -> None:
    response = probe.get("/probe-api-error")

    assert_error(response, 403, "FORBIDDEN")
    assert response.json()["error"]["message"] == "You are not allowed to do this."


def test_framework_http_error_drops_its_detail(probe: TestClient) -> None:
    assert_error(probe.get("/probe-http-error"), 401, "UNAUTHENTICATED")


def test_unmapped_http_error_is_answered_generically(probe: TestClient) -> None:
    assert_error(probe.get("/probe-teapot"), 500, "INTERNAL_ERROR")


@pytest.mark.parametrize(("kind", "code"), [("time", "TIME_ALREADY_BOOKED"), ("email", "CONFLICT")])
def test_data_conflict(probe: TestClient, kind: str, code: str) -> None:
    assert_error(probe.get(f"/probe-conflict/{kind}"), 409, code)


# ---------- Unhandled exceptions ----------


def test_internal_exception_returns_the_generic_body_only(
    probe: TestClient, caplog: pytest.LogCaptureFixture
) -> None:
    with caplog.at_level(logging.INFO):
        response = probe.get("/probe-boom")

    assert_error(response, 500, "INTERNAL_ERROR")
    assert response.json()["error"]["message"] == "Something went wrong. Please try again later."
    (record,) = [r for r in caplog.records if r.getMessage() == "unhandled exception"]
    assert record.exc_info is not None
    (access,) = [r for r in caplog.records if r.getMessage() == "request"]
    assert access.status == 500


def test_stack_trace_is_in_the_log_but_not_in_the_response(
    probe: TestClient, capsys: pytest.CaptureFixture[str]
) -> None:
    root = logging.getLogger()
    saved_handlers, saved_level = root.handlers[:], root.level
    configure_logging(LogLevel.INFO)
    try:
        response = probe.get("/probe-boom")
        output = capsys.readouterr().out
    finally:
        root.handlers[:] = saved_handlers
        root.setLevel(saved_level)

    assert "Traceback" not in response.text
    entries = [json.loads(line) for line in output.splitlines() if line.strip()]
    (entry,) = [entry for entry in entries if entry["message"] == "unhandled exception"]
    assert entry["requestId"] == response.headers["X-Request-Id"]
    assert entry["exception"].startswith("Traceback")
    assert "RuntimeError: internal detail /srv/app/secret.py" in entry["exception"]
