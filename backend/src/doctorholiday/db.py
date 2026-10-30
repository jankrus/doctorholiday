"""Database engine, sessions and the per-request transaction.

Data access is synchronous (SQLAlchemy 2 + psycopg 3, ADR-003); endpoints that use the database
are plain `def` functions, which FastAPI runs in its thread pool. The schema comes from the SQL
migrations in `backend/migrations`; the models in `doctorholiday.models` only mirror it.
"""

import logging
from collections.abc import Iterator
from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy import Engine, create_engine, text
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session, sessionmaker

from doctorholiday.config import Settings

logger = logging.getLogger(__name__)


def create_db_engine(settings: Settings) -> Engine:
    # Lazy: no connection is opened until the first query, so the app starts without a database.
    return create_engine(
        settings.database_url.get_secret_value(),
        pool_pre_ping=True,
        pool_timeout=2,
        hide_parameters=True,
        connect_args={"connect_timeout": 2},
    )


def create_session_factory(engine: Engine) -> sessionmaker[Session]:
    # expire_on_commit=False: objects stay readable after the commit, e.g. to build the response.
    return sessionmaker(bind=engine, expire_on_commit=False)


def get_engine(request: Request) -> Engine:
    return request.app.state.engine


def _db_session(request: Request) -> Iterator[Session]:
    # One transaction per request: committed when the endpoint returns, rolled back on any
    # exception. Used with scope="function" (DbSession below), so the commit runs before the
    # response is sent and a failed commit can never be answered with a success status.
    session_factory: sessionmaker[Session] = request.app.state.session_factory
    with session_factory() as session, session.begin():
        yield session


DbSession = Annotated[Session, Depends(_db_session, scope="function")]


def violated_constraint(exc: IntegrityError) -> str | None:
    """Name of the constraint behind an IntegrityError.

    Repositories map it to a domain error. The driver's message and DETAIL line contain the
    offending values (e.g. an e-mail address) and must never reach a client or a log (rule 3).
    """
    diag = getattr(exc.orig, "diag", None)
    return getattr(diag, "constraint_name", None)


def check_database(engine: Engine) -> bool:
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
    except SQLAlchemyError:
        logger.warning("database not reachable", exc_info=True)
        return False
    return True
