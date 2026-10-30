"""Register, login, logout and the current session (A01, A03, A06, A22; #14).

MVP subset of #14; not here yet: rate limiting and lockout (429), MFA, the first-admin bootstrap
(#15), CSRF protection, invitations. Search for MVP-TEMP to find the temporary shortcuts.
"""

import logging
import uuid
from datetime import timedelta
from ipaddress import ip_address
from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response, status
from pydantic import BaseModel, ConfigDict, EmailStr, Field, SecretStr
from sqlalchemy.orm import Session

from doctorholiday.auth.dependencies import CurrentSession, reject_session
from doctorholiday.auth.passwords import hash_password, verify_dummy, verify_password
from doctorholiday.auth.sessions import (
    clear_session_cookie,
    hash_token,
    new_token,
    set_session_cookie,
    token_from_cookie,
)
from doctorholiday.config import Settings
from doctorholiday.db import DbSession
from doctorholiday.errors import ErrorCode, error_response
from doctorholiday.models import AuditAction, AuditOutcome, IPAddress, Role, SessionState, User
from doctorholiday.repositories import sessions, users
from doctorholiday.repositories.audit import audit_target, record_event
from doctorholiday.repositories.errors import EmailAlreadyRegisteredError

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])

# Field types as in backend/openapi.yaml. Passwords are SecretStr so they never show up in a repr
# or traceback, and they are not trimmed (BR-01).
Email = Annotated[EmailStr, Field(min_length=3, max_length=254)]
NewPassword = Annotated[SecretStr, Field(min_length=12, max_length=128)]
Password = Annotated[SecretStr, Field(min_length=1, max_length=128)]
DisplayName = Annotated[str, Field(min_length=1, max_length=100, pattern=r"^[^\x00-\x1F\x7F<>]+$")]


class _Request(BaseModel):
    model_config = ConfigDict(extra="forbid")  # additionalProperties: false


class RegisterRequest(_Request):
    email: Email
    password: NewPassword
    display_name: DisplayName | None = Field(default=None, alias="displayName")
    # MVP-TEMP: lets testers create every role until invitations (FR-02) and the admin bootstrap
    # (#15) exist. Remove together with `role` in RegisterRequest in openapi.yaml; registration
    # then always creates a PATIENT again (BR-02).
    role: Role = Role.PATIENT


class LoginRequest(_Request):
    email: Email
    password: Password


class CurrentUser(BaseModel):
    id: uuid.UUID
    email: str
    display_name: str | None = Field(default=None, serialization_alias="displayName")
    role: Role
    mfa_enabled: bool = Field(serialization_alias="mfaEnabled")


class SessionInfo(BaseModel):
    state: SessionState
    # Only in ACTIVE (BR-05).
    user: CurrentUser | None = None
    # MVP-TEMP: `setupRequired` is left out. The frontend sends an admin with setupRequired to
    # /setup, and PUT /api/v1/settings does not exist yet. `appointmentAccessUntil` follows with
    # the grants (#18).


_NO_STORE = {"Cache-Control": "no-store"}


def _client_ip(request: Request) -> IPAddress | None:
    # The direct peer; behind ingress-nginx that is the proxy until forwarded headers are handled.
    if request.client is None:
        return None
    try:
        return ip_address(request.client.host)
    except ValueError:
        return None


def _session_info(db: Session, state: SessionState, user: User) -> SessionInfo:
    if state is not SessionState.ACTIVE:
        return SessionInfo(state=state)
    credential = users.get_credential(db, user.id)
    return SessionInfo(
        state=state,
        user=CurrentUser(
            id=user.id,
            email=user.email or "",
            display_name=user.display_name,
            role=user.role,
            mfa_enabled=credential is not None and credential.mfa_enabled,
        ),
    )


