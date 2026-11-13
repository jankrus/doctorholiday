"""The database clock: every time rule compares with the transaction's `now()`, never the app's."""

from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session


def database_now(session: Session) -> datetime:
    """The transaction's `now()`; constant for the whole transaction."""
    return session.scalars(select(func.now())).one()
