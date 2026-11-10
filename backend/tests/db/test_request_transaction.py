"""The DbSession dependency: one transaction per request, committed before the response."""

import uuid
from collections.abc import Iterator

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import Engine, select
from sqlalchemy.orm import Session

from doctorholiday.config import Settings
from doctorholiday.db import DbSession
from doctorholiday.main import create_app
from doctorholiday.models import AuditAction, AuditEvent, AuditOutcome, Role, User
from doctorholiday.repositories.audit import record_event
from tests.db.conftest import UserFactory


@pytest.fixture
def client(
    env: dict[str, str], db_url: str, monkeypatch: pytest.MonkeyPatch
) -> Iterator[TestClient]:
    monkeypatch.setenv("DATABASE_URL", db_url)
    app: FastAPI = create_app(Settings())  # type: ignore[call-arg]

    @app.post("/test/audit")
    def write_event(session: DbSession, target: str, fail: bool = False) -> dict[str, str]:
        record_event(session, action=AuditAction.LOGIN, outcome=AuditOutcome.SUCCESS, target=target)
        if fail:
            raise RuntimeError("endpoint failed after writing")
        return {"status": "ok"}

    @app.post("/test/user")
    def add_user(session: DbSession, email: str) -> dict[str, str]:
        # Not flushed here: the INSERT, and its unique violation, happen in the commit.
        session.add(User(email=email, display_name="Late", role=Role.PATIENT))
        return {"status": "ok"}

    with TestClient(app, raise_server_exceptions=False) as test_client:
        yield test_client


def _events_with_target(engine: Engine, target: str) -> int:
    with Session(engine) as session:
        return len(session.scalars(select(AuditEvent).where(AuditEvent.target == target)).all())


def test_successful_request_is_committed(client: TestClient, db_engine: Engine) -> None:
    target = f"user:{uuid.uuid4()}"
    assert client.post("/test/audit", params={"target": target}).status_code == 200
    assert _events_with_target(db_engine, target) == 1


def test_failed_request_is_rolled_back(client: TestClient, db_engine: Engine) -> None:
    target = f"user:{uuid.uuid4()}"
    assert client.post("/test/audit", params={"target": target, "fail": True}).status_code == 500
    assert _events_with_target(db_engine, target) == 0


def test_failing_commit_is_not_answered_with_success(
    client: TestClient, make_committed_user: UserFactory
) -> None:
    existing = make_committed_user()
    response = client.post("/test/user", params={"email": existing.email})
    assert response.status_code == 500
    assert existing.email not in response.text
