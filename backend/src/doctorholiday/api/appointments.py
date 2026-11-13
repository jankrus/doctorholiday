"""Appointments (#17): book (A08), cancel (A09, A10), reschedule (A30) and the lists (A11, A12).

Authorisation (x-roles, x-own-only, x-tbac in openapi.yaml):
- Roles are checked per route with `require_roles`; the role comes from the session's user row.
- Ownership: a `PATIENT` acts only on appointments whose `patient_id` is their own ID; any other
  appointment answers `404`, exactly like an unknown ID, so IDs cannot be probed.
- A `PATIENT` never sees `patient` or `guest` in a response (closed response schemas in the
  contract tests check this).
- `ADMIN` reaches appointment data (A10, A12) only with an active time-limited grant (BR-17,
  `403 ACCESS_GRANT_REQUIRED` otherwise); every access under a grant is audited.

Concurrency: every write locks the rows it depends on in a fixed order (patient or guest phone,
then the appointment, then the doctor), so concurrent requests run one after the other where
they conflict and never deadlock. The exclusion constraint `appointments_no_overlap` stays the
final guard: an overlap with another booked appointment is `409 TIME_ALREADY_BOOKED`.
"""

import logging
import uuid
from datetime import datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response, status
from pydantic import AwareDatetime, StringConstraints
from sqlalchemy.orm import Session

from doctorholiday import scheduling
from doctorholiday.api.common import NO_STORE, CamelRequest, client_ip
from doctorholiday.api.responses import Appointment
from doctorholiday.auth.dependencies import require_roles
from doctorholiday.db import DbSession
from doctorholiday.errors import VALIDATION_MESSAGE, ApiError, ErrorCode, not_found
from doctorholiday.models import Appointment as AppointmentRow
from doctorholiday.models import AppointmentReason, AuditAction, AuditOutcome, Role, User
from doctorholiday.repositories import appointments, clock, practice_settings, schedule, users
from doctorholiday.repositories.audit import audit_target, record_event
from doctorholiday.validation import DisplayName, Email

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/appointments", tags=["appointments"])

# BR-09, BR-24
MAX_OPEN_APPOINTMENTS = 5

BookingUser = Annotated[User, Depends(require_roles(Role.PATIENT, Role.STAFF))]

# E.164 as in the contract's GuestContact.phone.
Phone = Annotated[str, StringConstraints(max_length=16, pattern=r"^\+[1-9][0-9]{6,14}$")]


class GuestContactIn(CamelRequest):
    name: DisplayName
    phone: Phone


class AppointmentCreateRequest(CamelRequest):
    doctor_id: uuid.UUID
    starts_at: AwareDatetime
    # An enum, no free text: no diagnoses or symptoms are stored (BR-10).
    reason: AppointmentReason
    # Who the appointment is for depends on the caller's role, so it is checked in the endpoint
    # (`_booking_party`), not here.
    patient_email: Email | None = None
    guest: GuestContactIn | None = None


def _invalid() -> ApiError:
    return ApiError(
        status.HTTP_422_UNPROCESSABLE_CONTENT, ErrorCode.VALIDATION_ERROR, VALIDATION_MESSAGE
    )


def _forbidden() -> ApiError:
    return ApiError(
        status.HTTP_403_FORBIDDEN, ErrorCode.FORBIDDEN, "You are not allowed to do this."
    )


def ensure_offered(
    db: Session, doctor: User, starts_at: datetime, *, minutes: int, now: datetime
) -> None:
    """`409 TIME_NOT_AVAILABLE` unless `starts_at` is a start time the doctor offers (BR-23).

    Booked appointments are not checked here: the exclusion constraint answers an overlap with
    `409 TIME_ALREADY_BOOKED`, for concurrent requests too. Call it with the doctor's row locked,
    so an absence created at the same time is either seen here or waits for this booking.
    """
    hours = [
        (row.weekday, row.start_time, row.end_time)
        for row in schedule.list_working_hours(db, [doctor.id])
    ]
    absences = [
        scheduling.Interval(row.starts_at, row.ends_at)
        for row in schedule.list_absences_overlapping(
            db,
            [doctor.id],
            starts_before=starts_at + timedelta(minutes=minutes),
            ends_after=starts_at,
        )
    ]
    if not scheduling.is_offered(hours, absences, starts_at=starts_at, minutes=minutes, now=now):
        raise ApiError(
            status.HTTP_409_CONFLICT,
            ErrorCode.TIME_NOT_AVAILABLE,
            "This time is not available. Please choose another one.",
        )


