"""Working hours (A13), absences (A14, A31) and the doctor schedule (A32), #17."""

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from sqlalchemy import Engine, func, select
from sqlalchemy.orm import Session

from doctorholiday.models import (
    Absence,
    Appointment,
    AppointmentReason,
    AuditAction,
    AuditEvent,
    AuditOutcome,
    Role,
    User,
    WorkingHours,
)
from doctorholiday.repositories.appointments import book_appointment, cancel_appointment
from tests.db.conftest import ClientFactory, UserFactory, database_now

WEEK = [
    {"weekday": 1, "startTime": "08:00", "endTime": "12:00"},
    {"weekday": 1, "startTime": "14:00", "endTime": "18:00"},
    {"weekday": 3, "startTime": "09:30", "endTime": "13:45"},
]


def put_hours(client: Any, doctor: User | uuid.UUID, entries: list[dict[str, Any]]) -> Any:
    doctor_id = doctor if isinstance(doctor, uuid.UUID) else doctor.id
    return client.put(f"/api/v1/doctors/{doctor_id}/working-hours", json={"entries": entries})


def audit_events(engine: Engine, action: AuditAction, target: str) -> list[AuditEvent]:
    with Session(engine) as session:
        return list(
            session.scalars(
                select(AuditEvent).where(AuditEvent.action == action, AuditEvent.target == target)
            )
        )


def book(engine: Engine, doctor: User, patient: User, starts_at: datetime) -> Appointment:
    with Session(engine, expire_on_commit=False) as session, session.begin():
        return book_appointment(
            session,
            doctor_id=doctor.id,
            starts_at=starts_at,
            ends_at=starts_at + timedelta(minutes=15),
            booked_by_id=patient.id,
            reason=AppointmentReason.CHECKUP,
            patient_id=patient.id,
        )


def iso(value: datetime) -> str:
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def future_minute(engine: Engine, delta: timedelta) -> datetime:
    """now + delta, rounded down to the full minute (BR-12)."""
    return (database_now(engine) + delta).replace(second=0, microsecond=0)


@pytest.fixture
def doctor(make_committed_user: UserFactory) -> User:
    return make_committed_user(Role.DOCTOR)


@pytest.fixture
def staff(make_committed_user: UserFactory) -> User:
    return make_committed_user(Role.STAFF)


# ---------- Working hours ----------


@pytest.mark.parametrize("role", [Role.STAFF, Role.ADMIN])
def test_staff_and_admin_replace_the_working_hours_of_any_doctor(
    client_as: ClientFactory,
    make_committed_user: UserFactory,
    doctor: User,
    db_engine: Engine,
    role: Role,
) -> None:
    actor = make_committed_user(role)
    client = client_as(actor)

    response = put_hours(client, doctor, list(reversed(WEEK)))

    assert response.status_code == 200
    body = response.json()
    assert body["doctor"] == {"id": str(doctor.id), "displayName": doctor.display_name}
    assert body["workingHours"] == WEEK  # sorted by weekday and start
    assert body["absences"] == []
    [event] = audit_events(db_engine, AuditAction.WORKING_HOURS_CHANGED, f"user:{doctor.id}")
    assert event.actor_id == actor.id
    assert event.outcome is AuditOutcome.SUCCESS
    assert event.details == {"entries": 3}


def test_a_doctor_sets_their_own_hours_only(
    client_as: ClientFactory, make_committed_user: UserFactory, doctor: User
) -> None:
    other = make_committed_user(Role.DOCTOR)
    client = client_as(doctor)

    assert put_hours(client, doctor, WEEK).status_code == 200
    response = put_hours(client, other, WEEK)
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "NOT_FOUND"


