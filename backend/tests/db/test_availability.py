"""GET /api/v1/availability (A07, BR-23) against a real database, #17.

The rules themselves are tested in tests/test_scheduling.py; this checks the endpoint with
working hours, absences and bookings from the database, relative to the database clock.
"""

import uuid
from datetime import UTC, date, datetime, time, timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine
from sqlalchemy.orm import Session

from doctorholiday.models import (
    Absence,
    AppointmentReason,
    Role,
    User,
)
from doctorholiday.repositories.appointments import book_appointment, cancel_appointment
from doctorholiday.scheduling import PRACTICE_TIME_ZONE as BERLIN
from tests.db.conftest import ClientFactory, UserFactory, database_now, practice_settings
from tests.db.helpers import at, every_day, iso, next_monday, set_hours


def query(client: TestClient, starts_from: datetime, starts_before: datetime, **params: Any) -> Any:
    return client.get(
        "/api/v1/availability",
        params={"from": iso(starts_from), "to": iso(starts_before), **params},
    )


def starts(response: Any, doctor: User | None = None) -> list[str]:
    assert response.status_code == 200, response.json()
    return [
        item["startsAt"]
        for item in response.json()["items"]
        if doctor is None or item["doctor"]["id"] == str(doctor.id)
    ]


@pytest.fixture
def doctor(make_committed_user: UserFactory) -> User:
    return make_committed_user(Role.DOCTOR)


@pytest.fixture
def patient_client(client_as: ClientFactory, make_committed_user: UserFactory) -> TestClient:
    return client_as(make_committed_user())


def test_multiple_entries_per_day_absences_and_bookings(
    patient_client: TestClient,
    doctor: User,
    make_committed_user: UserFactory,
    db_engine: Engine,
) -> None:
    monday = next_monday(db_engine)
    set_hours(db_engine, doctor, (1, time(8), time(9)), (1, time(14), time(14, 40)))
    patient = make_committed_user()
    with Session(db_engine, expire_on_commit=False) as session, session.begin():
        session.add(
            Absence(
                doctor_id=doctor.id,
                starts_at=at(monday, 8, 20),
                ends_at=at(monday, 8, 31),
                created_by_id=doctor.id,
            )
        )
        booked = book_appointment(
            session,
            doctor_id=doctor.id,
            starts_at=at(monday, 14),
            ends_at=at(monday, 14, 15),
            booked_by_id=patient.id,
            reason=AppointmentReason.CHECKUP,
            patient_id=patient.id,
        )
        cancelled = book_appointment(
            session,
            doctor_id=doctor.id,
            starts_at=at(monday, 8),
            ends_at=at(monday, 8, 15),
            booked_by_id=patient.id,
            reason=AppointmentReason.CHECKUP,
            patient_id=patient.id,
        )
        cancel_appointment(session, cancelled, cancelled_by_id=patient.id)

    response = query(
        patient_client, at(monday, 0), at(monday + timedelta(days=1), 0), doctorId=str(doctor.id)
    )

    assert starts(response) == [
        iso(at(monday, 8)),  # the cancelled appointment does not block
        # 08:15 and 08:30 overlap the absence
        iso(at(monday, 8, 45)),
        # 14:00 is booked, 14:30 would end after 14:40
        iso(at(monday, 14, 15)),
    ]
    first = response.json()["items"][0]
    assert first == {
        "doctor": {"id": str(doctor.id), "displayName": doctor.display_name},
        "startsAt": iso(at(monday, 8)),
        "endsAt": iso(at(monday, 8, 15)),
    }
    assert booked.status == "BOOKED"


def test_the_appointment_length_comes_from_the_settings(
    patient_client: TestClient, doctor: User, db_engine: Engine
) -> None:
    monday = next_monday(db_engine)
    set_hours(db_engine, doctor, (1, time(8), time(9)))

    with practice_settings(db_engine, appointment_minutes=25):
        response = query(patient_client, at(monday, 0), at(monday, 23), doctorId=str(doctor.id))

    assert starts(response) == [iso(at(monday, 8)), iso(at(monday, 8, 25))]
    assert response.json()["items"][0]["endsAt"] == iso(at(monday, 8, 25))


def _next_dst_change(engine: Engine) -> date:
    """The first day 3-330 days ahead whose UTC offset in Berlin differs from the day before."""
    day = database_now(engine).astimezone(BERLIN).date() + timedelta(days=3)
    for _ in range(330):
        if at(day, 12).utcoffset() != at(day - timedelta(days=1), 12).utcoffset():
            return day
        day += timedelta(days=1)
    pytest.fail("no daylight-saving change within 330 days")


def test_a_daylight_saving_change_keeps_the_local_time(
    patient_client: TestClient, doctor: User, db_engine: Engine
) -> None:
    change = _next_dst_change(db_engine)
    set_hours(db_engine, doctor, *every_day(time(8), time(8, 15)))
    first_day = change - timedelta(days=3)

    response = query(
        patient_client,
        at(first_day, 0),
        at(first_day + timedelta(days=7), 0),
        doctorId=str(doctor.id),
    )

    found = [datetime.fromisoformat(value) for value in starts(response)]
    assert [moment.astimezone(BERLIN).time() for moment in found] == [time(8)] * 7
    assert [moment.astimezone(BERLIN).date() for moment in found] == [
        first_day + timedelta(days=i) for i in range(7)
    ]
    # One hour apart in UTC before and after the change.
    offsets = {moment.astimezone(BERLIN).utcoffset() for moment in found}
    assert len(offsets) == 2


