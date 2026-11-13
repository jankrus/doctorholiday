"""POST /api/v1/appointments (A08, BR-09, BR-10, BR-24), #17.

Includes the acceptance test for atomic booking: two simultaneous bookings of the same time end
in exactly one 201 and one 409.
"""

import threading
import uuid
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from datetime import date, time, timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, update
from sqlalchemy.orm import Session

from doctorholiday.models import Appointment, AuditAction, AuditOutcome, Role, User
from doctorholiday.repositories.appointments import cancel_appointment
from tests.db.conftest import ClientFactory, UserFactory, database_now, practice_settings
from tests.db.helpers import (
    add_absence,
    at,
    audit_events,
    book,
    get_appointment,
    iso,
    new_guest,
    next_monday,
    set_hours,
)

# For requests that are rejected; successful guest bookings use new_guest().
GUEST = new_guest()


@pytest.fixture
def monday(db_engine: Engine) -> date:
    return next_monday(db_engine)


@pytest.fixture
def doctor(make_committed_user: UserFactory, db_engine: Engine) -> User:
    doctor = make_committed_user(Role.DOCTOR)
    set_hours(db_engine, doctor, (1, time(8), time(10)), (2, time(8), time(10)))
    return doctor


@pytest.fixture
def patient(make_committed_user: UserFactory) -> User:
    return make_committed_user()


@pytest.fixture
def staff(make_committed_user: UserFactory) -> User:
    return make_committed_user(Role.STAFF)


def booking(doctor: User, starts_at: Any, **extra: Any) -> dict[str, Any]:
    return {"doctorId": str(doctor.id), "startsAt": iso(starts_at), "reason": "CHECKUP", **extra}


def post(client: TestClient, body: dict[str, Any]) -> Any:
    return client.post("/api/v1/appointments", json=body)


def error_code(response: Any) -> str:
    return response.json()["error"]["code"]


# ---------- Happy paths ----------


def test_a_patient_books_for_themselves(
    client_as: ClientFactory, doctor: User, patient: User, monday: date, db_engine: Engine
) -> None:
    response = post(
        client_as(patient), booking(doctor, at(monday, 8, 15), reason="BLOOD_TEST_FASTING")
    )

    assert response.status_code == 201
    body = response.json()
    assert body["status"] == "BOOKED"
    assert body["reason"] == "BLOOD_TEST_FASTING"
    assert body["doctor"] == {"id": str(doctor.id), "displayName": doctor.display_name}
    assert body["startsAt"] == iso(at(monday, 8, 15))
    assert body["endsAt"] == iso(at(monday, 8, 30))
    assert body["bookedBy"] == "PATIENT"
    # The patient's own view: no patient or guest block (closed schema in the contract check).
    assert "patient" not in body
    assert "guest" not in body
    row = get_appointment(db_engine, body["id"])
    assert row.patient_id == patient.id
    assert row.booked_by_id == patient.id
    [event] = audit_events(db_engine, AuditAction.APPOINTMENT_BOOKED, f"appointment:{body['id']}")
    assert event.actor_id == patient.id
    assert event.outcome is AuditOutcome.SUCCESS
    assert event.details is None


def test_the_appointment_length_comes_from_the_settings(
    client_as: ClientFactory, doctor: User, patient: User, monday: date, db_engine: Engine
) -> None:
    with practice_settings(db_engine, appointment_minutes=30):
        response = post(client_as(patient), booking(doctor, at(monday, 8, 30)))

    assert response.status_code == 201
    assert response.json()["endsAt"] == iso(at(monday, 9))


def test_staff_books_for_a_patient_by_e_mail(
    client_as: ClientFactory,
    doctor: User,
    patient: User,
    staff: User,
    monday: date,
    db_engine: Engine,
) -> None:
    response = post(
        client_as(staff), booking(doctor, at(monday, 9), patientEmail=patient.email.upper())
    )

    assert response.status_code == 201
    body = response.json()
    assert body["patient"] == {
        "id": str(patient.id),
        "deleted": False,
        "email": patient.email,
        "displayName": patient.display_name,
    }
    assert "guest" not in body
    assert body["bookedBy"] == "PRACTICE"
    [event] = audit_events(db_engine, AuditAction.APPOINTMENT_BOOKED, f"appointment:{body['id']}")
    assert event.actor_id == staff.id


