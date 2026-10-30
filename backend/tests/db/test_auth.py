"""Register, login, logout and /me against a real database (#14 acceptance criteria, minus 429).

The app commits for real; every test uses its own e-mail addresses, and the database is thrown
away after `make test-db`.
"""

import hashlib
import json
import logging
import uuid
from collections.abc import Callable, Iterator
from contextlib import ExitStack
from datetime import timedelta

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from httpx2 import Response
from sqlalchemy import Engine, func, select, update
from sqlalchemy.orm import Session

from doctorholiday.auth.dependencies import ActiveUser
from doctorholiday.auth.sessions import COOKIE_NAME
from doctorholiday.config import Settings
from doctorholiday.logs import JsonFormatter
from doctorholiday.main import create_app
from doctorholiday.models import (
    AuditAction,
    AuditEvent,
    AuditOutcome,
    Credential,
    Role,
    SessionState,
    User,
    UserSession,
)

PASSWORD = "correct horse battery staple"
COOKIE_ATTRIBUTES = "HttpOnly; Secure; SameSite=Strict; Path=/"
ClientFactory = Callable[[], TestClient]


@pytest.fixture
def app(env: dict[str, str], db_url: str, monkeypatch: pytest.MonkeyPatch) -> FastAPI:
    monkeypatch.setenv("DATABASE_URL", db_url)
    app = create_app(Settings())  # type: ignore[call-arg]

    @app.get("/test/active-user")
    def active_user(user: ActiveUser) -> dict[str, str]:
        return {"id": str(user.id)}

    return app


@pytest.fixture
def new_client(app: FastAPI) -> Iterator[ClientFactory]:
    """Independent clients (own cookie jar), e.g. two browsers. https: the cookie is Secure."""
    with ExitStack() as stack:
        yield lambda: stack.enter_context(TestClient(app, base_url="https://testserver"))


@pytest.fixture
def client(new_client: ClientFactory) -> TestClient:
    return new_client()


@pytest.fixture
def email() -> str:
    # Not .test: email-validator rejects special-use domains.
    return f"patient-{uuid.uuid4().hex}@example.com"


def register(client: TestClient, email: str, password: str = PASSWORD, **extra: str) -> Response:
    return client.post(
        "/api/v1/auth/register", json={"email": email, "password": password, **extra}
    )


def login(client: TestClient, email: str, password: str = PASSWORD) -> Response:
    return client.post("/api/v1/auth/login", json={"email": email, "password": password})


def registered_and_logged_in(client: TestClient, email: str) -> str:
    """Register, log in and return the session token."""
    assert register(client, email).status_code == 202
    response = login(client, email)
    assert response.status_code == 200
    return response.cookies[COOKIE_NAME]


def use_cookie(client: TestClient, token: str) -> None:
    """Make `token` the only session cookie the client sends.

    Without a domain: httpx never sends a cookie set with domain="testserver".
    """
    client.cookies.clear()
    client.cookies.set(COOKIE_NAME, token)


def user_by_email(engine: Engine, email: str) -> User | None:
    with Session(engine) as session:
        return session.scalars(select(User).where(User.email == email)).one_or_none()


def session_row(engine: Engine, token: str) -> UserSession | None:
    token_hash = hashlib.sha256(token.encode()).digest()
    with Session(engine) as session:
        return session.scalars(
            select(UserSession).where(UserSession.token_hash == token_hash)
        ).one_or_none()


def change_session(engine: Engine, token: str, **values: object) -> None:
    token_hash = hashlib.sha256(token.encode()).digest()
    with Session(engine) as session, session.begin():
        session.execute(
            update(UserSession).where(UserSession.token_hash == token_hash).values(**values)
        )


def audit_events(engine: Engine, action: AuditAction, target_user: User) -> list[AuditEvent]:
    with Session(engine) as session:
        return list(
            session.scalars(
                select(AuditEvent)
                .where(AuditEvent.action == action, AuditEvent.target == f"user:{target_user.id}")
                .order_by(AuditEvent.timestamp)
            )
        )


