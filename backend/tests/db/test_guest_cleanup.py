"""Daily erasure of guest contact data (BR-24), #17."""

import itertools
import json
import logging
import uuid
from collections.abc import Iterator
from datetime import timedelta

import pytest
from sqlalchemy import Engine, func, update
from sqlalchemy.orm import Session

from doctorholiday.jobs import guest_cleanup
from doctorholiday.models import Appointment, AppointmentReason, AppointmentStatus, Role, User
from doctorholiday.repositories.appointments import erase_expired_guest_data
from tests.db.conftest import ClientFactory, UserFactory, database_now
from tests.db.helpers import book, get_appointment, new_guest

_HOURS = itertools.count()


def guest_appointment(
    engine: Engine,
    doctor: User,
    staff: User,
    *,
    ended_days_ago: float | None = None,
    cancelled_days_ago: float | None = None,
) -> tuple[uuid.UUID, dict[str, str]]:
    """A guest appointment that ended (or was cancelled) that many days ago; future otherwise.
    Each gets an hour of its own, so they never overlap."""
    guest = new_guest()
    hour = timedelta(hours=next(_HOURS))
    with Session(engine) as session, session.begin():
        ends = (
            func.now()
            + hour
            + (-timedelta(days=ended_days_ago) if ended_days_ago else timedelta(days=3))
        )
        row = Appointment(
            doctor_id=doctor.id,
            starts_at=ends - timedelta(minutes=15),
            ends_at=ends,
            guest_name=guest["name"],
            guest_phone=guest["phone"],
            booked_by_id=staff.id,
            reason=AppointmentReason.OTHER,
        )
        session.add(row)
        session.flush()
        if cancelled_days_ago is not None:
            session.execute(
                update(Appointment)
                .where(Appointment.id == row.id)
                .values(
                    status=AppointmentStatus.CANCELLED,
                    cancelled_at=func.now() - timedelta(days=cancelled_days_ago),
                    cancelled_by_id=staff.id,
                )
            )
        return row.id, guest


def run_cleanup(engine: Engine) -> int:
    with Session(engine) as session, session.begin():
        return erase_expired_guest_data(session)


@pytest.fixture
def restore_logging() -> Iterator[None]:
    """The command configures the root logger (JSON to stdout); undo it for the other tests."""
    root = logging.getLogger()
    saved_handlers, saved_level = root.handlers[:], root.level
    yield
    root.handlers[:] = saved_handlers
    root.setLevel(saved_level)


@pytest.fixture
def doctor(make_committed_user: UserFactory) -> User:
    return make_committed_user(Role.DOCTOR)


@pytest.fixture
def staff(make_committed_user: UserFactory) -> User:
    return make_committed_user(Role.STAFF)


def test_guest_data_is_erased_30_days_after_the_end_or_the_cancellation(
    doctor: User, staff: User, db_engine: Engine
) -> None:
    ended_long_ago, _ = guest_appointment(db_engine, doctor, staff, ended_days_ago=30.01)
    ended_recently, guest = guest_appointment(db_engine, doctor, staff, ended_days_ago=29.9)
    # Cancelled a month ago for a time that is still ahead: the cancellation counts.
    cancelled_long_ago, _ = guest_appointment(db_engine, doctor, staff, cancelled_days_ago=31)
    cancelled_recently, _ = guest_appointment(db_engine, doctor, staff, cancelled_days_ago=1)
    upcoming, _ = guest_appointment(db_engine, doctor, staff)

    assert run_cleanup(db_engine) >= 2

    for erased in (ended_long_ago, cancelled_long_ago):
        row = get_appointment(db_engine, erased)
        assert (row.guest_name, row.guest_phone) == (None, None)
        assert row.guest_erased_at is not None
        # Doctor, time, reason and status stay.
        assert (row.doctor_id, row.reason) == (doctor.id, AppointmentReason.OTHER)
    for kept in (ended_recently, cancelled_recently, upcoming):
        row = get_appointment(db_engine, kept)
        assert row.guest_name is not None
        assert row.guest_erased_at is None
    assert get_appointment(db_engine, ended_recently).guest_phone == guest["phone"]


def test_the_cleanup_is_idempotent_and_leaves_patient_appointments_alone(
    doctor: User, staff: User, make_committed_user: UserFactory, db_engine: Engine
) -> None:
    patient = make_committed_user()
    old_patient_appointment = book(
        db_engine, doctor, patient, database_now(db_engine) - timedelta(days=40)
    )
    erased, _ = guest_appointment(db_engine, doctor, staff, ended_days_ago=40)
    run_cleanup(db_engine)
    first_erasure = get_appointment(db_engine, erased).guest_erased_at

    run_cleanup(db_engine)

    assert get_appointment(db_engine, erased).guest_erased_at == first_erasure
    row = get_appointment(db_engine, old_patient_appointment.id)
    assert (row.patient_id, row.guest_erased_at) == (patient.id, None)


def test_an_erased_guest_appointment_shows_neither_guest_nor_patient(
    client_as: ClientFactory, doctor: User, staff: User, db_engine: Engine
) -> None:
    erased, _ = guest_appointment(db_engine, doctor, staff, ended_days_ago=31)
    run_cleanup(db_engine)

    response = client_as(staff).get("/api/v1/appointments", params={"doctorId": str(doctor.id)})

    [item] = [item for item in response.json()["items"] if item["id"] == str(erased)]
    assert "guest" not in item
    assert "patient" not in item
    assert item["bookedBy"] == "PRACTICE"


def test_the_command_logs_only_the_count(
    doctor: User,
    staff: User,
    db_engine: Engine,
    env: dict[str, str],
    db_url: str,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    restore_logging: None,
) -> None:
    _, guest = guest_appointment(db_engine, doctor, staff, ended_days_ago=31)
    monkeypatch.setenv("DATABASE_URL", db_url)

    assert guest_cleanup.main() == 0

    output = capsys.readouterr()
    text = output.out + output.err
    lines = [json.loads(line) for line in text.splitlines() if line.startswith("{")]
    [finished] = [line for line in lines if line.get("message") == "guest data cleanup finished"]
    assert finished["erasedAppointments"] >= 1
    assert guest["phone"] not in text
    assert guest["name"] not in text


def test_the_command_needs_only_the_database_url(
    doctor: User,
    staff: User,
    db_engine: Engine,
    env: dict[str, str],
    db_url: str,
    monkeypatch: pytest.MonkeyPatch,
    restore_logging: None,
) -> None:
    # Least privilege (AGENTS.md rule 6): the CronJob gets no API secrets.
    guest_appointment(db_engine, doctor, staff, ended_days_ago=31)
    monkeypatch.setenv("DATABASE_URL", db_url)
    for name in ("SESSION_SECRET", "MFA_ENCRYPTION_KEY", "ALLOWED_ORIGINS"):
        monkeypatch.delenv(name)

    assert guest_cleanup.main() == 0


def test_the_command_refuses_an_invalid_configuration(
    env: dict[str, str], monkeypatch: pytest.MonkeyPatch, restore_logging: None
) -> None:
    monkeypatch.setenv("DATABASE_URL", "not a url")

    assert guest_cleanup.main() == 1
