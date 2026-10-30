"""Failed-login counters (#14). The rate limiting policy lives in doctorholiday.auth.throttling."""

from datetime import datetime, timedelta

from sqlalchemy import delete, func, or_, select, tuple_
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from doctorholiday.models import LoginThrottle, ThrottleScope


def database_now(session: Session) -> datetime:
    """The transaction's `now()`, the one clock all counters are compared with."""
    return session.scalars(select(func.now())).one()


def lock_counter(session: Session, *, scope: ThrottleScope, key_hash: bytes) -> LoginThrottle:
    """The counter for this key, created if missing and locked until the transaction ends.

    The lock serialises concurrent logins with the same key, so parallel guesses cannot all pass
    the check before the first failure is counted.
    """
    # DO UPDATE instead of DO NOTHING: it locks and returns the row in one statement, even if a
    # concurrent transaction inserted or deleted it in the meantime.
    statement = insert(LoginThrottle).values(scope=scope, key_hash=key_hash)
    return session.scalars(
        statement.on_conflict_do_update(
            index_elements=[LoginThrottle.scope, LoginThrottle.key_hash],
            set_={"scope": statement.excluded.scope},
        ).returning(LoginThrottle),
        execution_options={"populate_existing": True},
    ).one()


def delete_counter(session: Session, counter: LoginThrottle) -> None:
    session.delete(counter)
    session.flush()


def delete_stale_counters(session: Session, *, window: timedelta) -> None:
    """Delete counters whose window and lockout are over; they would be reset anyway.

    Skips rows other transactions hold, so it never waits for or deadlocks with a running login.
    Call it before `lock_counter`, so the caller's own rows are not locked yet.
    """
    stale = (
        select(LoginThrottle.scope, LoginThrottle.key_hash)
        .where(
            LoginThrottle.window_started_at <= func.now() - window,
            or_(LoginThrottle.locked_until.is_(None), LoginThrottle.locked_until <= func.now()),
        )
        .with_for_update(skip_locked=True)
    )
    session.execute(
        delete(LoginThrottle)
        .where(tuple_(LoginThrottle.scope, LoginThrottle.key_hash).in_(stale))
        .execution_options(synchronize_session=False)
    )
