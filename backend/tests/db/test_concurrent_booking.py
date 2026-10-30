"""BR-09 / #12: concurrent bookings of overlapping times for one doctor fail at database level.

These tests commit for real, in separate connections, like concurrent requests do.
"""

import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import Engine, select, text
from sqlalchemy.orm import Session

from doctorholiday.models import Appointment, AppointmentReason, Role, User
from doctorholiday.repositories.appointments import book_appointment
from doctorholiday.repositories.errors import TimeAlreadyBookedError
from tests.db.conftest import UserFactory

NINE = datetime(2030, 1, 7, 9, 0, tzinfo=UTC)
SLOT = timedelta(minutes=15)


def _book_and_commit(
    engine: Engine, doctor: User, patient: User, starts_at: datetime, ready: threading.Barrier
) -> str:
    try:
        with Session(engine) as session, session.begin():
            ready.wait(timeout=5)
            book_appointment(
                session,
                doctor_id=doctor.id,
                starts_at=starts_at,
                ends_at=starts_at + SLOT,
                booked_by_id=patient.id,
                reason=AppointmentReason.CHECKUP,
                patient_id=patient.id,
            )
    except TimeAlreadyBookedError:
        return "conflict"
    return "booked"


def _booked_count(engine: Engine, doctor: User) -> int:
    with Session(engine) as session:
        return len(
            session.scalars(select(Appointment).where(Appointment.doctor_id == doctor.id)).all()
        )


def _wait_until_blocked_on_a_lock(engine: Engine) -> None:
    """Wait until another session of the application role waits for a row/transaction lock."""
    deadline = time.monotonic() + 5
    with engine.connect() as connection:
        while time.monotonic() < deadline:
            waiting = connection.execute(
                text(
                    "SELECT count(*) FROM pg_stat_activity "
                    "WHERE usename = current_user AND wait_event_type = 'Lock'"
                )
            ).scalar_one()
            if waiting:
                return
            time.sleep(0.02)
    pytest.fail("the second booking never waited for the first transaction")


@pytest.mark.parametrize("attempts", [2, 5])
def test_only_one_of_several_concurrent_overlapping_bookings_succeeds(
    db_engine: Engine, make_committed_user: UserFactory, attempts: int
) -> None:
    doctor = make_committed_user(Role.DOCTOR)
    patients = [make_committed_user() for _ in range(attempts)]
    ready = threading.Barrier(attempts)
    # Every pair overlaps: the starts differ by less than one slot.
    starts = [NINE + timedelta(minutes=i) for i in range(attempts)]

    with ThreadPoolExecutor(max_workers=attempts) as pool:
        results = list(
            pool.map(
                lambda i: _book_and_commit(db_engine, doctor, patients[i], starts[i], ready),
                range(attempts),
            )
        )

    assert sorted(results) == ["booked"] + ["conflict"] * (attempts - 1)
    assert _booked_count(db_engine, doctor) == 1


@pytest.mark.parametrize(
    ("first_commits", "second_result"), [(True, "conflict"), (False, "booked")]
)
def test_overlapping_booking_waits_for_the_open_transaction(
    db_engine: Engine, make_committed_user: UserFactory, first_commits: bool, second_result: str
) -> None:
    doctor, patient = make_committed_user(Role.DOCTOR), make_committed_user()
    no_wait = threading.Barrier(1)

    with Session(db_engine) as first, ThreadPoolExecutor(max_workers=1) as pool:
        first.begin()
        book_appointment(
            first,
            doctor_id=doctor.id,
            starts_at=NINE,
            ends_at=NINE + SLOT,
            booked_by_id=patient.id,
            reason=AppointmentReason.CHECKUP,
            patient_id=patient.id,
        )
        second = pool.submit(
            _book_and_commit, db_engine, doctor, patient, NINE + timedelta(minutes=5), no_wait
        )

        # The database holds the second insert until the first transaction ends.
        _wait_until_blocked_on_a_lock(db_engine)
        assert not second.done()
        if first_commits:
            first.commit()
        else:
            first.rollback()

        assert second.result(timeout=5) == second_result
    assert _booked_count(db_engine, doctor) == 1