def without_request_id(response: Response) -> tuple[int, dict[str, str], dict[str, object]]:
    """Status, headers and body with the per-request ID removed, for comparing responses."""
    headers = {k: v for k, v in response.headers.items() if k != "x-request-id"}
    body = response.json()
    assert uuid.UUID(body["error"].pop("requestId")) == uuid.UUID(response.headers["x-request-id"])
    return response.status_code, headers, body


# ---------- Happy path ----------


def test_register_login_me_logout(client: TestClient, email: str, db_engine: Engine) -> None:
    response = register(client, email, displayName="Erika Mustermann")
    assert response.status_code == 202
    assert response.content == b""

    response = login(client, email)
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    user = user_by_email(db_engine, email)
    assert user is not None
    expected = {
        "state": "ACTIVE",
        "user": {
            "id": str(user.id),
            "email": email,
            "displayName": "Erika Mustermann",
            "role": "PATIENT",
            "mfaEnabled": False,
        },
    }
    assert response.json() == expected

    response = client.get("/api/v1/auth/me")
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    assert response.json() == expected

    response = client.post("/api/v1/auth/logout")
    assert response.status_code == 204
    assert response.headers["set-cookie"] == f"{COOKIE_NAME}=; Max-Age=0; {COOKIE_ATTRIBUTES}"
    assert client.get("/api/v1/auth/me").status_code == 401


def test_optional_fields_are_absent_not_null(client: TestClient, email: str) -> None:
    registered_and_logged_in(client, email)
    body = client.get("/api/v1/auth/me").json()
    assert "displayName" not in body["user"]
    # MVP-TEMP: no setupRequired; appointmentAccessUntil comes with the grants (#18).
    assert set(body) == {"state", "user"}


@pytest.mark.parametrize("role", list(Role))
def test_register_with_role(client: TestClient, email: str, role: Role) -> None:
    # MVP-TEMP: the role field goes away with invitations and the bootstrap.
    assert register(client, email, role=role.value).status_code == 202
    login(client, email)
    assert client.get("/api/v1/auth/me").json()["user"]["role"] == role.value


def test_email_is_case_insensitive(client: TestClient, email: str) -> None:
    assert register(client, email).status_code == 202
    assert login(client, email.upper()).status_code == 200


def test_password_is_not_trimmed(client: TestClient, email: str) -> None:
    padded = f"  {PASSWORD}  "
    assert register(client, email, padded).status_code == 202
    assert login(client, email, PASSWORD).status_code == 401
    assert login(client, email, padded).status_code == 200


def test_password_is_stored_as_argon2id(client: TestClient, email: str, db_engine: Engine) -> None:
    register(client, email)
    user = user_by_email(db_engine, email)
    assert user is not None
    with Session(db_engine) as session:
        credential = session.get(Credential, user.id)
    assert credential is not None
    assert credential.password_hash.startswith("$argon2id$")
    assert PASSWORD not in credential.password_hash


# ---------- No account enumeration ----------


def test_unknown_email_and_wrong_password_answer_identically(
    client: TestClient, email: str
) -> None:
    register(client, email)

    unknown = login(client, f"unknown-{uuid.uuid4().hex}@example.com")
    wrong = login(client, email, "wrong password, but long")

    # Byte-identical apart from the request ID, which is unique per request by design.
    assert unknown.status_code == 401
    assert without_request_id(unknown) == without_request_id(wrong)
    assert wrong.json()["error"]["code"] == "INVALID_CREDENTIALS"
    assert "set-cookie" not in wrong.headers


