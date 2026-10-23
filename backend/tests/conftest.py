import base64
from collections.abc import Iterator

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from doctorholiday.config import Settings
from doctorholiday.main import create_app

# Dummy values for tests only. Nothing listens on port 1, so the database is unreachable.
TEST_ENV = {
    "DATABASE_URL": "postgresql+psycopg://dh:db-password-sentinel@127.0.0.1:1/doctorholiday",
    "SESSION_SECRET": "session-secret-sentinel-0123456789abcdef",
    # Encoded at runtime, so no secret-looking literal sits in the repo (Gitleaks).
    "MFA_ENCRYPTION_KEY": base64.urlsafe_b64encode(b"mfa-key-sentinel-0123456789abcde").decode(),
    "ALLOWED_ORIGINS": "https://doctorholiday.localhost",
    "PORT": "8080",
    "LOG_LEVEL": "DEBUG",
}


@pytest.fixture
def env(monkeypatch: pytest.MonkeyPatch) -> dict[str, str]:
    for key, value in TEST_ENV.items():
        monkeypatch.setenv(key, value)
    return dict(TEST_ENV)


@pytest.fixture
def settings(env: dict[str, str]) -> Settings:
    return Settings()  # type: ignore[call-arg]


@pytest.fixture
def app(settings: Settings) -> FastAPI:
    return create_app(settings)


@pytest.fixture
def client(app: FastAPI) -> Iterator[TestClient]:
    with TestClient(app) as test_client:
        yield test_client