def test_staff_books_for_a_guest_and_the_audit_holds_no_guest_data(
    client_as: ClientFactory, doctor: User, staff: User, monday: date, db_engine: Engine
) -> None:
    guest_contact = new_guest()
    response = post(client_as(staff), booking(doctor, at(monday, 9, 15), guest=guest_contact))

    assert response.status_code == 201
    body = response.json()
    assert body["guest"] == guest_contact
    assert "patient" not in body
    assert body["bookedBy"] == "PRACTICE"
    row = get_appointment(db_engine, body["id"])
    assert (row.patient_id, row.guest_name, row.guest_phone) == (
        None,
        guest_contact["name"],
        guest_contact["phone"],
    )
    [event] = audit_events(db_engine, AuditAction.APPOINTMENT_BOOKED, f"appointment:{body['id']}")
    assert guest_contact["name"] not in repr(event.details)
    assert event.target == f"appointment:{body['id']}"


# ---------- Who books for whom ----------


@pytest.mark.parametrize(
    "extra",
    [
        {"patientEmail": "someone@example.com"},
        {"guest": GUEST},
        {"patientEmail": "a@example.com", "guest": GUEST},
    ],
)
def test_a_patient_cannot_book_for_anyone_else(
    client_as: ClientFactory, doctor: User, patient: User, monday: date, extra: dict[str, Any]
) -> None:
    response = post(client_as(patient), booking(doctor, at(monday, 8), **extra))

    assert response.status_code == 403
    assert error_code(response) == "FORBIDDEN"


@pytest.mark.parametrize("extra", [{}, {"patientEmail": "a@example.com", "guest": GUEST}])
def test_staff_names_exactly_one_party(
    client_as: ClientFactory, doctor: User, staff: User, monday: date, extra: dict[str, Any]
) -> None:
    response = post(client_as(staff), booking(doctor, at(monday, 8), **extra))

    assert response.status_code == 422
    assert error_code(response) == "VALIDATION_ERROR"


def test_staff_books_only_for_active_patients(
    client_as: ClientFactory,
    doctor: User,
    staff: User,
    make_committed_user: UserFactory,
    monday: date,
    db_engine: Engine,
) -> None:
    inactive = make_committed_user()
    with Session(db_engine) as session, session.begin():
        session.execute(update(User).where(User.id == inactive.id).values(is_active=False))
    client = client_as(staff)

    for email in ("nobody@example.com", make_committed_user(Role.STAFF).email, inactive.email):
        response = post(client, booking(doctor, at(monday, 8), patientEmail=email))
        assert response.status_code == 404
        assert error_code(response) == "NOT_FOUND"


@pytest.mark.parametrize("role", [Role.DOCTOR, Role.ADMIN])
def test_doctors_and_admins_do_not_book(
    client_as: ClientFactory,
    make_committed_user: UserFactory,
    doctor: User,
    patient: User,
    monday: date,
    role: Role,
) -> None:
    response = post(
        client_as(make_committed_user(role)),
        booking(doctor, at(monday, 8), patientEmail=patient.email),
    )

    assert response.status_code == 403
    assert error_code(response) == "FORBIDDEN"


def test_booking_needs_a_session(client_as: ClientFactory, doctor: User, monday: date) -> None:
    assert post(client_as(None), booking(doctor, at(monday, 8))).status_code == 401


def test_only_active_doctors_can_be_booked(
    client_as: ClientFactory, patient: User, staff: User, monday: date, db_engine: Engine
) -> None:
    set_hours(db_engine, staff, (1, time(8), time(10)))  # hours, but not a doctor
    client = client_as(patient)

    for doctor_id in (uuid.uuid4(), staff.id):
        response = client.post(
            "/api/v1/appointments",
            json={"doctorId": str(doctor_id), "startsAt": iso(at(monday, 8)), "reason": "CHECKUP"},
        )
        assert response.status_code == 404


# ---------- Validation ----------