def test_a_put_replaces_the_whole_schedule(
    client_as: ClientFactory, staff: User, doctor: User, db_engine: Engine
) -> None:
    client = client_as(staff)
    put_hours(client, doctor, WEEK)

    assert put_hours(client, doctor, WEEK[2:]).json()["workingHours"] == WEEK[2:]
    assert put_hours(client, doctor, []).json()["workingHours"] == []
    with Session(db_engine) as session:
        assert not session.scalars(
            select(WorkingHours).where(WorkingHours.doctor_id == doctor.id)
        ).all()


def test_changing_hours_keeps_booked_appointments(
    client_as: ClientFactory,
    staff: User,
    doctor: User,
    make_committed_user: UserFactory,
    db_engine: Engine,
) -> None:
    appointment = book(
        db_engine, doctor, make_committed_user(), future_minute(db_engine, timedelta(days=3))
    )

    assert put_hours(client_as(staff), doctor, []).status_code == 200
    with Session(db_engine) as session:
        assert session.get_one(Appointment, appointment.id).status == "BOOKED"


@pytest.mark.parametrize(
    "entries",
    [
        [
            {"weekday": 1, "startTime": "08:00", "endTime": "12:00"},
            {"weekday": 1, "startTime": "11:55", "endTime": "13:00"},
        ],
        [
            {"weekday": 2, "startTime": "08:00", "endTime": "18:00"},
            {"weekday": 2, "startTime": "09:00", "endTime": "10:00"},
        ],
        [
            {"weekday": 5, "startTime": "10:00", "endTime": "11:00"},
            {"weekday": 5, "startTime": "10:00", "endTime": "11:00"},
        ],
    ],
)
def test_overlapping_entries_of_a_weekday_are_a_conflict(
    client_as: ClientFactory, staff: User, doctor: User, entries: list[dict[str, Any]]
) -> None:
    client = client_as(staff)
    put_hours(client, doctor, WEEK)

    response = put_hours(client, doctor, entries)

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "WORKING_HOURS_OVERLAP"
    # Nothing changed.
    assert client.get(f"/api/v1/doctors/{doctor.id}/schedule").json()["workingHours"] == WEEK


def test_adjacent_entries_and_the_same_hours_on_other_days_are_fine(
    client_as: ClientFactory, staff: User, doctor: User
) -> None:
    entries = [
        {"weekday": 1, "startTime": "08:00", "endTime": "12:00"},
        {"weekday": 1, "startTime": "12:00", "endTime": "13:00"},
        {"weekday": 2, "startTime": "08:00", "endTime": "12:00"},
    ]

    assert put_hours(client_as(staff), doctor, entries).status_code == 200


def test_five_entries_per_weekday_are_allowed_six_are_not(
    client_as: ClientFactory, staff: User, doctor: User
) -> None:
    def day(count: int) -> list[dict[str, Any]]:
        return [
            {"weekday": 4, "startTime": f"{8 + i:02d}:00", "endTime": f"{8 + i:02d}:30"}
            for i in range(count)
        ]

    client = client_as(staff)
    assert put_hours(client, doctor, day(5)).status_code == 200
    response = put_hours(client, doctor, day(6))
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


@pytest.mark.parametrize(
    "entry",
    [
        {"weekday": 1, "startTime": "12:00", "endTime": "08:00"},
        {"weekday": 1, "startTime": "08:00", "endTime": "08:00"},
        {"weekday": 1, "startTime": "08:03", "endTime": "12:00"},
        {"weekday": 1, "startTime": "8:00", "endTime": "12:00"},
        {"weekday": 1, "startTime": "08:00", "endTime": "24:00"},
        {"weekday": 0, "startTime": "08:00", "endTime": "12:00"},
        {"weekday": 8, "startTime": "08:00", "endTime": "12:00"},
        {"weekday": 1, "startTime": "08:00"},
        {"weekday": 1, "startTime": "08:00", "endTime": "12:00", "note": "x"},
    ],
)
def test_invalid_entries_are_rejected(
    client_as: ClientFactory, staff: User, doctor: User, entry: dict[str, Any]
) -> None:
    response = put_hours(client_as(staff), doctor, [entry])

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