def test_only_future_times_are_offered(
    patient_client: TestClient, doctor: User, db_engine: Engine
) -> None:
    set_hours(db_engine, doctor, *every_day(time(0), time(23, 55)))
    now = database_now(db_engine)

    response = query(
        patient_client, now - timedelta(days=1), now + timedelta(hours=1), doctorId=str(doctor.id)
    )

    found = [datetime.fromisoformat(value) for value in starts(response)]
    assert found
    assert all(moment > now for moment in found)


def test_nothing_is_offered_more_than_365_days_ahead(
    patient_client: TestClient, doctor: User, db_engine: Engine
) -> None:
    set_hours(db_engine, doctor, *every_day(time(0), time(23, 55)))
    limit = database_now(db_engine) + timedelta(days=365)

    response = query(
        patient_client,
        limit - timedelta(days=1),
        limit + timedelta(days=1),
        doctorId=str(doctor.id),
        limit=100,
    )

    found = [datetime.fromisoformat(value) for value in starts(response)]
    assert found
    assert max(found) <= limit
    assert response.json()["total"] < 2 * 24 * 4  # nothing after the limit


def test_the_range_spans_at_most_31_days(patient_client: TestClient, db_engine: Engine) -> None:
    start = datetime.combine(next_monday(db_engine), time(), tzinfo=UTC)

    assert query(patient_client, start, start + timedelta(days=31)).status_code == 200
    for end in (start + timedelta(days=31, minutes=1), start, start - timedelta(hours=1)):
        response = query(patient_client, start, end)
        assert response.status_code == 422
        assert response.json()["error"]["code"] == "VALIDATION_ERROR"


@pytest.mark.parametrize(
    "params",
    [
        {},
        {"from": "2030-01-07T00:00:00Z"},
        {"to": "2030-01-07T00:00:00Z"},
        {"from": "2030-01-07T00:00:00", "to": "2030-01-08T00:00:00"},  # no time zone
        {"from": "2030-01-07T00:00:00Z", "to": "2030-01-08T00:00:00Z", "doctorId": "nope"},
        {"from": "2030-01-07T00:00:00Z", "to": "2030-01-08T00:00:00Z", "limit": "101"},
        {"from": "2030-01-07T00:00:00Z", "to": "2030-01-08T00:00:00Z", "patientId": "x"},
    ],
)
def test_invalid_queries_are_rejected(patient_client: TestClient, params: dict[str, str]) -> None:
    response = patient_client.get("/api/v1/availability", params=params)

    assert response.status_code == 422


def test_sorted_by_start_then_doctor_and_paginated(
    patient_client: TestClient, make_committed_user: UserFactory, db_engine: Engine
) -> None:
    ours = [make_committed_user(Role.DOCTOR) for _ in range(2)]
    for doctor in ours:
        # 06:00 is a time few other tests' doctors work, so the page holds all of ours.
        set_hours(db_engine, doctor, (1, time(6), time(6, 30)))
    monday = next_monday(db_engine)
    window = (at(monday, 6), at(monday, 6, 30))

    everything = query(patient_client, *window, limit=100).json()
    items = [
        item for item in everything["items"] if item["doctor"]["id"] in {str(d.id) for d in ours}
    ]

    assert [item["startsAt"] for item in items] == [iso(at(monday, 6))] * 2 + [
        iso(at(monday, 6, 15))
    ] * 2
    keys = [
        (item["startsAt"], item["doctor"]["displayName"], item["doctor"]["id"])
        for item in everything["items"]
    ]
    assert keys == sorted(keys)
    one = query(patient_client, *window, limit=1, offset=1).json()
    assert one["items"] == everything["items"][1:2]
    assert one["total"] == everything["total"]
    assert (one["limit"], one["offset"]) == (1, 1)


def test_an_unknown_or_inactive_doctor_has_no_times(
    patient_client: TestClient, make_committed_user: UserFactory, db_engine: Engine
) -> None:
    staff = make_committed_user(Role.STAFF)
    set_hours(db_engine, staff, (1, time(8), time(9)))  # not a doctor
    monday = next_monday(db_engine)

    for doctor_id in (uuid.uuid4(), staff.id):
        response = query(patient_client, at(monday, 0), at(monday, 23), doctorId=str(doctor_id))
        assert response.json() == {"limit": 20, "offset": 0, "total": 0, "items": []}


@pytest.mark.parametrize("role", list(Role))
def test_every_role_sees_availability_but_no_session_does(
    client_as: ClientFactory, make_committed_user: UserFactory, db_engine: Engine, role: Role
) -> None:
    monday = next_monday(db_engine)

    assert (
        query(client_as(make_committed_user(role)), at(monday, 0), at(monday, 23)).status_code
        == 200
    )
    assert query(client_as(None), at(monday, 0), at(monday, 23)).status_code == 401


def test_a_booking_blocks_only_its_own_doctor(
    patient_client: TestClient,
    make_committed_user: UserFactory,
    db_engine: Engine,
) -> None:
    first, second = make_committed_user(Role.DOCTOR), make_committed_user(Role.DOCTOR)
    monday = next_monday(db_engine)
    for doctor in (first, second):
        set_hours(db_engine, doctor, (1, time(8), time(8, 30)))
    patient = make_committed_user()
    with Session(db_engine) as session, session.begin():
        book_appointment(
            session,
            doctor_id=first.id,
            starts_at=at(monday, 8),
            ends_at=at(monday, 8, 15),
            booked_by_id=patient.id,
            reason=AppointmentReason.CHECKUP,
            patient_id=patient.id,
        )

    def found(doctor: User) -> list[str]:
        return starts(query(patient_client, at(monday, 0), at(monday, 23), doctorId=str(doctor.id)))

    assert found(first) == [iso(at(monday, 8, 15))]
    assert found(second) == [iso(at(monday, 8)), iso(at(monday, 8, 15))]