@pytest.mark.parametrize(
    "change",
    [
        {"reason": "I have a headache"},  # no free text (BR-10)
        {"reason": None},
        {"startsAt": "2030-01-07T08:00:00"},  # no time zone
        {"doctorId": "not-a-uuid"},
        {"note": "extra field"},
        {"guest": {"name": "Erika", "phone": "071112345678"}},  # not E.164
        {"guest": {"name": "<b>Erika</b>", "phone": "+4971112345678"}},
        {"guest": {"name": "Erika"}},
        {"patientEmail": "not-an-e-mail"},
    ],
)
def test_invalid_bodies_are_rejected(
    client_as: ClientFactory, doctor: User, staff: User, monday: date, change: dict[str, Any]
) -> None:
    body = {**booking(doctor, at(monday, 8)), **change}

    response = post(client_as(staff), body)

    assert response.status_code == 422
    assert error_code(response) == "VALIDATION_ERROR"


# ---------- Available time (BR-23) ----------


def test_only_offered_times_can_be_booked(
    client_as: ClientFactory, doctor: User, patient: User, monday: date, db_engine: Engine
) -> None:
    add_absence(
        db_engine, doctor, at(monday + timedelta(days=1), 8), at(monday + timedelta(days=1), 9)
    )
    now = database_now(db_engine)
    client = client_as(patient)

    for starts_at in (
        at(monday, 10),  # after the working hours
        at(monday, 7, 45),  # before
        at(monday, 8, 5),  # not a step of 15 minutes
        at(monday, 9, 50),  # would end after 10:00
        at(monday + timedelta(days=1), 8, 45),  # absent
        at(monday + timedelta(days=2), 8),  # Wednesday: no hours
        at(monday - timedelta(days=7 * 3), 8),  # in the past
        at(monday + timedelta(days=7 * 53), 8),  # more than 365 days ahead
    ):
        response = post(client, booking(doctor, starts_at))
        assert response.status_code == 409, starts_at
        assert error_code(response) == "TIME_NOT_AVAILABLE"
    assert monday - timedelta(days=21) < now.date()


def test_a_booked_time_is_already_booked(
    client_as: ClientFactory,
    doctor: User,
    patient: User,
    make_committed_user: UserFactory,
    monday: date,
    db_engine: Engine,
) -> None:
    other = client_as(make_committed_user())
    assert post(client_as(patient), booking(doctor, at(monday, 8))).status_code == 201

    response = post(other, booking(doctor, at(monday, 8)))
    assert response.status_code == 409
    assert error_code(response) == "TIME_ALREADY_BOOKED"
    # Booked earlier with a longer appointment length: 08:30-09:00 blocks the 08:45 step too.
    book(db_engine, doctor, patient, at(monday, 8, 30), minutes=30)
    response = post(other, booking(doctor, at(monday, 8, 45)))
    assert response.status_code == 409
    assert error_code(response) == "TIME_ALREADY_BOOKED"
    # Another doctor at the same time is fine.
    second = make_committed_user(Role.DOCTOR)
    set_hours(db_engine, second, (1, time(8), time(9)))
    assert post(other, booking(second, at(monday, 8))).status_code == 201


def test_a_cancelled_time_can_be_booked_again(
    client_as: ClientFactory,
    doctor: User,
    patient: User,
    make_committed_user: UserFactory,
    monday: date,
    db_engine: Engine,
) -> None:
    appointment = book(db_engine, doctor, patient, at(monday, 8))
    with Session(db_engine) as session, session.begin():
        cancel_appointment(
            session, session.get_one(Appointment, appointment.id), cancelled_by_id=patient.id
        )

    assert post(client_as(make_committed_user()), booking(doctor, at(monday, 8))).status_code == 201


# ---------- Open-appointment limit (BR-09, BR-24) ----------


