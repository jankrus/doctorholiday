"""Register, login, logout, /me, login rate limiting (#14) and the first-admin bootstrap (#15)
against a real database.

The app commits for real; every test uses its own e-mail addresses, and the database is thrown
away after `make test-db`.
"""

import hashlib
import json
import logging
import random
import threading
import uuid
from collections.abc import Callable, Iterator
from concurrent.futures import ThreadPoolExecutor
from contextlib import ExitStack
from datetime import datetime, timedelta

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from httpx2 import Response
from sqlalchemy import ColumnElement, Engine, and_, func, select, update
from sqlalchemy.orm import Session

from doctorholiday.auth.dependencies import ActiveUser
from doctorholiday.auth.sessions import COOKIE_NAME
from doctorholiday.config import Settings
from doctorholiday.logs import JsonFormatter
from doctorholiday.main import create_app
from doctorholiday.models import (
    AdminBootstrap,
    AuditAction,
    AuditEvent,
    AuditOutcome,
    Credential,
    RateLimit,
    RateLimitScope,
    Role,
    SessionState,
    User,
    UserSession,
)
from tests import contract
from tests.db.conftest import UserFactory

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


def set_bootstrap(engine: Engine, admin_id: uuid.UUID | None) -> None:
    """Mark the first-admin bootstrap as done by `admin_id`, or as not done yet (None)."""
    with Session(engine) as session, session.begin():
        session.execute(
            update(AdminBootstrap)
            .where(AdminBootstrap.id == 1)
            .values(
                bootstrapped=admin_id is not None,
                admin_id=admin_id,
                bootstrapped_at=None if admin_id is None else func.now(),
            )
        )


def bootstrap_row(engine: Engine) -> AdminBootstrap:
    with Session(engine) as session:
        return session.get_one(AdminBootstrap, 1)


@pytest.fixture(autouse=True)
def bootstrapped_admin(db_engine: Engine, make_committed_user: UserFactory) -> Iterator[User]:
    """The admin of an already bootstrapped system, as after the operator's first login or
    `make -C backend seed`, so the logins of the tests keep their role.

    Restored afterwards, because test_seed.py expects the state of a fresh database.
    """
    before = bootstrap_row(db_engine)
    admin = make_committed_user(Role.ADMIN)
    set_bootstrap(db_engine, admin.id)
    yield admin
    with Session(db_engine) as session, session.begin():
        session.execute(
            update(AdminBootstrap)
            .where(AdminBootstrap.id == 1)
            .values(
                bootstrapped=before.bootstrapped,
                admin_id=before.admin_id,
                bootstrapped_at=before.bootstrapped_at,
            )
        )


@pytest.fixture
def client_ip() -> str:
    """An IP of its own per test, so failed logins of other tests never hit its IP limit."""
    return f"10.{random.randrange(256)}.{random.randrange(256)}.{random.randrange(1, 255)}"  # noqa: S311


@pytest.fixture
def new_client(app: FastAPI, client_ip: str) -> Iterator[ClientFactory]:
    """Independent clients (own cookie jar), e.g. two browsers on the same machine (one IP).
    https: the cookie is Secure."""
    with ExitStack() as stack:
        yield lambda: contract.install(
            stack.enter_context(
                TestClient(app, base_url="https://testserver", client=(client_ip, 50000))
            )
        )


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
def test_registration_with_a_role_is_rejected(
    client: TestClient, email: str, db_engine: Engine, role: Role
) -> None:
    """BR-02: no role can be chosen at registration, not even PATIENT (extra="forbid")."""
    response = register(client, email, role=role.value)
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"
    assert user_by_email(db_engine, email) is None


def test_email_is_case_insensitive(client: TestClient, email: str) -> None:
    assert register(client, email).status_code == 202
    assert login(client, email.upper()).status_code == 200


def test_email_is_stored_trimmed_and_lowercased(
    client: TestClient, email: str, db_engine: Engine
) -> None:
    assert register(client, f"  {email.upper()} ").status_code == 202

    user = user_by_email(db_engine, email)
    assert user is not None
    assert user.email == email
    assert login(client, f" {email} ").status_code == 200
    assert client.get("/api/v1/auth/me").json()["user"]["email"] == email


