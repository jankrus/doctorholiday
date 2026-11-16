"""Working hours (A13), absences (A14, A31), the doctor schedule (A32) and availability (A07).

Roles (x-roles in openapi.yaml): working hours, absences and schedules are for `STAFF` and
`ADMIN` (every active doctor) and `DOCTOR` (only themselves; another doctor's ID answers `404`,
like an unknown one, x-own-only); `PATIENT` gets `403`. Availability is open to every role and is
computed in `doctorholiday.scheduling`, never stored (BR-23).
"""

import logging
import uuid
from datetime import datetime, time, timedelta
from itertools import pairwise
from typing import Annotated, Self

from fastapi import APIRouter, Depends, Query, Request, Response, status
from pydantic import AwareDatetime, Field, StringConstraints, model_validator
from sqlalchemy.orm import Session

from doctorholiday import scheduling
from doctorholiday.api.common import (
    DEFAULT_LIMIT,
    NO_STORE,
    CamelRequest,
    Limit,
    Offset,
    Page,
    client_ip,
)
from doctorholiday.api.responses import Absence, AvailableTime, DoctorSchedule
from doctorholiday.auth.dependencies import ActiveUser, require_roles
from doctorholiday.db import DbSession
from doctorholiday.errors import (
    WORKING_HOURS_OVERLAP_MESSAGE,
    ApiError,
    ErrorCode,
    invalid,
    not_found,
)
from doctorholiday.models import AuditAction, AuditOutcome, Role, User
from doctorholiday.repositories import appointments, clock, practice_settings, schedule, users
from doctorholiday.repositories.audit import audit_target, record_event

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1", tags=["schedule"])

ScheduleUser = Annotated[User, Depends(require_roles(Role.STAFF, Role.DOCTOR, Role.ADMIN))]

# BR-08
MAX_ENTRIES_PER_WEEKDAY = 5
# BR-12
MAX_ABSENCE_LENGTH = timedelta(days=90)
MAX_OPEN_ABSENCES = 100
MAX_DAYS_AHEAD = scheduling.MAX_DAYS_AHEAD

# `LocalTime` of the contract: HH:MM on full 5 minutes.
LocalTime = Annotated[
    str, StringConstraints(max_length=5, pattern=r"^([01][0-9]|2[0-3]):[0-5][05]$")
]


def _parse_local_time(value: str) -> time:
    hours, minutes = value.split(":")
    return time(int(hours), int(minutes))


class WorkingHoursEntryIn(CamelRequest):
    weekday: Annotated[int, Field(ge=1, le=7)]
    start_time: LocalTime
    end_time: LocalTime

    @model_validator(mode="after")
    def _end_after_start(self) -> Self:
        if _parse_local_time(self.end_time) <= _parse_local_time(self.start_time):
            raise ValueError("endTime must be after startTime")
        return self


class WorkingHoursUpdate(CamelRequest):
    entries: Annotated[list[WorkingHoursEntryIn], Field(max_length=35)]

    @model_validator(mode="after")
    def _at_most_five_per_weekday(self) -> Self:
        for weekday in range(1, 8):
            if sum(entry.weekday == weekday for entry in self.entries) > MAX_ENTRIES_PER_WEEKDAY:
                raise ValueError("at most 5 entries per weekday")
        return self


def _on_full_minute(value: datetime) -> bool:
    return value.second == 0 and value.microsecond == 0


class AbsenceCreateRequest(CamelRequest):
    starts_at: AwareDatetime
    ends_at: AwareDatetime
    doctor_id: uuid.UUID | None = None

    @model_validator(mode="after")
    def _valid_range(self) -> Self:
        # BR-12: full minutes, endsAt after startsAt, at most 90 days. The time-relative rules
        # ("in the future", "at most 365 days ahead") need the database clock and are checked in
        # the endpoint.
        if not (_on_full_minute(self.starts_at) and _on_full_minute(self.ends_at)):
            raise ValueError("startsAt and endsAt must be on full minutes")
        if self.ends_at <= self.starts_at:
            raise ValueError("endsAt must be after startsAt")
        if self.ends_at - self.starts_at > MAX_ABSENCE_LENGTH:
            raise ValueError("an absence lasts at most 90 days")
        return self