def test_a_patient_has_at_most_five_open_appointments(
    client_as: ClientFactory,
    doctor: User,
    patient: User,
    staff: User,
    monday: date,
    db_engine: Engine,
) -> None:
    # Past and cancelled appointments do not count.
    book(db_engine, doctor, patient, at(monday - timedelta(days=21), 8))
    cancelled = book(db_engine, doctor, patient, at(monday, 9, 45))
    with Session(db_engine) as session, session.begin():
        cancel_appointment(
            session, session.get_one(Appointment, cancelled.id), cancelled_by_id=patient.id
        )
    client = client_as(patient)
    for minute in (0, 15, 30, 45):
        assert post(client, booking(doctor, at(monday, 8, minute))).status_code == 201
    # Booked by staff counts as well.
    staff_booking = booking(doctor, at(monday, 9), patientEmail=patient.email)
    assert post(client_as(staff), staff_booking).status_code == 201

    for who, body in (
        (client, booking(doctor, at(monday, 9, 15))),
        (client_as(staff), {**staff_booking, "startsAt": iso(at(monday, 9, 30))}),
    ):
        response = post(who, body)
        assert response.status_code == 409
        assert error_code(response) == "APPOINTMENT_LIMIT_REACHED"


def test_a_guest_phone_has_at_most_five_open_appointments(
    client_as: ClientFactory, doctor: User, staff: User, monday: date
) -> None:
    client = client_as(staff)
    phone = f"+49170{uuid.uuid4().int % 10**8:08d}"
    guest = {"name": "Guest", "phone": phone}
    for minute in (0, 15, 30, 45):
        assert post(client, booking(doctor, at(monday, 8, minute), guest=guest)).status_code == 201
    assert post(client, booking(doctor, at(monday, 9), guest=guest)).status_code == 201

    response = post(
        client, booking(doctor, at(monday, 9, 15), guest={**guest, "name": "Other name"})
    )
    assert response.status_code == 409
    assert error_code(response) == "APPOINTMENT_LIMIT_REACHED"
    # Another number is not affected.
    other = {"name": "Guest", "phone": f"{phone[:-1]}{(int(phone[-1]) + 1) % 10}"}
    assert post(client, booking(doctor, at(monday, 9, 15), guest=other)).status_code == 201


# ---------- Concurrency (acceptance criterion) ----------

ROUNDS = 10


def _post_together(clients: list[TestClient], bodies: list[dict[str, Any]]) -> list[Any]:
    ready = threading.Barrier(len(clients))

    def run(index: int) -> Any:
        ready.wait(timeout=5)
        return post(clients[index], bodies[index])

    with ThreadPoolExecutor(max_workers=len(clients)) as pool:
        return list(pool.map(run, range(len(clients))))


def test_two_simultaneous_bookings_of_the_same_time_yield_one_201_and_one_409(
    client_as: ClientFactory, make_committed_user: UserFactory, db_engine: Engine, monday: date
) -> None:
    for _ in range(ROUNDS):
        clients = [client_as(make_committed_user()) for _ in range(2)]
        doctor = make_committed_user(Role.DOCTOR)
        set_hours(db_engine, doctor, (1, time(8), time(9)))
        body = booking(doctor, at(monday, 8))

        responses = _post_together(clients, [body, body])

        assert Counter(r.status_code for r in responses) == {201: 1, 409: 1}
        [conflict] = [r for r in responses if r.status_code == 409]
        assert error_code(conflict) == "TIME_ALREADY_BOOKED"
        with Session(db_engine) as session:
            assert session.query(Appointment).filter_by(doctor_id=doctor.id).count() == 1


def test_simultaneous_bookings_cannot_pass_the_limit_together(
    client_as: ClientFactory, make_committed_user: UserFactory, db_engine: Engine, monday: date
) -> None:
    patient = make_committed_user()
    doctors = [make_committed_user(Role.DOCTOR) for _ in range(2)]
    for doctor in doctors:
        set_hours(db_engine, doctor, (1, time(8), time(10)))
    for minute in (0, 15, 30, 45):
        book(db_engine, doctors[0], patient, at(monday, 8, minute))
    clients = [client_as(patient) for _ in range(2)]

    # Two different doctors, so only the limit can stop one of them.
    responses = _post_together(clients, [booking(d, at(monday, 9)) for d in doctors])

    assert sorted(r.status_code for r in responses) == [201, 409]
    [conflict] = [r for r in responses if r.status_code == 409]
    assert error_code(conflict) == "APPOINTMENT_LIMIT_REACHED"
