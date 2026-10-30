"""Fixtures for tests against a real, migrated PostgreSQL.

`make test-db` (repo root) starts a throwaway database from compose.yaml, applies the migrations
with the same migrate.sh as everywhere else and sets TEST_DATABASE_URL to the application role
`doctorholiday_app`, so these tests also run with the backend's grants. Without the variable
they are skipped. The database is deleted afterwards, so committed test rows do not matter.
"""

import os
import uuid
from collections.abc import Callable, Iterator

import pytest
from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session

from doctorholiday.models import Role, User
from doctorholiday.repositories.users import create_user

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