def test_more_than_35_entries_are_rejected(
    client_as: ClientFactory, staff: User, doctor: User
) -> None:
    entries = [{"weekday": 1, "startTime": "08:00", "endTime": "08:05"}] * 36

    assert put_hours(client_as(staff), doctor, entries).status_code == 422


def test_only_active_doctors_have_working_hours(
    client_as: ClientFactory, staff: User, make_committed_user: UserFactory
) -> None:
    client = client_as(staff)

    for target in (uuid.uuid4(), make_committed_user(Role.STAFF).id, make_committed_user().id):
        response = put_hours(client, target, WEEK)
        assert response.status_code == 404


def test_patients_and_anonymous_callers_cannot_set_working_hours(
    client_as: ClientFactory, make_committed_user: UserFactory, doctor: User
) -> None:
    response = put_hours(client_as(make_committed_user()), doctor, WEEK)
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "FORBIDDEN"
    assert put_hours(client_as(None), doctor, WEEK).status_code == 401


# ---------- Absences ----------


def absence_body(
    engine: Engine, start: timedelta, length: timedelta, **extra: Any
) -> dict[str, Any]:
    starts_at = future_minute(engine, start)
    return {"startsAt": iso(starts_at), "endsAt": iso(starts_at + length), **extra}


def test_a_doctor_blocks_their_own_time_without_naming_themselves(
    client_as: ClientFactory, doctor: User, db_engine: Engine
) -> None:
    body = absence_body(db_engine, timedelta(days=2), timedelta(days=1))

    response = client_as(doctor).post("/api/v1/absences", json=body)

    assert response.status_code == 201
    absence = response.json()
    assert absence["doctor"]["id"] == str(doctor.id)
    assert absence["startsAt"] == body["startsAt"]
    assert absence["endsAt"] == body["endsAt"]
    [event] = audit_events(db_engine, AuditAction.ABSENCE_CREATED, f"absence:{absence['id']}")
    assert event.actor_id == doctor.id


def test_a_doctor_may_name_themselves_but_nobody_else(
    client_as: ClientFactory, doctor: User, make_committed_user: UserFactory, db_engine: Engine
) -> None:
    client = client_as(doctor)
    other = make_committed_user(Role.DOCTOR)

    own = absence_body(db_engine, timedelta(days=2), timedelta(hours=2), doctorId=str(doctor.id))
    assert client.post("/api/v1/absences", json=own).status_code == 201
    foreign = absence_body(db_engine, timedelta(days=2), timedelta(hours=2), doctorId=str(other.id))
    assert client.post("/api/v1/absences", json=foreign).status_code == 404


@pytest.mark.parametrize("role", [Role.STAFF, Role.ADMIN])
def test_staff_and_admin_must_name_an_active_doctor(
    client_as: ClientFactory,
    make_committed_user: UserFactory,
    doctor: User,
    db_engine: Engine,
    role: Role,
) -> None:
    client = client_as(make_committed_user(role))
    body = absence_body(db_engine, timedelta(days=2), timedelta(hours=2))

    assert client.post("/api/v1/absences", json=body).status_code == 422
    unknown = {**body, "doctorId": str(uuid.uuid4())}
    assert client.post("/api/v1/absences", json=unknown).status_code == 404
    not_a_doctor = {**body, "doctorId": str(make_committed_user(Role.STAFF).id)}
    assert client.post("/api/v1/absences", json=not_a_doctor).status_code == 404
    response = client.post("/api/v1/absences", json={**body, "doctorId": str(doctor.id)})
    assert response.status_code == 201


def test_patients_cannot_block_time(
    client_as: ClientFactory, make_committed_user: UserFactory, doctor: User, db_engine: Engine
) -> None:
    body = absence_body(db_engine, timedelta(days=2), timedelta(hours=2), doctorId=str(doctor.id))

    assert client_as(make_committed_user()).post("/api/v1/absences", json=body).status_code == 403
    assert client_as(None).post("/api/v1/absences", json=body).status_code == 401