def schedule_doctor(db: Session, user: User, doctor_id: uuid.UUID, *, lock: bool = False) -> User:
    """The doctor whose schedule `user` may manage, else `404` (BR-08, BR-12, footnote 6)."""
    # Checked against the session, never the request: a doctor gets 404 for every other ID.
    if user.role is Role.DOCTOR and doctor_id != user.id:
        raise not_found()
    doctor = users.get_active_doctor(db, doctor_id, lock=lock)
    if doctor is None:
        raise not_found()
    return doctor


def _schedule(db: Session, doctor: User) -> DoctorSchedule:
    return DoctorSchedule.of(
        doctor,
        schedule.list_working_hours(db, [doctor.id]),
        schedule.list_open_absences(db, doctor.id),
    )


@router.get(
    "/doctors/{id}/schedule",
    operation_id="getDoctorSchedule",
    response_model=DoctorSchedule,
)
def get_doctor_schedule(
    id: uuid.UUID,  # path parameter name of the contract
    user: ScheduleUser,
    response: Response,
    db: DbSession,
) -> DoctorSchedule:
    response.headers.update(NO_STORE)
    return _schedule(db, schedule_doctor(db, user, id))


@router.put(
    "/doctors/{id}/working-hours",
    operation_id="setWorkingHours",
    response_model=DoctorSchedule,
)
def set_working_hours(
    id: uuid.UUID,  # path parameter name of the contract
    body: WorkingHoursUpdate,
    user: ScheduleUser,
    request: Request,
    response: Response,
    db: DbSession,
) -> DoctorSchedule:
    entries = sorted(
        (entry.weekday, _parse_local_time(entry.start_time), _parse_local_time(entry.end_time))
        for entry in body.entries
    )
    # Sorted by weekday and start: an entry overlaps another iff it starts before the previous
    # one of the same weekday ends.
    for previous, current in pairwise(entries):
        if previous[0] == current[0] and current[1] < previous[2]:
            raise ApiError(
                status.HTTP_409_CONFLICT,
                ErrorCode.WORKING_HOURS_OVERLAP,
                WORKING_HOURS_OVERLAP_MESSAGE,
            )

    doctor = schedule_doctor(db, user, id, lock=True)
    # Booked appointments stay as they are; times outside the new hours are no longer offered.
    schedule.replace_working_hours(db, doctor_id=doctor.id, entries=entries, updated_by_id=user.id)
    record_event(
        db,
        action=AuditAction.WORKING_HOURS_CHANGED,
        outcome=AuditOutcome.SUCCESS,
        actor_id=user.id,
        target=audit_target("user", doctor.id),
        ip=client_ip(request),
        details={"entries": len(entries)},
    )
    logger.info("working hours changed", extra={"doctorId": str(doctor.id)})
    response.headers.update(NO_STORE)
    return _schedule(db, doctor)


@router.post(
    "/absences",
    operation_id="createAbsence",
    status_code=status.HTTP_201_CREATED,
    response_model=Absence,
)
def create_absence(
    body: AbsenceCreateRequest,
    user: ScheduleUser,
    request: Request,
    response: Response,
    db: DbSession,
) -> Absence:
    if body.doctor_id is None:
        # A doctor may omit their own ID; STAFF and ADMIN must name the doctor.
        if user.role is not Role.DOCTOR:
            raise invalid()
        doctor_id = user.id
    else:
        doctor_id = body.doctor_id
    # Locked first: a booking of this doctor that runs concurrently waits, and sees the absence.
    doctor = schedule_doctor(db, user, doctor_id, lock=True)

    now = clock.database_now(db)
    if body.ends_at <= now or body.starts_at > now + MAX_DAYS_AHEAD:
        raise invalid()
    if schedule.count_open_absences(db, doctor.id) >= MAX_OPEN_ABSENCES:
        raise ApiError(
            status.HTTP_409_CONFLICT,
            ErrorCode.CONFLICT,
            "This doctor already has the maximum number of absences.",
        )
    # BR-12: no patient silently loses an appointment; they are rescheduled or cancelled first.
    if appointments.has_booked_overlapping(
        db, doctor.id, starts_at=body.starts_at, ends_at=body.ends_at
    ):
        raise ApiError(
            status.HTTP_409_CONFLICT,
            ErrorCode.ABSENCE_HAS_APPOINTMENTS,
            "There are booked appointments in this time. Reschedule or cancel them first.",
        )

    absence = schedule.create_absence(
        db,
        doctor_id=doctor.id,
        starts_at=body.starts_at,
        ends_at=body.ends_at,
        created_by_id=user.id,
    )
    record_event(
        db,
        action=AuditAction.ABSENCE_CREATED,
        outcome=AuditOutcome.SUCCESS,
        actor_id=user.id,
        target=audit_target("absence", absence.id),
        ip=client_ip(request),
    )
    logger.info("absence created", extra={"absenceId": str(absence.id)})
    response.headers.update(NO_STORE)
    return Absence.of(absence, doctor)


