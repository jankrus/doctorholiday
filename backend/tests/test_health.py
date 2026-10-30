import logging

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine

from doctorholiday.db import get_engine


def test_liveness(client: TestClient) -> None:
    response = client.get("/healthz")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_readiness_with_reachable_database(app: FastAPI, client: TestClient) -> None:
    engine = create_engine("sqlite://")
    app.dependency_overrides[get_engine] = lambda: engine

    response = client.get("/readyz")

    assert response.status_code == 200
    assert response.json() == {"status": "ready"}


def test_readiness_with_unreachable_database(
    client: TestClient, caplog: pytest.LogCaptureFixture
) -> None:
    # The test settings point to 127.0.0.1:1, where nothing listens.
    response = client.get("/readyz")

    assert response.status_code == 503
    assert response.json() == {"status": "not_ready"}
    assert "database not reachable" in caplog.text
    assert "db-password-sentinel" not in caplog.text


def test_no_framework_docs_or_server_header(client: TestClient) -> None:
    for path in ("/docs", "/redoc", "/openapi.json"):
        assert client.get(path).status_code == 404
    assert "server" not in client.get("/healthz").headers


def test_probes_are_logged_quietly(client: TestClient, caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.DEBUG, logger="doctorholiday.access"):
        client.get("/healthz")

    (record,) = [r for r in caplog.records if r.name == "doctorholiday.access"]
    assert record.levelno == logging.DEBUG
