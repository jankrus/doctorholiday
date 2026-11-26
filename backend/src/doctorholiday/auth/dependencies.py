"""Who is calling: session cookie → token hash → valid session row → active user.

- `CurrentSession`: any session state; for `/auth/me` and `/auth/logout` (BR-05).
- `ActiveUser`: the user of an `ACTIVE` session; every other endpoint that needs a login uses
  this one (e.g. bookings, #17). Other states get `403 MFA_REQUIRED`.
- `require_roles(...)`: an `ActiveUser` whose role is one of the given ones, else `403 FORBIDDEN`
  (RBAC, `x-roles` in openapi.yaml). Object-level checks ("own only") stay in the endpoint,
  which answers `404` for foreign objects.
- `reject_session`: for register and login, which only callers without a session may use.
- `public`: for the probes, which need no login.

Default deny (#16): every dependency above carries its allowed roles in `AUTHZ_ATTRIBUTE`.
`doctorholiday.auth.policy` reads them from the route table and refuses to start the app if a
route has none, so a new endpoint without an explicit rule never goes live.
"""

import logging
from collections.abc import Callable
from dataclasses import dataclass
from datetime import timedelta
from typing import Annotated

from fastapi import Depends, Request, status
from sqlalchemy.orm import Session

from doctorholiday.auth.sessions import hash_token, token_from_cookie
from doctorholiday.config import Settings
from doctorholiday.db import DbSession
from doctorholiday.errors import ApiError, ErrorCode, forbidden
from doctorholiday.models import Role, SessionState, User, UserSession
from doctorholiday.repositories import sessions, users

logger = logging.getLogger(__name__)

# The roles a dependency lets through; `ANONYMOUS` stands for a request without a session.
AUTHZ_ATTRIBUTE = "authz_roles"
ANONYMOUS = "ANONYMOUS"
_LOGGED_IN = frozenset(role.value for role in Role)


def _marked[F: Callable[..., object]](function: F, roles: frozenset[str]) -> F:
    setattr(function, AUTHZ_ATTRIBUTE, roles)
    return function


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


_marked(_require_session, _LOGGED_IN)
CurrentSession = Annotated[Authenticated, Depends(_require_session)]


def _require_active_user(authenticated: CurrentSession) -> User:
    if authenticated.session.state is not SessionState.ACTIVE:
        raise ApiError(
            status.HTTP_403_FORBIDDEN,
            ErrorCode.MFA_REQUIRED,
            "Please complete the two-factor authentication first.",
        )
    return authenticated.user


_marked(_require_active_user, _LOGGED_IN)
ActiveUser = Annotated[User, Depends(_require_active_user)]


def require_roles(*allowed: Role) -> Callable[[User], User]:
    """Dependency: the active user if their role is allowed, else `403 FORBIDDEN`.

    The role comes from the database row of the session's user, never from the request.
    """
    roles = frozenset(allowed)

    def dependency(user: ActiveUser) -> User:
        if user.role not in roles:
            logger.info("role not allowed", extra={"userId": str(user.id), "role": user.role})
            raise forbidden()
        return user

    return _marked(dependency, frozenset(role.value for role in roles))


def reject_session(request: Request, db: DbSession) -> None:
    if _authenticate(request, db) is not None:
        raise ApiError(status.HTTP_403_FORBIDDEN, ErrorCode.FORBIDDEN, "You are already logged in.")


_marked(reject_session, frozenset({ANONYMOUS}))


def public() -> None:
    """Dependency: an explicit "no login needed" (the probes). Anyone may call the route."""


_marked(public, frozenset({ANONYMOUS}) | _LOGGED_IN)