def _limit_reached() -> ApiError:
    return ApiError(
        status.HTTP_409_CONFLICT,
        ErrorCode.APPOINTMENT_LIMIT_REACHED,
        "The maximum number of open appointments is reached.",
    )


def _booking_party(
    db: Session, user: User, body: AppointmentCreateRequest
) -> tuple[User | None, GuestContactIn | None]:
    """Exactly one of (patient, None) and (None, guest) (BR-09, BR-24)."""
    if user.role is Role.PATIENT:
        # Always for themselves: naming anyone is not allowed, not just ignored.
        if body.patient_email is not None or body.guest is not None:
            raise _forbidden()
        return user, None
    # STAFF: exactly one of patientEmail and guest.
    if (body.patient_email is None) == (body.guest is None):
        raise _invalid()
    if body.guest is not None:
        return None, body.guest
    patient = users.get_active_patient_by_email(db, body.patient_email)
    if patient is None:
        raise not_found()
    return patient, None


def appointment_view(db: Session, row: AppointmentRow, user: User) -> Appointment:
    ids = [row.doctor_id] + ([row.patient_id] if row.patient_id else [])
    return Appointment.of(
        row, users.get_users(db, ids), practice_view=user.role is not Role.PATIENT
    )


@router.post(
    "",
    operation_id="bookAppointment",
    status_code=status.HTTP_201_CREATED,
    response_model=Appointment,
    response_model_exclude_none=True,
)
def book_appointment(
    body: AppointmentCreateRequest,
    user: BookingUser,
    request: Request,
    response: Response,
    db: DbSession,
) -> Appointment:
    patient, guest = _booking_party(db, user, body)

    # Lock order: the party first, then the doctor (module docstring).
    if patient is not None:
        users.lock_user(db, patient.id)
    if guest is not None:
        appointments.lock_guest_phone(db, guest.phone)
    doctor = users.get_active_doctor(db, body.doctor_id, lock=True)
    if doctor is None:
        raise not_found()

    minutes = practice_settings.get_practice_settings(db).appointment_minutes
    ensure_offered(db, doctor, body.starts_at, minutes=minutes, now=clock.database_now(db))
    open_count = (
        appointments.count_open_for_patient(db, patient.id)
        if patient is not None
        else appointments.count_open_for_guest_phone(db, guest.phone if guest else "")
    )
    if open_count >= MAX_OPEN_APPOINTMENTS:
        raise _limit_reached()

    # TimeAlreadyBookedError (overlap with a booked appointment) becomes 409 TIME_ALREADY_BOOKED.
    row = appointments.book_appointment(
        db,
        doctor_id=doctor.id,
        starts_at=body.starts_at,
        ends_at=body.starts_at + timedelta(minutes=minutes),
        booked_by_id=user.id,
        reason=body.reason,
        patient_id=patient.id if patient else None,
        guest_name=guest.name if guest else None,
        guest_phone=guest.phone if guest else None,
    )
    # The appointment ID only; never patient or guest data (BR-19, BR-24).
    record_event(
        db,
        action=AuditAction.APPOINTMENT_BOOKED,
        outcome=AuditOutcome.SUCCESS,
        actor_id=user.id,
        target=audit_target("appointment", row.id),
        ip=client_ip(request),
    )
    logger.info("appointment booked", extra={"appointmentId": str(row.id)})
    response.headers.update(NO_STORE)
    return appointment_view(db, row, user)
