"""Rate limit counters (BR-03). The policy lives in doctorholiday.auth.rate_limiting."""

from datetime import datetime, timedelta

from sqlalchemy import delete, func, or_, select, tuple_
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from doctorholiday.models import RateLimit, RateLimitScope


def database_now(session: Session) -> datetime:
    """The transaction's `now()`, the one clock all counters are compared with."""
    return session.scalars(select(func.now())).one()


def lock_counter(session: Session, *, scope: RateLimitScope, key_hash: bytes) -> RateLimit:
    """The counter for this key, created if missing and locked until the transaction ends.

    The lock serialises concurrent requests with the same key, so parallel attempts cannot all
    pass the check before the first one is counted.
    """
    # DO UPDATE instead of DO NOTHING: it locks and returns the row in one statement, even if a
    # concurrent transaction inserted or deleted it in the meantime.
    statement = insert(RateLimit).values(scope=scope, key_hash=key_hash)
    return session.scalars(
        statement.on_conflict_do_update(
            index_elements=[RateLimit.scope, RateLimit.key_hash],
            set_={"scope": statement.excluded.scope},
        ).returning(RateLimit),
        execution_options={"populate_existing": True},
    ).one()


def delete_counter(session: Session, counter: RateLimit) -> None:
    session.delete(counter)
    session.flush()


def delete_stale_counters(session: Session, *, scope: RateLimitScope, window: timedelta) -> None:
    """Delete the scope's counters whose window and lockout are over; they would be reset anyway.

    Skips rows other transactions hold, so it never waits for or deadlocks with a running request.
    Call it before `lock_counter`, so the caller's own rows are not locked yet.
    """
    stale = (
        select(RateLimit.scope, RateLimit.key_hash)
        .where(
            RateLimit.scope == scope,
            RateLimit.window_started_at <= func.now() - window,
            or_(RateLimit.locked_until.is_(None), RateLimit.locked_until <= func.now()),
        )
        .with_for_update(skip_locked=True)
    )
    session.execute(
        delete(RateLimit)
        .where(tuple_(RateLimit.scope, RateLimit.key_hash).in_(stale))
        .execution_options(synchronize_session=False)
    )