@router.delete(
    "/absences/{id}",
    operation_id="deleteAbsence",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_absence(
    id: uuid.UUID,  # path parameter name of the contract
    user: ScheduleUser,
    request: Request,
    db: DbSession,
) -> Response:
    absence = schedule.get_absence(db, id)
    if absence is None or (user.role is Role.DOCTOR and absence.doctor_id != user.id):
        raise not_found()
    schedule.delete_absence(db, absence)
    record_event(
        db,
        action=AuditAction.ABSENCE_DELETED,
        outcome=AuditOutcome.SUCCESS,
        actor_id=user.id,
        target=audit_target("absence", id),
        ip=client_ip(request),
    )
    logger.info("absence deleted", extra={"absenceId": str(id)})
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get(
    "/availability",
    operation_id="listAvailability",
    response_model=Page[AvailableTime],
)
def list_availability(
    _user: ActiveUser,
    db: DbSession,
    from_: Annotated[AwareDatetime, Query(alias="from")],
    to: AwareDatetime,
    doctor_id: Annotated[uuid.UUID | None, Query(alias="doctorId")] = None,
    limit: Limit = DEFAULT_LIMIT,
    offset: Offset = 0,
) -> Page[AvailableTime]:
    # Bounds the work per request (BR-23): at most 31 days of steps per doctor.
    if not from_ < to <= from_ + scheduling.MAX_RANGE:
        raise invalid()

    # An unknown or inactive doctorId simply has no available times.
    doctors = users.list_active_doctors(db, doctor_id=doctor_id)
    minutes = practice_settings.get_practice_settings(db).appointment_minutes
    now = clock.database_now(db)
    ids = [doctor.id for doctor in doctors]
    # Everything that can overlap an appointment starting in [from, to).
    window = {"starts_before": to + timedelta(minutes=minutes), "ends_after": from_}
    hours: dict[uuid.UUID, list[scheduling.WorkingHoursEntry]] = {}
    for row in schedule.list_working_hours(db, ids):
        hours.setdefault(row.doctor_id, []).append((row.weekday, row.start_time, row.end_time))
    blocked: dict[uuid.UUID, list[scheduling.Interval]] = {}
    for row in [
        *schedule.list_absences_overlapping(db, ids, **window),
        *appointments.list_booked_overlapping(db, ids, **window),
    ]:
        blocked.setdefault(row.doctor_id, []).append(
            scheduling.Interval(row.starts_at, row.ends_at)
        )

    found = [
        (starts_at, doctor)
        for doctor in doctors
        for starts_at in scheduling.available_times(
            hours.get(doctor.id, []),
            scheduling.Blocked(blocked.get(doctor.id, [])),
            starts_from=from_,
            starts_before=to,
            minutes=minutes,
            now=now,
        )
    ]
    # Ascending by start, then by doctor (BR-20); `doctors` is sorted by name, sort() is stable.
    found.sort(key=lambda item: item[0])
    return Page(
        limit=limit,
        offset=offset,
        total=len(found),
        items=[
            AvailableTime.of(doctor, starts_at, minutes)
            for starts_at, doctor in found[offset : offset + limit]
        ],
    )