@pytest.mark.parametrize(
    ("start", "length"),
    [
        (timedelta(days=-2), timedelta(days=1)),  # ended already
        (timedelta(days=366), timedelta(days=1)),  # starts more than 365 days ahead
        (timedelta(days=2), timedelta(days=90, minutes=1)),  # longer than 90 days
        (timedelta(days=2), timedelta(0)),  # empty
        (timedelta(days=2), timedelta(hours=-1)),  # ends before it starts
    ],
)
def test_invalid_ranges_are_rejected(
    client_as: ClientFactory, doctor: User, db_engine: Engine, start: timedelta, length: timedelta
) -> None:
    body = absence_body(db_engine, start, length)

    response = client_as(doctor).post("/api/v1/absences", json=body)

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


def test_a_running_absence_and_exactly_90_days_are_allowed(
    client_as: ClientFactory, doctor: User, db_engine: Engine
) -> None:
    client = client_as(doctor)

    running = absence_body(db_engine, timedelta(days=-1), timedelta(days=2))
    assert client.post("/api/v1/absences", json=running).status_code == 201
    longest = absence_body(db_engine, timedelta(days=200), timedelta(days=90))
    assert client.post("/api/v1/absences", json=longest).status_code == 201


@pytest.mark.parametrize(
    ("starts_at", "ends_at"),
    [
        ("2030-01-07T09:00:30Z", "2030-01-07T10:00:00Z"),  # not on a full minute
        ("2030-01-07T09:00:00", "2030-01-07T10:00:00"),  # no time zone
        ("tomorrow", "2030-01-07T10:00:00Z"),
    ],
)
def test_timestamps_must_be_full_minutes_with_a_time_zone(
    client_as: ClientFactory, doctor: User, starts_at: str, ends_at: str
) -> None:
    body = {"startsAt": starts_at, "endsAt": ends_at}

    assert client_as(doctor).post("/api/v1/absences", json=body).status_code == 422


def test_an_absence_over_a_booked_appointment_is_rejected(
    client_as: ClientFactory, doctor: User, make_committed_user: UserFactory, db_engine: Engine
) -> None:
    starts_at = future_minute(db_engine, timedelta(days=4))
    appointment = book(db_engine, doctor, make_committed_user(), starts_at)
    client = client_as(doctor)
    # Overlaps the last minute of the appointment.
    body = {
        "startsAt": iso(starts_at + timedelta(minutes=14)),
        "endsAt": iso(starts_at + timedelta(hours=1)),
    }

    response = client.post("/api/v1/absences", json=body)

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "ABSENCE_HAS_APPOINTMENTS"
    # Touching the end is no overlap, and a cancelled appointment no longer blocks.
    touching = {**body, "startsAt": iso(starts_at + timedelta(minutes=15))}
    assert client.post("/api/v1/absences", json=touching).status_code == 201
    with Session(db_engine) as session, session.begin():
        cancel_appointment(
            session, session.get_one(Appointment, appointment.id), cancelled_by_id=doctor.id
        )
    assert client.post("/api/v1/absences", json=body).status_code == 201


def test_a_doctor_has_at_most_100_open_absences(
    client_as: ClientFactory, doctor: User, db_engine: Engine
) -> None:
    start = future_minute(db_engine, timedelta(days=1))
    with Session(db_engine) as session, session.begin():
        session.add_all(
            Absence(
                doctor_id=doctor.id,
                starts_at=start + timedelta(hours=i),
                ends_at=start + timedelta(hours=i, minutes=30),
                created_by_id=doctor.id,
            )
            for i in range(99)
        )
        # Ended absences do not count.
        session.add(
            Absence(
                doctor_id=doctor.id,
                starts_at=start - timedelta(days=3),
                ends_at=start - timedelta(days=2),
                created_by_id=doctor.id,
            )
        )
    client = client_as(doctor)
    body = absence_body(db_engine, timedelta(days=30), timedelta(hours=1))

    assert client.post("/api/v1/absences", json=body).status_code == 201
    response = client.post("/api/v1/absences", json=body)
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "CONFLICT"


