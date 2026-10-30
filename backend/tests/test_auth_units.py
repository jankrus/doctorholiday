"""Auth building blocks that need no database; the endpoints are tested in tests/db/test_auth.py."""

import logging
from ipaddress import ip_address

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from doctorholiday.auth.passwords import hash_password, verify_password
from doctorholiday.auth.rate_limiting import account_key, ip_key
from doctorholiday.auth.sessions import hash_token, new_token

PASSWORD = "correct horse battery staple"


def test_password_hash_is_argon2id_and_salted() -> None:
    first, second = hash_password(PASSWORD), hash_password(PASSWORD)

    assert first.startswith("$argon2id$v=19$m=65536,t=3,p=4$")
    assert first != second
    assert verify_password(first, PASSWORD)
    assert not verify_password(first, PASSWORD + " ")
    assert not verify_password(first, PASSWORD.upper())


def test_invalid_stored_hash_fails_closed(caplog: pytest.LogCaptureFixture) -> None:
    broken = "$argon2id$not-a-hash-sentinel"

    with caplog.at_level(logging.WARNING):
        assert not verify_password(broken, PASSWORD)

    assert "not a valid Argon2 hash" in caplog.text
    assert "sentinel" not in caplog.text


def test_tokens_are_random_and_only_their_hash_is_kept() -> None:
    tokens = {new_token() for _ in range(100)}

    assert len(tokens) == 100
    assert all(len(token) == 43 for token in tokens)
    token = tokens.pop()
    assert len(hash_token(token)) == 32
    assert token.encode() not in hash_token(token)


def test_unhandled_exception_answers_with_generic_error(app: FastAPI) -> None:
    @app.get("/test/boom")
    def boom() -> None:
        raise RuntimeError("internal detail sentinel")

    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.get("/test/boom")

    assert response.status_code == 500
    body = response.json()
    assert body["error"]["code"] == "INTERNAL_ERROR"
    assert "sentinel" not in response.text


def test_validation_error_does_not_log_the_input(
    client: TestClient, caplog: pytest.LogCaptureFixture
) -> None:
    # Fails validation before any database access, so no database is needed.
    with caplog.at_level(logging.DEBUG):
        response = client.post(
            "/api/v1/auth/register",
            json={"email": "patient@example.com", "password": "short-secret"[:11]},
        )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"
    assert "request validation failed" in caplog.text
    assert "short-secre" not in caplog.text
    (record,) = [r for r in caplog.records if r.getMessage() == "request validation failed"]
    assert record.fields == [{"loc": ["body", "password"], "type": "too_short"}]


@pytest.mark.parametrize(
    ("ip", "key"),
    [
        ("203.0.113.7", "203.0.113.7"),
        # One IPv6 client usually owns a whole /64.
        ("2001:db8:1:2:3:4:5:6", "2001:db8:1:2::/64"),
        ("2001:db8:1:2:ffff::1", "2001:db8:1:2::/64"),
        ("::ffff:203.0.113.7", "203.0.113.7"),
    ],
)
def test_ip_key(ip: str, key: str) -> None:
    assert ip_key(ip_address(ip)) == key


def test_ip_key_without_a_client_address() -> None:
    assert ip_key(None) == "unknown"


def test_account_key_ignores_case() -> None:
    assert account_key("Patient@Example.COM") == account_key("patient@example.com")
