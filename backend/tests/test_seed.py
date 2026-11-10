"""The guards of the dev seed command (#12); seeding itself: tests/db/test_seed.py."""

import pytest

from doctorholiday import seed

LOCAL_URL = "postgresql+psycopg://doctorholiday_app:pw@localhost:5432/doctorholiday"
SEED_PASSWORD = "seed sentinel passphrase"


@pytest.fixture
def seed_env(monkeypatch: pytest.MonkeyPatch) -> pytest.MonkeyPatch:
    for name in ("DATABASE_URL", "SEED_DEV_DATA", "SEED_PASSWORD"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("DATABASE_URL", LOCAL_URL)
    monkeypatch.setenv("SEED_DEV_DATA", "true")
    monkeypatch.setenv("SEED_PASSWORD", SEED_PASSWORD)
    return monkeypatch


def _refusal(capsys: pytest.CaptureFixture[str]) -> str:
    assert seed.main() == 2
    out, err = capsys.readouterr()
    assert out == ""
    assert SEED_PASSWORD not in err
    assert "pw@" not in err
    return err


@pytest.mark.parametrize("value", [None, "false", "0"])
def test_refused_without_the_flag(
    seed_env: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], value: str | None
) -> None:
    if value is None:
        seed_env.delenv("SEED_DEV_DATA")
    else:
        seed_env.setenv("SEED_DEV_DATA", value)
    assert "SEED_DEV_DATA" in _refusal(capsys)


@pytest.mark.parametrize(
    "host", ["postgres.doctorholiday.svc.cluster.local", "db", "10.0.0.5", "localhost.evil.com"]
)
def test_refused_for_a_database_elsewhere(
    seed_env: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], host: str
) -> None:
    seed_env.setenv("DATABASE_URL", LOCAL_URL.replace("localhost", host))
    assert "localhost" in _refusal(capsys)


@pytest.mark.parametrize("password", ["too short", "qwerty123456", "dev-admin@example.com"])
def test_refused_for_a_weak_password(
    seed_env: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], password: str
) -> None:
    seed_env.setenv("SEED_PASSWORD", password)
    err = _refusal(capsys)
    assert "SEED_PASSWORD" in err
    assert password not in err


def test_refused_without_a_password(
    seed_env: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    seed_env.delenv("SEED_PASSWORD")
    assert "SEED_PASSWORD" in _refusal(capsys)


@pytest.mark.parametrize("host", ["localhost", "127.0.0.1", "[::1]"])
def test_local_databases_are_allowed(seed_env: pytest.MonkeyPatch, host: str) -> None:
    seed_env.setenv("DATABASE_URL", LOCAL_URL.replace("localhost", host))
    seed.check_allowed(seed.SeedSettings())  # type: ignore[call-arg]