@router.post(
    "/register",
    operation_id="register",
    status_code=status.HTTP_202_ACCEPTED,
    dependencies=[Depends(reject_session)],
)
def register(body: RegisterRequest, request: Request, db: DbSession) -> Response:
    # Hashed before the insert, so a taken e-mail costs the same time as a new account (BR-02).
    password_hash = hash_password(body.password.get_secret_value())
    try:
        user = users.create_user(
            db,
            email=body.email,
            display_name=body.display_name,
            role=body.role,
            password_hash=password_hash,
        )
    except EmailAlreadyRegisteredError:
        existing = users.get_user_by_email(db, body.email)
        record_event(
            db,
            action=AuditAction.USER_REGISTERED,
            outcome=AuditOutcome.FAILURE,
            target=audit_target("user", existing.id) if existing else None,
            ip=_client_ip(request),
            details={"reason": "EMAIL_TAKEN"},
        )
        logger.info("registration with a taken e-mail ignored")
    else:
        record_event(
            db,
            action=AuditAction.USER_REGISTERED,
            outcome=AuditOutcome.SUCCESS,
            actor_id=user.id,
            target=audit_target("user", user.id),
            ip=_client_ip(request),
        )
        logger.info("user registered", extra={"userId": str(user.id), "role": user.role})
    # The same answer in both cases, so the endpoint cannot be used to find accounts.
    return Response(status_code=status.HTTP_202_ACCEPTED)


@router.post(
    "/login",
    operation_id="login",
    response_model=SessionInfo,
    response_model_exclude_none=True,
    dependencies=[Depends(reject_session)],
)
def login(body: LoginRequest, request: Request, response: Response, db: DbSession) -> object:
    password = body.password.get_secret_value()
    user = users.get_user_by_email(db, body.email)
    if user is None:
        verify_dummy(password)
        failure = "UNKNOWN_ACCOUNT"
    else:
        credential = users.get_credential(db, user.id)
        if credential is None:
            verify_dummy(password)
            failure = "UNKNOWN_ACCOUNT"
        # The password is checked first, so an inactive account takes as long as an active one.
        elif not verify_password(credential.password_hash, password):
            failure = "WRONG_PASSWORD"
        elif not user.is_active or user.deleted_at is not None:
            failure = "INACTIVE"
        else:
            failure = None

    if failure is not None:
        record_event(
            db,
            action=AuditAction.LOGIN,
            outcome=AuditOutcome.FAILURE,
            target=audit_target("user", user.id) if user else None,
            ip=_client_ip(request),
            details={"reason": failure},
        )
        logger.info("login failed", extra={"reason": failure})
        # Returned, not raised: raising would roll back the audit event. Identical for every
        # cause (BR-03).
        return error_response(
            request,
            status.HTTP_401_UNAUTHORIZED,
            ErrorCode.INVALID_CREDENTIALS,
            "E-mail or password is incorrect.",
        )

    # A cookie sent along here is no valid session (reject_session), but may name an expired one.
    # It is deleted and never reused: the new session always gets a fresh token (session fixation).
    if (old_token := token_from_cookie(request)) is not None:
        sessions.delete_session(db, token_hash=hash_token(old_token))

    settings: Settings = request.app.state.settings
    token = new_token()
    # MVP-TEMP: always ACTIVE. With MFA (#21), staff roles start in MFA_ENROLLMENT_REQUIRED and
    # accounts with MFA in MFA_PENDING (BR-05).
    state = SessionState.ACTIVE
    sessions.create_session(
        db,
        token_hash=hash_token(token),
        user_id=user.id,
        state=state,
        absolute_timeout=timedelta(minutes=settings.session_absolute_timeout_minutes),
    )
    record_event(
        db,
        action=AuditAction.LOGIN,
        outcome=AuditOutcome.SUCCESS,
        actor_id=user.id,
        target=audit_target("user", user.id),
        ip=_client_ip(request),
    )
    logger.info("login succeeded", extra={"userId": str(user.id)})
    set_session_cookie(response, token)
    response.headers.update(_NO_STORE)
    return _session_info(db, state, user)


@router.post("/logout", operation_id="logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(authenticated: CurrentSession, request: Request, db: DbSession) -> Response:
    sessions.delete_session(db, token_hash=authenticated.session.token_hash)
    record_event(
        db,
        action=AuditAction.LOGOUT,
        outcome=AuditOutcome.SUCCESS,
        actor_id=authenticated.user.id,
        target=audit_target("user", authenticated.user.id),
        ip=_client_ip(request),
    )
    response = Response(status_code=status.HTTP_204_NO_CONTENT, headers=_NO_STORE)
    clear_session_cookie(response)
    return response


@router.get(
    "/me",
    operation_id="getCurrentSession",
    response_model=SessionInfo,
    response_model_exclude_none=True,
)
def me(authenticated: CurrentSession, response: Response, db: DbSession) -> SessionInfo:
    response.headers.update(_NO_STORE)
    return _session_info(db, authenticated.session.state, authenticated.user)
