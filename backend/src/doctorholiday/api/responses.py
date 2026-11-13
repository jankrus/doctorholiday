"""Response bodies shared by several routers, named as the schemas in openapi.yaml."""

import enum
import uuid
from collections.abc import Iterable, Mapping
from datetime import datetime, time, timedelta

from doctorholiday.api.common import ResponseModel, UtcDatetime
from doctorholiday.models import Absence as AbsenceRow
from doctorholiday.models import Appointment as AppointmentRow
from doctorholiday.models import AppointmentReason, AppointmentStatus, User, WorkingHours
from doctorholiday.models import PracticeSettings as PracticeSettingsRow

# Shown if a doctor has no display name; accounts from invitations always have one (BR-14).
_UNNAMED_DOCTOR = "Doctor"


class DoctorRef(ResponseModel):
    id: uuid.UUID
    display_name: str

    @classmethod
    def of(cls, doctor: User) -> "DoctorRef":
        # ID and display name only, never the e-mail (A27).
        return cls(id=doctor.id, display_name=doctor.display_name or _UNNAMED_DOCTOR)


class PracticeSettings(ResponseModel):
    practice_name: str
    cancellation_deadline_hours: int
    appointment_minutes: int
    updated_at: UtcDatetime

    @classmethod
    def of(cls, row: PracticeSettingsRow) -> "PracticeSettings":
        return cls(
            practice_name=row.practice_name,
            cancellation_deadline_hours=row.cancellation_deadline_hours,
            appointment_minutes=row.appointment_minutes,
            updated_at=row.updated_at,
        )


def local_time(value: time) -> str:
    """`LocalTime` of the contract: `HH:MM`."""
    return value.strftime("%H:%M")


class WorkingHoursEntry(ResponseModel):
    weekday: int
    start_time: str
    end_time: str

    @classmethod
    def of(cls, row: WorkingHours) -> "WorkingHoursEntry":
        return cls(
            weekday=row.weekday,
            start_time=local_time(row.start_time),
            end_time=local_time(row.end_time),
        )


class Absence(ResponseModel):
    id: uuid.UUID
    doctor: DoctorRef
    starts_at: UtcDatetime
    ends_at: UtcDatetime

    @classmethod
    def of(cls, row: AbsenceRow, doctor: User) -> "Absence":
        return cls(
            id=row.id, doctor=DoctorRef.of(doctor), starts_at=row.starts_at, ends_at=row.ends_at
        )


class DoctorSchedule(ResponseModel):
    doctor: DoctorRef
    working_hours: list[WorkingHoursEntry]
    absences: list[Absence]

    @classmethod
    def of(
        cls, doctor: User, working_hours: Iterable[WorkingHours], absences: Iterable[AbsenceRow]
    ) -> "DoctorSchedule":
        return cls(
            doctor=DoctorRef.of(doctor),
            working_hours=[WorkingHoursEntry.of(row) for row in working_hours],
            absences=[Absence.of(row, doctor) for row in absences],
        )


class AvailableTime(ResponseModel):
    doctor: DoctorRef
    starts_at: UtcDatetime
    ends_at: UtcDatetime

    @classmethod
    def of(cls, doctor: User, starts_at: datetime, minutes: int) -> "AvailableTime":
        return cls(
            doctor=DoctorRef.of(doctor),
            starts_at=starts_at,
            ends_at=starts_at + timedelta(minutes=minutes),
        )


class BookingParty(enum.StrEnum):
    PATIENT = "PATIENT"
    PRACTICE = "PRACTICE"


class PatientRef(ResponseModel):
    id: uuid.UUID
    deleted: bool
    # Absent after the patient deleted their account (BR-13).
    email: str | None = None
    display_name: str | None = None

    @classmethod
    def of(cls, patient: User) -> "PatientRef":
        if patient.deleted_at is not None:
            return cls(id=patient.id, deleted=True)
        return cls(
            id=patient.id, deleted=False, email=patient.email, display_name=patient.display_name
        )


class GuestContact(ResponseModel):
    name: str
    phone: str


class Appointment(ResponseModel):
    """`patient` and `guest` are only in the practice's view (STAFF, DOCTOR, ADMIN); a patient
    sees their own appointments without either (A11). Absent fields are left out of the JSON
    (`response_model_exclude_none=True` on the routes)."""

    id: uuid.UUID
    status: AppointmentStatus
    reason: AppointmentReason
    doctor: DoctorRef
    starts_at: UtcDatetime
    ends_at: UtcDatetime
    patient: PatientRef | None = None
    guest: GuestContact | None = None
    booked_by: BookingParty
    created_at: UtcDatetime
    cancelled_at: UtcDatetime | None = None
    cancelled_by: BookingParty | None = None

    @classmethod
    def of(
        cls, row: AppointmentRow, users: Mapping[uuid.UUID, User], *, practice_view: bool
    ) -> "Appointment":
        """`users` holds at least the appointment's doctor and, for the practice view, its
        patient (repositories.users.get_users)."""
        patient = users[row.patient_id] if practice_view and row.patient_id else None
        guest = (
            GuestContact(name=row.guest_name, phone=row.guest_phone)
            if practice_view and row.guest_name is not None and row.guest_phone is not None
            else None
        )
        return cls(
            id=row.id,
            status=row.status,
            reason=row.reason,
            doctor=DoctorRef.of(users[row.doctor_id]),
            starts_at=row.starts_at,
            ends_at=row.ends_at,
            patient=PatientRef.of(patient) if patient else None,
            guest=guest,
            booked_by=_party(row.booked_by_id, row),
            created_at=row.created_at,
            cancelled_at=row.cancelled_at,
            cancelled_by=_party(row.cancelled_by_id, row) if row.cancelled_by_id else None,
        )


def _party(actor_id: uuid.UUID | None, row: AppointmentRow) -> BookingParty:
    # Only the patient themselves acts as PATIENT; everyone else (staff, doctor, admin) is the
    # practice. Guests have no login, so their appointments are always the practice's doing.
    if row.patient_id is not None and actor_id == row.patient_id:
        return BookingParty.PATIENT
    return BookingParty.PRACTICE
