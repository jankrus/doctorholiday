"""Application settings, loaded only from environment variables (AGENTS.md rule 1).

The process fails fast at startup if a variable is missing or invalid. Error messages name the
variable and the problem, never the value, because the value may be a secret.
"""

import base64
import binascii
import re
from enum import StrEnum
from typing import Annotated
from urllib.parse import urlsplit

from pydantic import Field, SecretStr, ValidationError, ValidationInfo, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

_FERNET_KEY = re.compile(r"^[A-Za-z0-9_-]{43}=$")


class LogLevel(StrEnum):
    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"


class Settings(BaseSettings):
    # No env_file: in the cluster the variables come from Kubernetes Secrets, locally from
    # `uv run --env-file .env` (see backend/README.md).
    model_config = SettingsConfigDict(frozen=True, extra="ignore")

    database_url: SecretStr
    session_secret: SecretStr
    mfa_encryption_key: SecretStr
    allowed_origins: Annotated[list[str], NoDecode]
    port: int = Field(default=8080, ge=1024, le=65535)
    log_level: LogLevel = LogLevel.INFO
    # Login sessions (#14): ended after this long without a request (idle) and at the latest this
    # long after the login (absolute), whatever the activity.
    session_idle_timeout_minutes: int = Field(default=30, ge=1, le=1440)
    session_absolute_timeout_minutes: int = Field(default=480, ge=1, le=10080)
    # Login rate limiting (#14, auth/throttling.py): this many failed logins per e-mail address
    # or per client IP within the window lock that key for the lockout time. The IP limit is
    # higher because a practice or household shares one IP behind NAT.
    login_max_failures_per_account: int = Field(default=5, ge=1, le=100)
    login_max_failures_per_ip: int = Field(default=20, ge=1, le=1000)
    login_failure_window_minutes: int = Field(default=15, ge=1, le=1440)
    login_lockout_minutes: int = Field(default=15, ge=1, le=1440)

    @field_validator("database_url")
    @classmethod
    def _check_database_url(cls, value: SecretStr) -> SecretStr:
        if not value.get_secret_value().startswith("postgresql+psycopg://"):
            raise ValueError("must start with postgresql+psycopg://")
        return value

    @field_validator("session_secret")
    @classmethod
    def _check_session_secret(cls, value: SecretStr) -> SecretStr:
        if len(value.get_secret_value()) < 32:
            raise ValueError("must be at least 32 characters long")
        return value

    @field_validator("mfa_encryption_key")
    @classmethod
    def _check_mfa_encryption_key(cls, value: SecretStr) -> SecretStr:
        raw = value.get_secret_value()
        try:
            valid = bool(_FERNET_KEY.match(raw)) and len(base64.urlsafe_b64decode(raw)) == 32
        except (binascii.Error, ValueError):
            valid = False
        if not valid:
            raise ValueError("must be 32 random bytes, base64url-encoded with padding (44 chars)")
        return value

    @field_validator("session_absolute_timeout_minutes")
    @classmethod
    def _check_absolute_timeout(cls, value: int, info: ValidationInfo) -> int:
        idle = info.data.get("session_idle_timeout_minutes")  # absent if itself invalid
        if idle is not None and value < idle:
            raise ValueError("must not be shorter than SESSION_IDLE_TIMEOUT_MINUTES")
        return value

    @field_validator("allowed_origins", mode="before")
    @classmethod
    def _split_origins(cls, value: object) -> object:
        if isinstance(value, str):
            return [origin.strip() for origin in value.split(",") if origin.strip()]
        return value

    @field_validator("allowed_origins")
    @classmethod
    def _check_origins(cls, value: list[str]) -> list[str]:
        if not value:
            raise ValueError("must contain at least one origin")
        for origin in value:
            parts = urlsplit(origin)
            if (
                parts.scheme not in ("http", "https")
                or not parts.hostname
                or "*" in origin
                or parts.username is not None
                or parts.path not in ("", "/")
                or parts.query
                or parts.fragment
            ):
                raise ValueError("must be a comma-separated list of http(s)://host[:port] origins")
        return [origin.rstrip("/") for origin in value]


class ConfigError(Exception):
    """Invalid configuration. `errors` is safe to log: variable names and reasons only."""

    def __init__(self, errors: list[str]) -> None:
        super().__init__("invalid configuration")
        self.errors = errors


def load_settings() -> Settings:
    try:
        return Settings()  # type: ignore[call-arg]  # fields are filled from the environment
    except ValidationError as exc:
        # Only `loc` and `msg`: pydantic's default string form also contains the input value.
        errors = [
            f"{str(error['loc'][0]).upper()}: "
            + ("is missing" if error["type"] == "missing" else error["msg"])
            for error in exc.errors(include_input=False, include_url=False)
        ]
        raise ConfigError(errors) from None
