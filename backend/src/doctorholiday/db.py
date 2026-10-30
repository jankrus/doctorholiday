"""Database engine. Models, migrations and sessions follow in #12.

Data access is synchronous (SQLAlchemy 2 + psycopg 3); endpoints that use the database are plain
`def` functions, which FastAPI runs in its thread pool.
"""

import logging

from fastapi import Request
from sqlalchemy import Engine, create_engine, text
from sqlalchemy.exc import SQLAlchemyError

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


def get_engine(request: Request) -> Engine:
    return request.app.state.engine


def check_database(engine: Engine) -> bool:
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
    except SQLAlchemyError:
        logger.warning("database not reachable", exc_info=True)
        return False
    return True
