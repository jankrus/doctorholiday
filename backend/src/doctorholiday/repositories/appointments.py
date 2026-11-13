"""Appointments. Overlaps are prevented by the database, not by a prior check (BR-09)."""

import uuid
from collections.abc import Iterable, Sequence
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from doctorholiday.db import violated_constraint
from doctorholiday.models import Appointment, AppointmentReason, AppointmentStatus, User
from doctorholiday.repositories.errors import TimeAlreadyBookedError


def book_appointment(
    session: Session,
    *,
    doctor_id: uuid.UUID,
    starts_at: datetime,
    ends_at: datetime,
    booked_by_id: uuid.UUID,
    reason: AppointmentReason,
    patient_id: uuid.UUID | None = None,
    guest_name: str | None = None,
    guest_phone: str | None = None,
) -> Appointment:
    """Book for a patient or a guest (exactly one; the database checks the shape).

    Two concurrent bookings of overlapping times for the same doctor cannot both succeed: the
    exclusion constraint rejects the second once the first commits. Availability checks before
    the insert are for user feedback only.

    Bookings of one doctor are serialised by a lock on the doctor's row, held until the
    transaction ends. Without it, concurrent inserts that conflict on the exclusion constraint
    each wait for the other's uncommitted row, and PostgreSQL aborts one of them with a deadlock
    error instead of the constraint violation (a 500 instead of a 409). `FOR NO KEY UPDATE` does
    not block the `FOR KEY SHARE` locks that foreign key checks take on the same row.
    """
    session.execute(select(User.id).where(User.id == doctor_id).with_for_update(key_share=True))
    appointment = Appointment(
        doctor_id=doctor_id,
        starts_at=starts_at,
        ends_at=ends_at,
        patient_id=patient_id,
        guest_name=guest_name,
        guest_phone=guest_phone,
        booked_by_id=booked_by_id,
        reason=reason,
    )
    try:
        with session.begin_nested():
            session.add(appointment)
            session.flush()
    except IntegrityError as exc:
        if violated_constraint(exc) == "appointments_no_overlap":
            raise TimeAlreadyBookedError from None
        raise
    return appointment


def get_appointment(session: Session, appointment_id: uuid.UUID) -> Appointment | None:
    return session.get(Appointment, appointment_id)


def list_booked_for_doctor(
    session: Session, doctor_id: uuid.UUID, *, starts_before: datetime, ends_after: datetime
) -> Sequence[Appointment]:
    """Booked appointments of one doctor that overlap [ends_after, starts_before)."""
    return session.scalars(
        select(Appointment)
        .where(
            Appointment.doctor_id == doctor_id,
            Appointment.status == AppointmentStatus.BOOKED,
            Appointment.starts_at < starts_before,
            Appointment.ends_at > ends_after,
        )
        .order_by(Appointment.starts_at)
    ).all()


def cancel_appointment(
    session: Session, appointment: Appointment, *, cancelled_by_id: uuid.UUID
) -> None:
    """Mark as cancelled; the time is bookable again. Who and when is up to the caller."""
    appointment.status = AppointmentStatus.CANCELLED
    appointment.cancelled_at = func.now()
    appointment.cancelled_by_id = cancelled_by_id
    session.flush()


def has_booked_overlapping(
    session: Session, doctor_id: uuid.UUID, *, starts_at: datetime, ends_at: datetime
) -> bool:
    """Whether a booked appointment of the doctor overlaps [starts_at, ends_at) (BR-12)."""
    return (
        session.scalar(
            select(Appointment.id)
            .where(
                Appointment.doctor_id == doctor_id,
                Appointment.status == AppointmentStatus.BOOKED,
                Appointment.starts_at < ends_at,
                Appointment.ends_at > starts_at,
            )
            .limit(1)
        )
        is not None
    )


def list_booked_overlapping(
    session: Session,
    doctor_ids: Iterable[uuid.UUID],
    *,
    starts_before: datetime,
    ends_after: datetime,
) -> Sequence[Appointment]:
    """Booked appointments of these doctors that overlap [ends_after, starts_before)."""
    return session.scalars(
        select(Appointment).where(
            Appointment.doctor_id.in_(set(doctor_ids)),
            Appointment.status == AppointmentStatus.BOOKED,
            Appointment.starts_at < starts_before,
            Appointment.ends_at > ends_after,
        )
    ).all()


def count_open_for_patient(session: Session, patient_id: uuid.UUID) -> int:
    """Booked appointments of the patient that have not started (BR-09: at most 5), whoever
    booked them."""
    return (
        session.scalar(
            select(func.count())
            .select_from(Appointment)
            .where(
                Appointment.patient_id == patient_id,
                Appointment.status == AppointmentStatus.BOOKED,
                Appointment.starts_at > func.now(),
            )
        )
        or 0
    )


def count_open_for_guest_phone(session: Session, phone: str) -> int:
    """Booked guest appointments with this phone number that have not started (BR-24: at most 5)."""
    return (
        session.scalar(
            select(func.count())
            .select_from(Appointment)
            .where(
                Appointment.guest_phone == phone,
                Appointment.status == AppointmentStatus.BOOKED,
                Appointment.starts_at > func.now(),
            )
        )
        or 0
    )


def lock_guest_phone(session: Session, phone: str) -> None:
    """Serialise bookings for one guest phone number until the transaction ends, so concurrent
    bookings cannot both pass the open-appointment limit (BR-24). A guest has no row to lock, so
    this takes a transaction-level advisory lock on a hash of the number."""
    session.execute(select(func.pg_advisory_xact_lock(func.hashtextextended(phone, 0))))