def test_removing_absences(
    client_as: ClientFactory,
    doctor: User,
    staff: User,
    make_committed_user: UserFactory,
    db_engine: Engine,
) -> None:
    body = absence_body(db_engine, timedelta(days=2), timedelta(hours=2))
    first, second = (client_as(doctor).post("/api/v1/absences", json=body).json() for _ in range(2))
    other_doctor = client_as(make_committed_user(Role.DOCTOR))
    patient = client_as(make_committed_user())

    assert other_doctor.delete(f"/api/v1/absences/{first['id']}").status_code == 404
    assert patient.delete(f"/api/v1/absences/{first['id']}").status_code == 403
    assert client_as(None).delete(f"/api/v1/absences/{first['id']}").status_code == 401
    assert client_as(doctor).delete(f"/api/v1/absences/{first['id']}").status_code == 204
    assert client_as(doctor).delete(f"/api/v1/absences/{first['id']}").status_code == 404
    assert client_as(staff).delete(f"/api/v1/absences/{second['id']}").status_code == 204
    assert client_as(staff).delete(f"/api/v1/absences/{uuid.uuid4()}").status_code == 404
    assert client_as(staff).delete("/api/v1/absences/not-a-uuid").status_code == 422

    [event] = audit_events(db_engine, AuditAction.ABSENCE_DELETED, f"absence:{second['id']}")
    assert event.actor_id == staff.id
    with Session(db_engine) as session:
        count = session.scalar(
            select(func.count()).select_from(Absence).where(Absence.doctor_id == doctor.id)
        )
    assert count == 0


# ---------- Schedule ----------


def test_the_schedule_lists_hours_and_absences_that_have_not_ended(
    client_as: ClientFactory, staff: User, doctor: User, db_engine: Engine
) -> None:
    client = client_as(staff)
    put_hours(client, doctor, WEEK)
    later = absence_body(db_engine, timedelta(days=9), timedelta(hours=1), doctorId=str(doctor.id))
    sooner = absence_body(db_engine, timedelta(days=2), timedelta(hours=1), doctorId=str(doctor.id))
    later_id = client.post("/api/v1/absences", json=later).json()["id"]
    sooner_id = client.post("/api/v1/absences", json=sooner).json()["id"]
    ended = future_minute(db_engine, timedelta(days=-3))
    with Session(db_engine) as session, session.begin():
        session.add(
            Absence(
                doctor_id=doctor.id,
                starts_at=ended,
                ends_at=ended + timedelta(hours=1),
                created_by_id=staff.id,
            )
        )

    response = client.get(f"/api/v1/doctors/{doctor.id}/schedule")

    assert response.status_code == 200
    body = response.json()
    assert body["workingHours"] == WEEK
    assert [absence["id"] for absence in body["absences"]] == [sooner_id, later_id]


def test_only_practice_roles_read_a_schedule_and_doctors_only_their_own(
    client_as: ClientFactory, make_committed_user: UserFactory, doctor: User
) -> None:
    path = f"/api/v1/doctors/{doctor.id}/schedule"

    assert client_as(doctor).get(path).status_code == 200
    assert client_as(make_committed_user(Role.ADMIN)).get(path).status_code == 200
    assert client_as(make_committed_user(Role.DOCTOR)).get(path).status_code == 404
    assert client_as(make_committed_user()).get(path).status_code == 403
    assert client_as(None).get(path).status_code == 401
    assert (
        client_as(make_committed_user(Role.STAFF))
        .get(f"/api/v1/doctors/{uuid.uuid4()}/schedule")
        .status_code
        == 404
    )
