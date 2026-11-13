"""Response bodies shared by several routers, named as the schemas in openapi.yaml."""

import uuid

from doctorholiday.api.common import ResponseModel, UtcDatetime
from doctorholiday.models import PracticeSettings as PracticeSettingsRow
from doctorholiday.models import User

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
