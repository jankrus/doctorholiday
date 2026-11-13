"""Working hours and absences of doctors (BR-08, BR-12). Availability is computed from them."""

import uuid
from collections.abc import Iterable, Sequence
from datetime import datetime, time

from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from doctorholiday.db import violated_constraint
from doctorholiday.models import Absence, WorkingHours
from doctorholiday.repositories.errors import WorkingHoursOverlapError

# (weekday, start, end), local time in Europe/Berlin
WorkingHoursEntry = tuple[int, time, time]


def list_working_hours(session: Session, doctor_ids: Iterable[uuid.UUID]) -> Sequence[WorkingHours]:
    """Entries of these doctors, sorted by doctor, weekday and start."""
    return session.scalars(
        select(WorkingHours)
        .where(WorkingHours.doctor_id.in_(set(doctor_ids)))
        .order_by(WorkingHours.doctor_id, WorkingHours.weekday, WorkingHours.start_time)
    ).all()


def replace_working_hours(
    session: Session,
    *,
    doctor_id: uuid.UUID,
    entries: Iterable[WorkingHoursEntry],
    updated_by_id: uuid.UUID,
) -> None:
    """Replace the doctor's whole weekly schedule (BR-08), in the caller's transaction.

    The caller holds the doctor's row lock (users.get_active_doctor(lock=True)), so two
    replacements never interleave. The exclusion constraint stays the final guard against
    overlapping entries and raises WorkingHoursOverlapError.
    """
    try:
        with session.begin_nested():
            session.execute(delete(WorkingHours).where(WorkingHours.doctor_id == doctor_id))
            session.add_all(
                WorkingHours(
                    doctor_id=doctor_id,
                    weekday=weekday,
                    start_time=start,
                    end_time=end,
                    updated_by_id=updated_by_id,
                )
                for weekday, start, end in entries
            )
            session.flush()
    except IntegrityError as exc:
        if violated_constraint(exc) == "working_hours_no_overlap":
            raise WorkingHoursOverlapError from None
        raise


def create_absence(
    session: Session,
    *,
    doctor_id: uuid.UUID,
    starts_at: datetime,
    ends_at: datetime,
    created_by_id: uuid.UUID,
) -> Absence:
    absence = Absence(
        doctor_id=doctor_id, starts_at=starts_at, ends_at=ends_at, created_by_id=created_by_id
    )
    session.add(absence)
    session.flush()
    return absence


def get_absence(session: Session, absence_id: uuid.UUID) -> Absence | None:
    return session.get(Absence, absence_id)


def delete_absence(session: Session, absence: Absence) -> None:
    session.delete(absence)
    session.flush()


def count_open_absences(session: Session, doctor_id: uuid.UUID) -> int:
    """Absences of the doctor that have not ended (BR-12: at most 100)."""
    return (
        session.scalar(
            select(func.count())
            .select_from(Absence)
            .where(Absence.doctor_id == doctor_id, Absence.ends_at > func.now())
        )
        or 0
    )


def list_open_absences(session: Session, doctor_id: uuid.UUID) -> Sequence[Absence]:
    """Absences of the doctor that have not ended, sorted by start (A32)."""
    return session.scalars(
        select(Absence)
        .where(Absence.doctor_id == doctor_id, Absence.ends_at > func.now())
        .order_by(Absence.starts_at, Absence.id)
    ).all()


def list_absences_overlapping(
    session: Session,
    doctor_ids: Iterable[uuid.UUID],
    *,
    starts_before: datetime,
    ends_after: datetime,
) -> Sequence[Absence]:
    """Absences of these doctors that overlap [ends_after, starts_before)."""
    return session.scalars(
        select(Absence).where(
            Absence.doctor_id.in_(set(doctor_ids)),
            Absence.starts_at < starts_before,
            Absence.ends_at > ends_after,
        )
    ).all()