def test_unknown_field_in_login_is_rejected(client: TestClient, email: str) -> None:
    response = client.post(
        "/api/v1/auth/login", json={"email": email, "password": PASSWORD, "isAdmin": True}
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


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
    second = register(new_client(), email, "another password, also long")
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


# ---------- Rate limiting and lockout ----------

WRONG = "wrong password, but long"
LOGIN_LOCKOUT = timedelta(minutes=15)
REGISTRATION_WINDOW = timedelta(minutes=60)


def unknown_email() -> str:
    return f"unknown-{uuid.uuid4().hex}@example.com"


def _is_counter(scope: RateLimitScope, key: str) -> ColumnElement[bool]:
    return and_(
        RateLimit.scope == scope, RateLimit.key_hash == hashlib.sha256(key.encode()).digest()
    )


def counter_row(
    engine: Engine, key: str, scope: RateLimitScope = RateLimitScope.LOGIN_ACCOUNT
) -> RateLimit | None:
    # Looked up by SHA-256: the table has no column for the clear text.
    with Session(engine) as session:
        return session.scalars(select(RateLimit).where(_is_counter(scope, key))).one_or_none()


def move_counter_back(
    engine: Engine,
    key: str,
    by: timedelta,
    scope: RateLimitScope = RateLimitScope.LOGIN_ACCOUNT,
) -> None:
    """Let `by` pass for one counter, as if its attempts and lockout were that much older."""
    with Session(engine) as session, session.begin():
        session.execute(
            update(RateLimit)
            .where(_is_counter(scope, key))
            .values(
                window_started_at=RateLimit.window_started_at - by,
                locked_until=RateLimit.locked_until - by,
            )
        )


def assert_rate_limited(response: Response, max_retry_after: timedelta = LOGIN_LOCKOUT) -> None:
    assert response.status_code == 429
    assert response.json()["error"]["code"] == "RATE_LIMITED"
    assert 1 <= int(response.headers["retry-after"]) <= max_retry_after.total_seconds()
    assert "set-cookie" not in response.headers


def test_sixth_rapid_failed_login_returns_429(client: TestClient, email: str) -> None:
    register(client, email)
    for _ in range(5):
        assert login(client, email, WRONG).status_code == 401

    assert_rate_limited(login(client, email, WRONG))
    # Locked means locked: not even the right password is checked.
    assert_rate_limited(login(client, email))


def test_lockout_is_per_account_across_ips(
    new_client: ClientFactory, app: FastAPI, email: str
) -> None:
    register(new_client(), email)
    for attempt in range(5):
        ip = f"10.1.0.{attempt}"
        with TestClient(app, base_url="https://testserver", client=(ip, 1)) as other:
            assert login(other, email, WRONG).status_code == 401

    assert_rate_limited(login(new_client(), email))


def test_lockout_of_unknown_and_known_emails_answers_identically(
    client: TestClient, email: str
) -> None:
    register(client, email)
    unknown = unknown_email()
    for _ in range(5):
        login(client, email, WRONG)
        login(client, unknown, WRONG)

    known_response = login(client, email, WRONG)
    unknown_response = login(client, unknown, WRONG)
    assert_rate_limited(known_response)
    # Retry-After may differ by a second, the rest is identical.
    known_status, known_headers, known_body = without_request_id(known_response)
    unknown_status, unknown_headers, unknown_body = without_request_id(unknown_response)
    assert (known_status, known_body) == (unknown_status, unknown_body)
    assert known_headers.keys() == unknown_headers.keys()


def test_lockout_counts_case_variants_of_an_email_together(client: TestClient, email: str) -> None:
    register(client, email)
    for _ in range(5):
        login(client, email.upper(), WRONG)
    assert_rate_limited(login(client, email))


def test_lockout_ends_after_the_lockout_time(
    client: TestClient, email: str, db_engine: Engine
) -> None:
    register(client, email)
    for _ in range(5):
        login(client, email, WRONG)
    assert_rate_limited(login(client, email))

    move_counter_back(db_engine, email, timedelta(minutes=15))
    assert login(client, email).status_code == 200
    # A successful login resets the account counter.
    assert counter_row(db_engine, email) is None


def test_failure_right_after_a_lockout_locks_again(
    client: TestClient, email: str, db_engine: Engine
) -> None:
    register(client, email)
    for _ in range(5):
        login(client, email, WRONG)
    # Lockout over, but the failures are still inside a (longer) window: one guess per lockout.
    with Session(db_engine) as session, session.begin():
        session.execute(
            update(RateLimit)
            .where(_is_counter(RateLimitScope.LOGIN_ACCOUNT, email))
            .values(locked_until=func.now())
        )
    assert login(client, email, WRONG).status_code == 401
    assert_rate_limited(login(client, email))


def test_failures_outside_the_window_are_forgotten(
    client: TestClient, email: str, db_engine: Engine
) -> None:
    register(client, email)
    for _ in range(4):
        login(client, email, WRONG)
    move_counter_back(db_engine, email, timedelta(minutes=15))

    for _ in range(4):
        assert login(client, email, WRONG).status_code == 401
    assert login(client, email).status_code == 200


def test_successful_login_resets_the_account_counter(client: TestClient, email: str) -> None:
    register(client, email)
    for _ in range(4):
        login(client, email, WRONG)
    assert login(client, email).status_code == 200
    client.post("/api/v1/auth/logout")

    for _ in range(4):
        assert login(client, email, WRONG).status_code == 401
    assert login(client, email).status_code == 200


def test_ip_limit_spans_accounts(new_client: ClientFactory, email: str) -> None:
    client = new_client()
    register(client, email)
    # 20 failed logins from one IP, each for another e-mail: no account counter is near its limit.
    for _ in range(20):
        assert login(client, unknown_email(), WRONG).status_code == 401

    assert_rate_limited(login(client, email))
    # A successful login does not reset the IP counter; it never happens while locked anyway.
    assert_rate_limited(login(new_client(), unknown_email(), WRONG))


def test_ip_limit_does_not_touch_other_ips(
    new_client: ClientFactory, app: FastAPI, email: str
) -> None:
    client = new_client()
    register(client, email)
    for _ in range(20):
        login(client, unknown_email(), WRONG)

    with TestClient(app, base_url="https://testserver", client=("10.255.255.254", 1)) as other:
        assert login(other, email).status_code == 200


def test_successful_login_does_not_reset_the_ip_counter(client: TestClient) -> None:
    accounts = [f"patient-{uuid.uuid4().hex}@example.com" for _ in range(4)]
    for account in accounts:
        register(client, account)
    # 4 failures per account, then a successful login that resets only the account counter.
    for account in accounts:
        for _ in range(4):
            assert login(client, account, WRONG).status_code == 401
        assert login(client, account).status_code == 200
        client.post("/api/v1/auth/logout")
    # 16 failures from this IP so far; 4 more reach the IP limit.
    for _ in range(4):
        assert login(client, unknown_email(), WRONG).status_code == 401

    assert_rate_limited(login(client, accounts[0]))


def test_concurrent_failed_logins_cannot_exceed_the_limit(
    app: FastAPI, client_ip: str, email: str
) -> None:
    ready = threading.Barrier(10)

    def attempt(_: int) -> int:
        # No `with`: leaving it would run the lifespan shutdown while other threads still work.
        client = TestClient(app, base_url="https://testserver", client=(client_ip, 1))
        ready.wait(timeout=10)
        return login(client, email, WRONG).status_code

    # The outer client's lifespan closes the pooled connections once all threads are done.
    with TestClient(app, base_url="https://testserver", client=(client_ip, 1)) as client:
        register(client, email)
        with ThreadPoolExecutor(max_workers=10) as pool:
            statuses = sorted(pool.map(attempt, range(10)))

    assert statuses == [401] * 5 + [429] * 5


def test_rate_limited_login_is_audited(
    client: TestClient, email: str, db_engine: Engine, client_ip: str
) -> None:
    register(client, email)
    for _ in range(6):
        login(client, email, WRONG)

    user = user_by_email(db_engine, email)
    assert user is not None
    reasons = [e.details for e in audit_events(db_engine, AuditAction.LOGIN, user)]
    assert reasons == [{"reason": "WRONG_PASSWORD"}] * 5 + [{"reason": "RATE_LIMITED"}]
    assert {str(e.ip) for e in audit_events(db_engine, AuditAction.LOGIN, user)} == {client_ip}


def test_counters_are_keyed_by_hashes_only(
    client: TestClient, email: str, db_engine: Engine, client_ip: str
) -> None:
    login(client, email, WRONG)
    account = counter_row(db_engine, email)
    ip = counter_row(db_engine, client_ip, RateLimitScope.LOGIN_IP)
    assert account is not None
    assert account.attempts == 1
    assert ip is not None
    assert ip.attempts == 1


def test_stale_counters_are_deleted(client: TestClient, email: str, db_engine: Engine) -> None:
    login(client, email, WRONG)
    move_counter_back(db_engine, email, timedelta(minutes=15))

    login(client, unknown_email(), WRONG)
    assert counter_row(db_engine, email) is None


def test_eleventh_registration_from_one_ip_returns_429(
    client: TestClient, db_engine: Engine
) -> None:
    taken = f"patient-{uuid.uuid4().hex}@example.com"
    assert register(client, taken).status_code == 202
    for _ in range(9):
        assert register(client, f"patient-{uuid.uuid4().hex}@example.com").status_code == 202

    # New and taken e-mails alike: the limit reveals no accounts.
    fresh = f"patient-{uuid.uuid4().hex}@example.com"
    assert_rate_limited(register(client, fresh), REGISTRATION_WINDOW)
    assert_rate_limited(register(client, taken), REGISTRATION_WINDOW)
    assert user_by_email(db_engine, fresh) is None


def test_registration_limit_is_per_ip(new_client: ClientFactory, app: FastAPI) -> None:
    client = new_client()
    for _ in range(10):
        register(client, f"patient-{uuid.uuid4().hex}@example.com")
    assert_rate_limited(
        register(client, f"patient-{uuid.uuid4().hex}@example.com"), REGISTRATION_WINDOW
    )

    with TestClient(app, base_url="https://testserver", client=("10.255.255.253", 1)) as other:
        assert register(other, f"patient-{uuid.uuid4().hex}@example.com").status_code == 202


def test_registration_limit_ends_after_the_window(
    client: TestClient, db_engine: Engine, client_ip: str
) -> None:
    for _ in range(10):
        register(client, f"patient-{uuid.uuid4().hex}@example.com")
    move_counter_back(db_engine, client_ip, REGISTRATION_WINDOW, RateLimitScope.REGISTRATION_IP)

    assert register(client, f"patient-{uuid.uuid4().hex}@example.com").status_code == 202


def test_registration_and_login_have_separate_counters(client: TestClient, email: str) -> None:
    register(client, email)
    for _ in range(9):
        register(client, f"patient-{uuid.uuid4().hex}@example.com")

    assert login(client, email).status_code == 200


def test_rate_limited_registration_is_audited(
    client: TestClient, db_engine: Engine, client_ip: str
) -> None:
    for _ in range(11):
        register(client, f"patient-{uuid.uuid4().hex}@example.com")

    with Session(db_engine) as session:
        events = session.scalars(
            select(AuditEvent).where(
                AuditEvent.action == AuditAction.USER_REGISTERED,
                AuditEvent.ip == client_ip,
            )
        ).all()
    assert sorted(e.details["reason"] for e in events if e.details) == ["RATE_LIMITED"]
    assert [e.target for e in events if e.details] == [None]
    assert len([e for e in events if e.outcome is AuditOutcome.SUCCESS]) == 10


# ---------- First-admin bootstrap (#15) ----------


@pytest.fixture
def unbootstrapped(db_engine: Engine, bootstrapped_admin: User) -> None:
    """No account has become admin yet, as on a freshly deployed system."""
    set_bootstrap(db_engine, None)


def database_now(engine: Engine) -> datetime:
    with Session(engine) as session:
        return session.execute(select(func.now())).scalar_one()


def bootstrap_events_since(engine: Engine, since: datetime) -> list[AuditEvent]:
    """Every ADMIN_BOOTSTRAPPED event since `since`, whatever its target."""
    with Session(engine) as session:
        return list(
            session.scalars(
                select(AuditEvent).where(
                    AuditEvent.action == AuditAction.ADMIN_BOOTSTRAPPED,
                    AuditEvent.timestamp >= since,
                )
            )
        )


def role_of(engine: Engine, email: str) -> Role:
    user = user_by_email(engine, email)
    assert user is not None
    return user.role


def logged_in_role(client: TestClient, email: str) -> str:
    response = login(client, email)
    assert response.status_code == 200
    me = client.get("/api/v1/auth/me").json()
    assert me["user"]["role"] == response.json()["user"]["role"]
    return me["user"]["role"]


@pytest.mark.usefixtures("unbootstrapped")
def test_first_login_becomes_admin_and_later_logins_keep_their_role(
    new_client: ClientFactory, db_engine: Engine, client_ip: str
) -> None:
    since = database_now(db_engine)
    a, b = (f"first-{name}-{uuid.uuid4().hex}@example.com" for name in "ab")
    client = new_client()
    assert register(client, a).status_code == 202
    assert register(client, b).status_code == 202
    # Registration never creates an admin, not even on an empty system (BR-02).
    assert role_of(db_engine, a) == role_of(db_engine, b) == Role.PATIENT

    # The login response and /me show the new role right away.
    assert logged_in_role(new_client(), a) == "ADMIN"
    assert logged_in_role(new_client(), b) == "PATIENT"
    assert logged_in_role(new_client(), a) == "ADMIN"

    admin = user_by_email(db_engine, a)
    assert admin is not None
    assert role_of(db_engine, b) == Role.PATIENT
    bootstrap = bootstrap_row(db_engine)
    assert (bootstrap.bootstrapped, bootstrap.admin_id) == (True, admin.id)
    assert bootstrap.bootstrapped_at is not None
    assert since <= bootstrap.bootstrapped_at <= database_now(db_engine)

    [event] = bootstrap_events_since(db_engine, since)
    assert (event.outcome, event.actor_id, event.target) == (
        AuditOutcome.SUCCESS,
        admin.id,
        f"user:{admin.id}",
    )
    assert str(event.ip) == client_ip
    assert event.details is None


@pytest.mark.usefixtures("unbootstrapped")
def test_concurrent_first_logins_promote_exactly_one(app: FastAPI, db_engine: Engine) -> None:
    since = database_now(db_engine)
    emails = [f"race-{i}-{uuid.uuid4().hex}@example.com" for i in range(10)]
    # One IP per login, so the logins share no rate limit counter and meet only at the bootstrap
    # row (one shared IP counter would serialize them before it).
    subnet = f"10.{random.randrange(256)}.{random.randrange(256)}"  # noqa: S311
    ready = threading.Barrier(10)

    def attempt(i: int) -> int:
        # No `with`: leaving it would run the lifespan shutdown while other threads still work.
        client = TestClient(app, base_url="https://testserver", client=(f"{subnet}.{i + 1}", 1))
        ready.wait(timeout=10)
        return login(client, emails[i]).status_code

    # The outer client's lifespan closes the pooled connections once all threads are done.
    with TestClient(app, base_url="https://testserver", client=(f"{subnet}.100", 1)) as client:
        for email in emails:
            assert register(client, email).status_code == 202
        with ThreadPoolExecutor(max_workers=10) as pool:
            statuses = list(pool.map(attempt, range(10)))

    # No deadlock and no lost login: every one succeeds.
    assert statuses == [200] * 10
    roles = [role_of(db_engine, email) for email in emails]
    assert sorted(roles) == [Role.ADMIN] + [Role.PATIENT] * 9
    admin = user_by_email(db_engine, emails[roles.index(Role.ADMIN)])
    assert admin is not None
    assert bootstrap_row(db_engine).admin_id == admin.id
    assert [event.target for event in bootstrap_events_since(db_engine, since)] == [
        f"user:{admin.id}"
    ]


def _wrong_password(client: TestClient, email: str, db_engine: Engine) -> Response:
    return login(client, email, WRONG)


def _inactive(client: TestClient, email: str, db_engine: Engine) -> Response:
    with Session(db_engine) as session, session.begin():
        session.execute(update(User).where(User.email == email).values(is_active=False))
    return login(client, email)


def _rate_limited(client: TestClient, email: str, db_engine: Engine) -> Response:
    for _ in range(5):
        login(client, email, WRONG)
    return login(client, email)  # the correct password, but locked


@pytest.mark.usefixtures("unbootstrapped")
@pytest.mark.parametrize(
    ("failed_login", "expected_status"),
    [(_wrong_password, 401), (_inactive, 401), (_rate_limited, 429)],
    ids=["wrong-password", "inactive", "rate-limited"],
)
def test_failed_login_does_not_bootstrap(
    new_client: ClientFactory,
    email: str,
    db_engine: Engine,
    failed_login: Callable[[TestClient, str, Engine], Response],
    expected_status: int,
) -> None:
    since = database_now(db_engine)
    client = new_client()
    register(client, email)

    assert failed_login(client, email, db_engine).status_code == expected_status

    assert role_of(db_engine, email) == Role.PATIENT
    assert not bootstrap_row(db_engine).bootstrapped
    assert bootstrap_events_since(db_engine, since) == []

    # The bootstrap is still open for the next successful login.
    other = f"next-{uuid.uuid4().hex}@example.com"
    register(client, other)
    assert logged_in_role(new_client(), other) == "ADMIN"


def test_bootstrapped_system_promotes_no_one(
    client: TestClient, email: str, db_engine: Engine, bootstrapped_admin: User
) -> None:
    """E.g. a seeded database: `make -C backend seed` records its admin as bootstrapped."""
    since = database_now(db_engine)
    before = bootstrap_row(db_engine)
    register(client, email)

    assert logged_in_role(client, email) == "PATIENT"

    after = bootstrap_row(db_engine)
    assert (after.admin_id, after.bootstrapped_at) == (
        bootstrapped_admin.id,
        before.bootstrapped_at,
    )
    assert bootstrap_events_since(db_engine, since) == []


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


@pytest.mark.parametrize(
    "password",
    [
        "qwerty123456",  # on the blocklist
        "Password1234",  # on the blocklist, in another case
        "my doctor holiday password",  # the service name
        "{email} is mine",  # the account's e-mail address
    ],
)
def test_common_password_is_rejected(
    client: TestClient,
    email: str,
    db_engine: Engine,
    password: str,
    caplog: pytest.LogCaptureFixture,
) -> None:
    password = password.format(email=email.upper())
    with caplog.at_level(logging.DEBUG):
        response = register(client, email, password)

    assert response.status_code == 422
    assert response.json() == {
        "error": {
            "code": "PASSWORD_TOO_COMMON",
            "message": "This password is too common. Please choose another one.",
            "requestId": response.headers["x-request-id"],
        }
    }
    assert user_by_email(db_engine, email) is None
    assert password not in caplog.text


def test_common_password_is_rejected_for_a_taken_email_too(client: TestClient, email: str) -> None:
    # The answer does not depend on the e-mail, so it reveals no accounts.
    assert register(client, email).status_code == 202
    assert register(client, email, "qwerty123456").status_code == 422


def test_rejected_common_passwords_count_against_the_registration_limit(
    client: TestClient,
) -> None:
    for _ in range(10):
        register(client, f"patient-{uuid.uuid4().hex}@example.com", "qwerty123456")
    assert_rate_limited(
        register(client, f"patient-{uuid.uuid4().hex}@example.com"), REGISTRATION_WINDOW
    )


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
