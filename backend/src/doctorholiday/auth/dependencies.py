"""Who is calling: session cookie → token hash → valid session row → active user.

- `CurrentSession`: any session state; for `/auth/me` and `/auth/logout` (BR-05).
- `ActiveUser`: the user of an `ACTIVE` session; every other endpoint that needs a login uses
  this one (e.g. bookings, #17). Other states get `403 MFA_REQUIRED`.
- `reject_session`: for register and login, which only callers without a session may use.
"""

from dataclasses import dataclass
from datetime import timedelta
from typing import Annotated

from fastapi import Depends, Request, status
from sqlalchemy.orm import Session

from doctorholiday.auth.sessions import hash_token, token_from_cookie
from doctorholiday.config import Settings
from doctorholiday.db import DbSession
from doctorholiday.errors import ApiError, ErrorCode
from doctorholiday.models import SessionState, User, UserSession
from doctorholiday.repositories import sessions, users


@dataclass(frozen=True)
class Authenticated:
    session: UserSession
    user: User


def _authenticate(request: Request, db: Session) -> Authenticated | None:
    token = token_from_cookie(request)
    if token is None:
        return None
    settings: Settings = request.app.state.settings
    user_session = sessions.refresh_session(
        db,
        token_hash=hash_token(token),
        idle_timeout=timedelta(minutes=settings.session_idle_timeout_minutes),
    )
    if user_session is None:
        return None
    user = users.get_user(db, user_session.user_id)
    # A deactivated or deleted account loses its sessions immediately, not only at the next login.
    if user is None or not user.is_active or user.deleted_at is not None:
        return None
    return Authenticated(session=user_session, user=user)


def _require_session(request: Request, db: DbSession) -> Authenticated:
    authenticated = _authenticate(request, db)
    if authenticated is None:
        raise ApiError(status.HTTP_401_UNAUTHORIZED, ErrorCode.UNAUTHENTICATED, "Please log in.")
    return authenticated


CurrentSession = Annotated[Authenticated, Depends(_require_session)]


def _require_active_user(authenticated: CurrentSession) -> User:
    if authenticated.session.state is not SessionState.ACTIVE:
        raise ApiError(
            status.HTTP_403_FORBIDDEN,
            ErrorCode.MFA_REQUIRED,
            "Please complete the two-factor authentication first.",
        )
    return authenticated.user


ActiveUser = Annotated[User, Depends(_require_active_user)]


def reject_session(request: Request, db: DbSession) -> None:
    if _authenticate(request, db) is not None:
        raise ApiError(status.HTTP_403_FORBIDDEN, ErrorCode.FORBIDDEN, "You are already logged in.")