def test_unknown_email_is_checked_against_a_dummy_hash(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[str] = []
    monkeypatch.setattr("doctorholiday.api.auth.verify_dummy", calls.append)
    login(client, f"unknown-{uuid.uuid4().hex}@example.com")
    assert calls == [PASSWORD]


def test_duplicate_registration_is_accepted_but_changes_nothing(
    new_client: ClientFactory, email: str, db_engine: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    first = register(new_client(), email)
    hashed: list[str] = []
    monkeypatch.setattr(
        "doctorholiday.api.auth.hash_password",
        lambda password: hashed.append(password) or "$argon2id$unused",
    )
    second = register(new_client(), email, "another password, also long", role="ADMIN")
    monkeypatch.undo()

    assert (second.status_code, second.content) == (first.status_code, first.content) == (202, b"")
    assert set(first.headers) == set(second.headers)
    # Hashed anyway, so the response takes as long as a real registration (BR-02).
    assert hashed == ["another password, also long"]

    client = new_client()
    assert login(client, email, "another password, also long").status_code == 401
    assert login(client, email).status_code == 200
    assert client.get("/api/v1/auth/me").json()["user"]["role"] == "PATIENT"

    user = user_by_email(db_engine, email)
    assert user is not None
    outcomes = [e.outcome for e in audit_events(db_engine, AuditAction.USER_REGISTERED, user)]
    assert outcomes == [AuditOutcome.SUCCESS, AuditOutcome.FAILURE]


def test_deactivated_user_cannot_log_in(client: TestClient, email: str, db_engine: Engine) -> None:
    register(client, email)
    with Session(db_engine) as session, session.begin():
        session.execute(update(User).where(User.email == email).values(is_active=False))

    deactivated = login(client, email)
    wrong = login(client, email, "wrong password, but long")
    assert deactivated.status_code == 401
    assert without_request_id(deactivated) == without_request_id(wrong)


def test_deactivation_ends_existing_sessions(
    client: TestClient, email: str, db_engine: Engine
) -> None:
    registered_and_logged_in(client, email)
    with Session(db_engine) as session, session.begin():
        session.execute(update(User).where(User.email == email).values(is_active=False))
    assert client.get("/api/v1/auth/me").status_code == 401


# ---------- Session cookie and session lifecycle ----------


def test_session_cookie_has_every_flag(client: TestClient, email: str, db_engine: Engine) -> None:
    register(client, email)
    response = login(client, email)

    cookie = response.headers["set-cookie"]
    token = response.cookies[COOKIE_NAME]
    assert cookie == f"{COOKIE_NAME}={token}; {COOKIE_ATTRIBUTES}"
    assert len(token) == 43  # token_urlsafe(32): 256 bits

    # Only the SHA-256 of the token is stored.
    row = session_row(db_engine, token)
    assert row is not None
    assert row.state is SessionState.ACTIVE
    assert token.encode() not in row.token_hash


def test_logged_out_session_is_rejected(
    client: TestClient, new_client: ClientFactory, email: str, db_engine: Engine
) -> None:
    token = registered_and_logged_in(client, email)
    replay = new_client()
    use_cookie(replay, token)
    assert replay.get("/api/v1/auth/me").status_code == 200  # the copied cookie works

    assert client.post("/api/v1/auth/logout").status_code == 204
    assert session_row(db_engine, token) is None

    # Replaying the old cookie from another client does not revive it.
    response = replay.get("/api/v1/auth/me")
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "UNAUTHENTICATED"
    assert replay.post("/api/v1/auth/logout").status_code == 401


def test_planted_session_id_is_not_adopted_at_login(client: TestClient, email: str) -> None:
    """Session fixation: an ID chosen before the login never becomes the session."""
    register(client, email)
    planted = "A" * 43
    use_cookie(client, planted)

    token = login(client, email).cookies[COOKIE_NAME]

    assert token != planted
    use_cookie(client, planted)
    assert client.get("/api/v1/auth/me").status_code == 401


def test_old_session_is_deleted_at_login(client: TestClient, email: str, db_engine: Engine) -> None:
    """A timed-out session sent along with a new login is deleted and not reused."""
    old_token = registered_and_logged_in(client, email)
    change_session(db_engine, old_token, last_seen_at=func.now() - timedelta(days=1))

    new_token = login(client, email).cookies[COOKIE_NAME]

    assert new_token != old_token
    assert session_row(db_engine, old_token) is None
    use_cookie(client, old_token)
    assert client.get("/api/v1/auth/me").status_code == 401


def test_login_and_register_with_a_valid_session_are_forbidden(
    client: TestClient, email: str
) -> None:
    registered_and_logged_in(client, email)

    for response in (login(client, email), register(client, f"other-{email}")):
        assert response.status_code == 403
        assert response.json()["error"]["code"] == "FORBIDDEN"
    assert client.get("/api/v1/auth/me").status_code == 200


def test_sessions_are_independent(new_client: ClientFactory, email: str) -> None:
    """Two devices: logging out on one keeps the other logged in."""
    first, second = new_client(), new_client()
    registered_and_logged_in(first, email)
    assert login(second, email).status_code == 200

    assert first.post("/api/v1/auth/logout").status_code == 204
    assert second.get("/api/v1/auth/me").status_code == 200


def test_idle_timeout(
    client: TestClient, email: str, db_engine: Engine, settings: Settings
) -> None:
    token = registered_and_logged_in(client, email)
    idle = timedelta(minutes=settings.session_idle_timeout_minutes)

    change_session(db_engine, token, last_seen_at=func.now() - idle + timedelta(minutes=1))
    assert client.get("/api/v1/auth/me").status_code == 200

    change_session(db_engine, token, last_seen_at=func.now() - idle - timedelta(seconds=1))
    assert client.get("/api/v1/auth/me").status_code == 401


def test_requests_keep_the_session_alive(
    client: TestClient, email: str, db_engine: Engine, settings: Settings
) -> None:
    token = registered_and_logged_in(client, email)
    idle = timedelta(minutes=settings.session_idle_timeout_minutes)
    change_session(db_engine, token, last_seen_at=func.now() - idle + timedelta(minutes=1))

    assert client.get("/api/v1/auth/me").status_code == 200

    # The request reset the idle timer, so the session survives what would have ended it.
    change_session(db_engine, token, last_seen_at=UserSession.last_seen_at - timedelta(minutes=2))
    assert client.get("/api/v1/auth/me").status_code == 200


def test_absolute_timeout(
    client: TestClient, email: str, db_engine: Engine, settings: Settings
) -> None:
    token = registered_and_logged_in(client, email)
    row = session_row(db_engine, token)
    assert row is not None
    assert row.expires_at - row.created_at == timedelta(
        minutes=settings.session_absolute_timeout_minutes
    )

    # Active the whole time (last_seen_at = now), but past the absolute expiry.
    change_session(
        db_engine,
        token,
        created_at=func.now() - timedelta(days=2),
        expires_at=func.now() - timedelta(seconds=1),
    )
    assert client.get("/api/v1/auth/me").status_code == 401


def test_session_before_mfa_shows_only_its_state(
    client: TestClient, email: str, db_engine: Engine
) -> None:
    """BR-05; with MFA (#21) login creates such sessions, for now the test sets the state."""
    token = registered_and_logged_in(client, email)
    assert client.get("/test/active-user").status_code == 200

    change_session(db_engine, token, state=SessionState.MFA_PENDING)

    assert client.get("/api/v1/auth/me").json() == {"state": "MFA_PENDING"}
    response = client.get("/test/active-user")
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "MFA_REQUIRED"


@pytest.mark.parametrize(
    "cookie", ["", "not-a-token", "A" * 42, "A" * 44, "A" * 42 + "=", "A" * 42 + "+", "A" * 43]
)
def test_malformed_cookie_is_no_session(client: TestClient, cookie: str) -> None:
    use_cookie(client, cookie)
    assert client.get("/api/v1/auth/me").status_code == 401


# ---------- Validation ----------


@pytest.mark.parametrize(
    "body",
    [
        {"email": "patient@example.com", "password": "x" * 11},  # BR-01: at least 12
        {"email": "patient@example.com", "password": "x" * 129},  # at most 128
        {"email": "not-an-email", "password": PASSWORD},
        {"email": "patient@example.com"},
        {"email": "patient@example.com", "password": PASSWORD, "isAdmin": True},
        {"email": "patient@example.com", "password": PASSWORD, "displayName": "<script>"},
        {"email": "patient@example.com", "password": PASSWORD, "role": "SUPERUSER"},
    ],
)
def test_invalid_registration(client: TestClient, body: dict[str, object]) -> None:
    response = client.post("/api/v1/auth/register", json=body)
    assert response.status_code == 422
    assert response.json() == {
        "error": {
            "code": "VALIDATION_ERROR",
            "message": "The request is invalid.",
            "requestId": response.headers["x-request-id"],
        }
    }


def test_password_length_bounds(client: TestClient) -> None:
    for length in (12, 128):
        email = f"len{length}-{uuid.uuid4().hex}@example.com"
        assert register(client, email, "ä" * length).status_code == 202
        assert login(client, email, "ä" * length).status_code == 200
        assert client.post("/api/v1/auth/logout").status_code == 204


# ---------- Audit and logs ----------


def test_audit_events(new_client: ClientFactory, email: str, db_engine: Engine) -> None:
    client = new_client()
    registered_and_logged_in(client, email)
    login(new_client(), email, "wrong password, but long")
    client.post("/api/v1/auth/logout")

    user = user_by_email(db_engine, email)
    assert user is not None
    registered = audit_events(db_engine, AuditAction.USER_REGISTERED, user)
    logins = audit_events(db_engine, AuditAction.LOGIN, user)
    logouts = audit_events(db_engine, AuditAction.LOGOUT, user)

    assert [(e.outcome, e.actor_id) for e in registered] == [(AuditOutcome.SUCCESS, user.id)]
    # The failed login is committed although the request is answered with 401.
    assert [(e.outcome, e.actor_id, e.details) for e in logins] == [
        (AuditOutcome.SUCCESS, user.id, None),
        (AuditOutcome.FAILURE, None, {"reason": "WRONG_PASSWORD"}),
    ]
    assert [(e.outcome, e.actor_id) for e in logouts] == [(AuditOutcome.SUCCESS, user.id)]
    for event in registered + logins + logouts:
        assert email not in json.dumps(event.details or {})


def test_failed_login_for_unknown_email_is_audited_without_the_email(
    client: TestClient, db_engine: Engine
) -> None:
    unknown = f"unknown-{uuid.uuid4().hex}@example.com"
    response = login(client, unknown)

    with Session(db_engine) as session:
        events = session.scalars(
            select(AuditEvent).where(
                AuditEvent.action == AuditAction.LOGIN,
                AuditEvent.outcome == AuditOutcome.FAILURE,
                AuditEvent.details["reason"].astext == "UNKNOWN_ACCOUNT",
                AuditEvent.timestamp >= func.now() - timedelta(minutes=1),
            )
        ).all()
    assert response.status_code == 401
    assert events
    assert all(e.target is None and e.actor_id is None for e in events)
    assert all(unknown not in json.dumps(e.details) for e in events)


def test_secrets_never_appear_in_responses_or_logs(
    new_client: ClientFactory, email: str, db_engine: Engine, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.DEBUG)
    client = new_client()
    responses = [
        register(client, email),
        register(client, email, "second password for the same e-mail"),
        client.post("/api/v1/auth/register", json={"email": email, "password": "too short"}),
        login(client, email, "wrong password, but long"),
        login(client, f"unknown-{uuid.uuid4().hex}@example.com", PASSWORD),
        login(client, email),
    ]
    token = responses[-1].cookies[COOKIE_NAME]
    responses += [client.get("/api/v1/auth/me"), client.post("/api/v1/auth/logout")]

    user = user_by_email(db_engine, email)
    assert user is not None
    with Session(db_engine) as session:
        credential = session.get(Credential, user.id)
    assert credential is not None
    secrets = [
        PASSWORD,
        "second password for the same e-mail",
        "too short",
        "wrong password, but long",
        credential.password_hash,
        credential.password_hash.rsplit("$", 1)[-1],  # the digest alone
    ]

    formatter = JsonFormatter()
    log_text = "\n".join(formatter.format(record) for record in caplog.records)
    assert "login failed" in log_text  # the capture works
    for secret in secrets:
        assert secret not in log_text
        for response in responses:
            assert secret not in response.text
            assert secret not in str(response.headers)
    assert token not in log_text
    assert email not in log_text
