import base64

import pytest

from doctorholiday.config import ConfigError, LogLevel, load_settings

REQUIRED = ["DATABASE_URL", "SESSION_SECRET", "MFA_ENCRYPTION_KEY", "ALLOWED_ORIGINS"]


def test_loads_valid_environment(env: dict[str, str]) -> None:
    settings = load_settings()

    assert settings.port == 8080
    assert settings.log_level is LogLevel.DEBUG
    assert settings.allowed_origins == ["https://doctorholiday.localhost"]
    assert settings.session_secret.get_secret_value() == env["SESSION_SECRET"]


def test_defaults(env: dict[str, str], monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("PORT")
    monkeypatch.delenv("LOG_LEVEL")

    settings = load_settings()

    assert settings.port == 8080
    assert settings.log_level is LogLevel.INFO


def test_secrets_are_masked_in_repr(env: dict[str, str]) -> None:
    text = repr(load_settings())

    assert env["SESSION_SECRET"] not in text
    assert "db-password-sentinel" not in text


@pytest.mark.parametrize("name", REQUIRED)
def test_missing_required_variable(
    env: dict[str, str], monkeypatch: pytest.MonkeyPatch, name: str
) -> None:
    monkeypatch.delenv(name)

    with pytest.raises(ConfigError) as exc_info:
        load_settings()

    assert exc_info.value.errors == [f"{name}: is missing"]


@pytest.mark.parametrize(
    ("name", "value"),
    [
        ("DATABASE_URL", "mysql://dh:invalid-secret-sentinel@db/doctorholiday"),
        ("SESSION_SECRET", "invalid-secret-sentinel"),
        ("MFA_ENCRYPTION_KEY", "invalid-secret-sentinel"),
        # Valid base64, but 23 instead of 32 bytes.
        ("MFA_ENCRYPTION_KEY", base64.urlsafe_b64encode(b"invalid-secret-sentinel").decode()),
        ("ALLOWED_ORIGINS", "*"),
        ("ALLOWED_ORIGINS", "https://*.example.org"),
        ("ALLOWED_ORIGINS", "https://doctorholiday.localhost/app"),
        ("ALLOWED_ORIGINS", "https://user:invalid-secret-sentinel@example.org"),
        ("ALLOWED_ORIGINS", "doctorholiday.localhost"),
        ("ALLOWED_ORIGINS", " , "),
        ("PORT", "80"),
        ("PORT", "invalid-secret-sentinel"),
        ("LOG_LEVEL", "TRACE"),
    ],
)
def test_invalid_value_is_named_but_not_echoed(
    env: dict[str, str], monkeypatch: pytest.MonkeyPatch, name: str, value: str
) -> None:
    monkeypatch.setenv(name, value)

    with pytest.raises(ConfigError) as exc_info:
        load_settings()

    errors = exc_info.value.errors
    assert len(errors) == 1
    assert errors[0].startswith(f"{name}: ")
    assert "invalid-secret-sentinel" not in str(errors)
    assert value not in str(errors)


def test_multiple_origins_are_split_and_normalised(
    env: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("ALLOWED_ORIGINS", "https://a.example.org/, http://localhost:5173")

    assert load_settings().allowed_origins == ["https://a.example.org", "http://localhost:5173"]
