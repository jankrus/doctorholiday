"""Helpers for the schedule and appointment API tests (#17): rows written directly, committed."""

import uuid
from datetime import UTC, date, datetime, time, timedelta

from sqlalchemy import Engine, select
from sqlalchemy.orm import Session

from doctorholiday.models import (
    Absence,
    Appointment,
    AppointmentReason,
    AuditAction,
    AuditEvent,
    User,
    WorkingHours,
)
from doctorholiday.repositories.appointments import book_appointment
from doctorholiday.scheduling import PRACTICE_TIME_ZONE as BERLIN
from tests.db.conftest import database_now


def iso(value: datetime) -> str:
    """The contract's Timestamp as the server returns it: UTC with `Z`."""
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def at(day: date, hour: int, minute: int = 0) -> datetime:
    """Local time in Berlin on `day`."""
    return datetime.combine(day, time(hour, minute), tzinfo=BERLIN)


def next_monday(engine: Engine) -> date:
    """A Monday 7-13 days ahead, so every time on it is in the future."""
    today = database_now(engine).astimezone(BERLIN).date()
    monday = today + timedelta(days=7 + (7 - today.weekday()) % 7)
    assert monday.isoweekday() == 1
    return monday


def set_hours(engine: Engine, doctor: User, *entries: tuple[int, time, time]) -> None:
    with Session(engine) as session, session.begin():
        session.add_all(
            WorkingHours(
                doctor_id=doctor.id,
                weekday=weekday,
                start_time=start,
                end_time=end,
                updated_by_id=doctor.id,
            )
            for weekday, start, end in entries
        )


def every_day(start: time, end: time) -> list[tuple[int, time, time]]:
    return [(weekday, start, end) for weekday in range(1, 8)]


def add_absence(engine: Engine, doctor: User, starts_at: datetime, ends_at: datetime) -> Absence:
    with Session(engine, expire_on_commit=False) as session, session.begin():
        absence = Absence(
            doctor_id=doctor.id, starts_at=starts_at, ends_at=ends_at, created_by_id=doctor.id
        )
        session.add(absence)
    return absence


def book(
    engine: Engine,
    doctor: User,
    patient: User,
    starts_at: datetime,
    minutes: int = 15,
    *,
    booked_by: User | None = None,
) -> Appointment:
    """A booked appointment, written without the API's checks (e.g. in the past)."""
    with Session(engine, expire_on_commit=False) as session, session.begin():
        return book_appointment(
            session,
            doctor_id=doctor.id,
            starts_at=starts_at,
            ends_at=starts_at + timedelta(minutes=minutes),
            booked_by_id=(booked_by or patient).id,
            reason=AppointmentReason.CHECKUP,
            patient_id=patient.id,
        )


def get_appointment(engine: Engine, appointment_id: object) -> Appointment:
    with Session(engine) as session:
        return session.get_one(Appointment, appointment_id)


def audit_events(engine: Engine, action: AuditAction, target: str) -> list[AuditEvent]:
    with Session(engine) as session:
        return list(
            session.scalars(
                select(AuditEvent).where(AuditEvent.action == action, AuditEvent.target == target)
            )
        )


def new_guest() -> dict[str, str]:
    """Guest contact with a phone number of its own, so the per-phone limit (BR-24) of one test
    never affects another."""
    return {"name": "Erika Mustermann", "phone": f"+49170{uuid.uuid4().int % 10**8:08d}"}
