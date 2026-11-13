"""Fixtures for tests against a real, migrated PostgreSQL.

`make test-db` (repo root) starts a throwaway database from compose.yaml, applies the migrations
with the same migrate.sh as everywhere else and sets TEST_DATABASE_URL to the application role
`doctorholiday_app`, so these tests also run with the backend's grants. Without the variable
they are skipped. The database is deleted afterwards, so committed test rows do not matter.
"""

import os
import uuid
from collections.abc import Callable, Iterator
from contextlib import ExitStack, contextmanager
from datetime import datetime, timedelta

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import Engine, create_engine, func, select, update
from sqlalchemy.orm import Session

from doctorholiday.auth.sessions import COOKIE_NAME, hash_token, new_token
from doctorholiday.config import Settings
from doctorholiday.main import create_app
from doctorholiday.models import PracticeSettings, Role, SessionState, User, UserSession
from doctorholiday.repositories.users import create_user
from tests import contract

# Passes the CHECK on credentials.password_hash; not a hash of anything.
DUMMY_PASSWORD_HASH = "$argon2id$test-only"

UserFactory = Callable[..., User]


@pytest.fixture(scope="session")
def db_url() -> str:
    url = os.environ.get("TEST_DATABASE_URL")
    if not url:
        pytest.skip("TEST_DATABASE_URL is not set; run `make test-db` from the repo root")
    return url


@pytest.fixture(scope="session")
def db_engine(db_url: str) -> Iterator[Engine]:
    engine = create_engine(db_url, hide_parameters=True)
    yield engine
    engine.dispose()


@pytest.fixture
def db_session(db_engine: Engine) -> Iterator[Session]:
    """A session whose work is rolled back after the test, including its commits."""
    with db_engine.connect() as connection:
        transaction = connection.begin()
        session = Session(
            bind=connection, join_transaction_mode="create_savepoint", expire_on_commit=False
        )
        try:
            yield session
        finally:
            session.close()
            transaction.rollback()


def _new_user(session: Session, role: Role) -> User:
    return create_user(
        session,
        email=f"{role.lower()}-{uuid.uuid4().hex}@example.test",
        display_name=f"Test {role.lower()}",
        role=role,
        password_hash=DUMMY_PASSWORD_HASH,
    )


@pytest.fixture
def make_user(db_session: Session) -> UserFactory:
    """Users inside the rolled-back test transaction."""
    return lambda role=Role.PATIENT: _new_user(db_session, role)


@pytest.fixture
def make_committed_user(db_engine: Engine) -> UserFactory:
    """Users visible to every connection, for tests with several transactions."""

    def factory(role: Role = Role.PATIENT) -> User:
        with Session(db_engine, expire_on_commit=False) as session, session.begin():
            return _new_user(session, role)

    return factory


# ---------- API tests ----------

ClientFactory = Callable[..., TestClient]


@pytest.fixture
def api_app(env: dict[str, str], db_url: str, monkeypatch: pytest.MonkeyPatch) -> FastAPI:
    monkeypatch.setenv("DATABASE_URL", db_url)
    return create_app(Settings())  # type: ignore[call-arg]


def create_session(engine: Engine, user: User, state: SessionState = SessionState.ACTIVE) -> str:
    """A committed login session of `user`; returns its token. Skips the password check, so the
    tests need no Argon2id hashing."""
    token = new_token()
    with Session(engine) as session, session.begin():
        session.add(
            UserSession(
                token_hash=hash_token(token),
                user_id=user.id,
                state=state,
                expires_at=func.now() + timedelta(hours=1),
            )
        )
    return token


@pytest.fixture
def client_as(api_app: FastAPI, db_engine: Engine) -> Iterator[ClientFactory]:
    """`client_as(user)`: a client logged in as `user`; `client_as(None)`: no session.

    Every response is checked against openapi.yaml (tests/contract.py).
    """
    with ExitStack() as stack:

        def factory(user: User | None, state: SessionState = SessionState.ACTIVE) -> TestClient:
            client = stack.enter_context(TestClient(api_app, base_url="https://testserver"))
            if user is not None:
                client.cookies.set(COOKIE_NAME, create_session(db_engine, user, state))
            return contract.install(client)

        yield factory


def database_now(engine: Engine) -> datetime:
    with Session(engine) as session:
        return session.execute(select(func.now())).scalar_one()


@contextmanager
def practice_settings(engine: Engine, **values: int) -> Iterator[None]:
    """Change the practice settings (e.g. appointment_minutes=30) for the duration of a test."""
    with Session(engine) as session:
        before = session.get_one(PracticeSettings, 1)
    saved = {name: getattr(before, name) for name in values}
    with Session(engine) as session, session.begin():
        session.execute(update(PracticeSettings).where(PracticeSettings.id == 1).values(**values))
    try:
        yield
    finally:
        with Session(engine) as session, session.begin():
            session.execute(
                update(PracticeSettings).where(PracticeSettings.id == 1).values(**saved)
            )
