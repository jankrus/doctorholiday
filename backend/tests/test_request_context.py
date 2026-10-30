import logging
import uuid

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from doctorholiday.logs import request_id_var


def test_every_response_has_a_fresh_request_id(client: TestClient) -> None:
    first = client.get("/healthz").headers["X-Request-Id"]
    second = client.get("/does-not-exist").headers["X-Request-Id"]

    assert uuid.UUID(first).version == 4
    assert uuid.UUID(second).version == 4
    assert first != second


def test_client_supplied_request_id_is_ignored(client: TestClient) -> None:
    forged = "forged\nlog-line"

    response = client.get("/healthz", headers={"X-Request-Id": forged})

    assert response.headers["X-Request-Id"] != forged
    assert uuid.UUID(response.headers["X-Request-Id"])


def test_access_log_entry(client: TestClient, caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.DEBUG, logger="doctorholiday.access"):
        response = client.get("/healthz?email=patient@example.org")

    (record,) = [r for r in caplog.records if r.name == "doctorholiday.access"]
    assert record.method == "GET"
    assert record.path == "/healthz"
    assert record.status == 200
    assert record.durationMs >= 0
    assert "patient@example.org" not in caplog.text
    assert response.headers["X-Request-Id"]


def test_request_id_is_available_during_the_request(app: FastAPI, client: TestClient) -> None:
    seen: dict[str, str | None] = {}

    @app.get("/probe-context")
    def probe_context() -> dict[str, str]:
        seen["var"] = request_id_var.get()
        return {}

    response = client.get("/probe-context")

    assert seen["var"] == response.headers["X-Request-Id"]
    assert request_id_var.get() is None


def test_unhandled_exception_is_logged_with_request_id(
    app: FastAPI, caplog: pytest.LogCaptureFixture
) -> None:
    @app.get("/boom")
    def boom() -> None:
        raise RuntimeError("internal detail")

    with (
        TestClient(app, raise_server_exceptions=False) as client,
        caplog.at_level(logging.INFO, logger="doctorholiday.access"),
    ):
        response = client.get("/boom")

    assert response.status_code == 500
    assert "internal detail" not in response.text
    (record,) = [r for r in caplog.records if r.getMessage() == "unhandled exception"]
    assert record.exc_info is not None
    (access,) = [r for r in caplog.records if r.getMessage() == "request"]
    assert access.status == 500
