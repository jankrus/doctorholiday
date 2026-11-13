"""Response bodies shared by several routers, named as the schemas in openapi.yaml."""

import uuid
from collections.abc import Iterable
from datetime import time

from doctorholiday.api.common import ResponseModel, UtcDatetime
from doctorholiday.models import Absence as AbsenceRow
from doctorholiday.models import PracticeSettings as PracticeSettingsRow
from doctorholiday.models import User, WorkingHours

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
