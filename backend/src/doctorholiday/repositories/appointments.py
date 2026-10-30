"""Appointments. Overlaps are prevented by the database, not by a prior check (BR-09)."""

import uuid
from collections.abc import Sequence
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from doctorholiday.db import violated_constraint
from doctorholiday.models import Appointment, AppointmentReason, AppointmentStatus
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
    exclusion constraint makes the second insert wait for the first transaction and fail once it
    commits. Availability checks before the insert are for user feedback only.
    """
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
