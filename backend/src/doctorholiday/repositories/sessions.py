"""Login sessions. Rows hold only the SHA-256 of the token (doctorholiday.auth.sessions).

Timeouts are compared with the database's `now()`, so there is a single clock for creating,
checking and refreshing a session.
"""

import uuid
from datetime import timedelta

from sqlalchemy import delete, func, update
from sqlalchemy.orm import Session

from doctorholiday.models import SessionState, UserSession


def create_session(
    session: Session,
    *,
    token_hash: bytes,
    user_id: uuid.UUID,
    state: SessionState,
    absolute_timeout: timedelta,
) -> UserSession:
    user_session = UserSession(
        token_hash=token_hash,
        user_id=user_id,
        state=state,
        expires_at=func.now() + absolute_timeout,
    )
    session.add(user_session)
    session.flush()
    return user_session


def refresh_session(
    session: Session, *, token_hash: bytes, idle_timeout: timedelta
) -> UserSession | None:
    """The session with this token if it has neither reached its absolute expiry nor been idle
    for `idle_timeout`; marks it as used now. None for unknown or timed-out sessions.

    Check and refresh are one statement, so a session cannot time out in between.
    """
    return session.scalars(
        update(UserSession)
        .where(
            UserSession.token_hash == token_hash,
            UserSession.expires_at > func.now(),
            UserSession.last_seen_at > func.now() - idle_timeout,
        )
        .values(last_seen_at=func.now())
        .returning(UserSession)
    ).one_or_none()


def delete_session(session: Session, *, token_hash: bytes) -> None:
    """Delete the session with this token, whether or not it has timed out."""
    session.execute(delete(UserSession).where(UserSession.token_hash == token_hash))
