"""Cancellation (A09, A10, BR-11) and rescheduling (A30, BR-22), #17."""

import uuid
from datetime import date, datetime, time, timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, func
from sqlalchemy.orm import Session

from doctorholiday.models import AccessPurpose, AdminAccessGrant, AuditAction, Role, User
from tests.db.conftest import ClientFactory, UserFactory, database_now, practice_settings
from tests.db.helpers import (
    at,
    audit_events,
    book,
    get_appointment,
    iso,
    new_guest,
    next_monday,
    set_hours,
)


@pytest.fixture
def monday(db_engine: Engine) -> date:
    return next_monday(db_engine)


@pytest.fixture
def doctor(make_committed_user: UserFactory, db_engine: Engine) -> User:
    doctor = make_committed_user(Role.DOCTOR)
    set_hours(db_engine, doctor, (1, time(8), time(10)))
    return doctor


@pytest.fixture
def patient(make_committed_user: UserFactory) -> User:
    return make_committed_user()


def soon(engine: Engine, hours: int) -> datetime:
    """A start `hours` from now, on a full minute: inside the 24-hour cancellation deadline."""
    return (database_now(engine) + timedelta(hours=hours)).replace(second=0, microsecond=0)


def cancel(client: TestClient, appointment_id: object) -> Any:
    return client.post(f"/api/v1/appointments/{appointment_id}/cancel")


def reschedule(
    client: TestClient, appointment_id: object, starts_at: datetime, **extra: Any
) -> Any:
    return client.post(
        f"/api/v1/appointments/{appointment_id}/reschedule",
        json={"startsAt": iso(starts_at), **extra},
    )


def error_code(response: Any) -> str:
    return response.json()["error"]["code"]


def grant_access(engine: Engine, admin: User) -> AdminAccessGrant:
    """An active TBAC grant (A19 itself is #55)."""
    with Session(engine, expire_on_commit=False) as session, session.begin():
        grant = AdminAccessGrant(
            admin_id=admin.id,
            purpose=AccessPurpose.SUPPORT_REQUEST,
            created_at=func.now(),
            expires_at=func.now() + timedelta(minutes=30),
        )
        session.add(grant)
    return grant


# ---------- Cancellation ----------


def test_a_patient_cancels_their_own_appointment_and_the_time_is_free_again(
    client_as: ClientFactory,
    doctor: User,
    patient: User,
    make_committed_user: UserFactory,
    monday: date,
    db_engine: Engine,
) -> None:
    appointment = book(db_engine, doctor, patient, at(monday, 8))

    response = cancel(client_as(patient), appointment.id)

    assert response.status_code == 200
    body = response.json()
    assert body["id"] == str(appointment.id)
    assert body["status"] == "CANCELLED"
    assert body["cancelledBy"] == "PATIENT"
    assert body["cancelledAt"]
    assert "patient" not in body
    [event] = audit_events(
        db_engine, AuditAction.APPOINTMENT_CANCELLED, f"appointment:{appointment.id}"
    )
    assert event.actor_id == patient.id
    rebooked = client_as(make_committed_user()).post(
        "/api/v1/appointments",
        json={"doctorId": str(doctor.id), "startsAt": iso(at(monday, 8)), "reason": "OTHER"},
    )
    assert rebooked.status_code == 201


def test_a_patient_cannot_cancel_someone_elses_appointment(
    client_as: ClientFactory,
    doctor: User,
    patient: User,
    make_committed_user: UserFactory,
    monday: date,
    db_engine: Engine,
) -> None:
    guest_contact = new_guest()
    foreign = book(db_engine, doctor, make_committed_user(), at(monday, 8))
    staff = make_committed_user(Role.STAFF)
    guest = (
        client_as(staff)
        .post(
            "/api/v1/appointments",
            json={
                "doctorId": str(doctor.id),
                "startsAt": iso(at(monday, 9)),
                "reason": "OTHER",
                "guest": guest_contact,
            },
        )
        .json()
    )
    client = client_as(patient)

    for appointment_id in (foreign.id, guest["id"], uuid.uuid4()):
        response = cancel(client, appointment_id)
        assert response.status_code == 404
        assert error_code(response) == "NOT_FOUND"
    assert get_appointment(db_engine, foreign.id).status == "BOOKED"


def test_a_patient_cancels_only_until_the_deadline(
    client_as: ClientFactory, doctor: User, patient: User, db_engine: Engine
) -> None:
    appointment = book(db_engine, doctor, patient, soon(db_engine, 3))
    client = client_as(patient)

    response = cancel(client, appointment.id)
    assert response.status_code == 409
    assert error_code(response) == "CANCELLATION_DEADLINE_PASSED"
    with practice_settings(db_engine, cancellation_deadline_hours=2):
        assert cancel(client, appointment.id).status_code == 200


@pytest.mark.parametrize("role", [Role.STAFF, Role.DOCTOR])
def test_the_practice_cancels_any_appointment_until_the_start(
    client_as: ClientFactory,
    make_committed_user: UserFactory,
    doctor: User,
    patient: User,
    db_engine: Engine,
    role: Role,
) -> None:
    appointment = book(db_engine, doctor, patient, soon(db_engine, 1))
    actor = make_committed_user(role)

    response = cancel(client_as(actor), appointment.id)

    assert response.status_code == 200
    body = response.json()
    assert body["cancelledBy"] == "PRACTICE"
    assert body["patient"]["id"] == str(patient.id)
    assert get_appointment(db_engine, appointment.id).cancelled_by_id == actor.id


def test_only_booked_appointments_that_have_not_started_can_be_cancelled(
    client_as: ClientFactory,
    make_committed_user: UserFactory,
    doctor: User,
    patient: User,
    monday: date,
    db_engine: Engine,
) -> None:
    staff = client_as(make_committed_user(Role.STAFF))
    started = book(db_engine, doctor, patient, soon(db_engine, 0) - timedelta(minutes=5))
    cancelled = book(db_engine, doctor, patient, at(monday, 8))
    assert cancel(staff, cancelled.id).status_code == 200

    for appointment_id in (started.id, cancelled.id):
        response = cancel(staff, appointment_id)
        assert response.status_code == 409
        assert error_code(response) == "APPOINTMENT_NOT_CANCELLABLE"


def test_an_admin_cancels_only_with_an_active_grant_and_the_access_is_audited(
    client_as: ClientFactory,
    make_committed_user: UserFactory,
    doctor: User,
    patient: User,
    monday: date,
    db_engine: Engine,
) -> None:
    admin = make_committed_user(Role.ADMIN)
    appointment = book(db_engine, doctor, patient, at(monday, 8))
    client = client_as(admin)

    response = cancel(client, appointment.id)
    assert response.status_code == 403
    assert error_code(response) == "ACCESS_GRANT_REQUIRED"

    grant = grant_access(db_engine, admin)
    assert cancel(client, appointment.id).status_code == 200
    [event] = audit_events(
        db_engine, AuditAction.APPOINTMENT_DATA_ACCESSED, f"appointment:{appointment.id}"
    )
    assert event.actor_id == admin.id
    assert event.details == {"grantId": str(grant.id)}


def test_cancelling_needs_a_session(
    client_as: ClientFactory, doctor: User, patient: User, monday: date, db_engine: Engine
) -> None:
    appointment = book(db_engine, doctor, patient, at(monday, 8))

    assert cancel(client_as(None), appointment.id).status_code == 401
    assert cancel(client_as(patient), "not-a-uuid").status_code == 422


# ---------- Rescheduling ----------


def test_a_patient_moves_their_appointment_and_the_old_time_is_free_again(
    client_as: ClientFactory,
    doctor: User,
    patient: User,
    make_committed_user: UserFactory,
    monday: date,
    db_engine: Engine,
) -> None:
    appointment = book(db_engine, doctor, patient, at(monday, 8))

    response = reschedule(client_as(patient), appointment.id, at(monday, 9, 15))

    assert response.status_code == 200
    body = response.json()
    assert body["id"] == str(appointment.id)
    assert (body["startsAt"], body["endsAt"]) == (iso(at(monday, 9, 15)), iso(at(monday, 9, 30)))
    assert body["status"] == "BOOKED"
    assert body["reason"] == "CHECKUP"
    row = get_appointment(db_engine, appointment.id)
    assert (row.patient_id, row.reason) == (patient.id, "CHECKUP")
    [event] = audit_events(
        db_engine, AuditAction.APPOINTMENT_RESCHEDULED, f"appointment:{appointment.id}"
    )
    assert event.details == {
        "oldStartsAt": iso(at(monday, 8)),
        "newStartsAt": iso(at(monday, 9, 15)),
    }
    rebooked = client_as(make_committed_user()).post(
        "/api/v1/appointments",
        json={"doctorId": str(doctor.id), "startsAt": iso(at(monday, 8)), "reason": "OTHER"},
    )
    assert rebooked.status_code == 201


def test_rescheduling_to_another_doctor(
    client_as: ClientFactory,
    doctor: User,
    patient: User,
    make_committed_user: UserFactory,
    monday: date,
    db_engine: Engine,
) -> None:
    other = make_committed_user(Role.DOCTOR)
    set_hours(db_engine, other, (1, time(14), time(15)))
    appointment = book(db_engine, doctor, patient, at(monday, 8))

    response = reschedule(
        client_as(make_committed_user(Role.STAFF)),
        appointment.id,
        at(monday, 14),
        doctorId=str(other.id),
    )

    assert response.status_code == 200
    assert response.json()["doctor"]["id"] == str(other.id)
    [event] = audit_events(
        db_engine, AuditAction.APPOINTMENT_RESCHEDULED, f"appointment:{appointment.id}"
    )
    assert event.details["oldDoctorId"] == str(doctor.id)
    assert event.details["newDoctorId"] == str(other.id)
    unknown = reschedule(
        client_as(patient), appointment.id, at(monday, 14), doctorId=str(uuid.uuid4())
    )
    assert unknown.status_code == 404


def test_the_own_old_time_does_not_block_the_new_one(
    client_as: ClientFactory, doctor: User, patient: User, monday: date, db_engine: Engine
) -> None:
    # 08:00-08:30, booked when appointments were 30 minutes long; 08:15 overlaps it.
    appointment = book(db_engine, doctor, patient, at(monday, 8), minutes=30)

    response = reschedule(client_as(patient), appointment.id, at(monday, 8, 15))

    assert response.status_code == 200
    assert response.json()["endsAt"] == iso(at(monday, 8, 30))


def test_a_failed_rescheduling_keeps_the_old_appointment(
    client_as: ClientFactory,
    doctor: User,
    patient: User,
    make_committed_user: UserFactory,
    monday: date,
    db_engine: Engine,
) -> None:
    appointment = book(db_engine, doctor, patient, at(monday, 8))
    book(db_engine, doctor, make_committed_user(), at(monday, 9))
    client = client_as(patient)

    taken = reschedule(client, appointment.id, at(monday, 9))
    assert taken.status_code == 409
    assert error_code(taken) == "TIME_ALREADY_BOOKED"
    for starts_at in (at(monday, 10), at(monday, 8, 7), at(monday + timedelta(days=1), 8)):
        response = reschedule(client, appointment.id, starts_at)
        assert response.status_code == 409
        assert error_code(response) == "TIME_NOT_AVAILABLE"

    row = get_appointment(db_engine, appointment.id)
    assert (row.doctor_id, row.starts_at, row.status) == (doctor.id, at(monday, 8), "BOOKED")


def test_a_patient_reschedules_only_their_own_appointments_until_the_deadline(
    client_as: ClientFactory,
    doctor: User,
    patient: User,
    make_committed_user: UserFactory,
    monday: date,
    db_engine: Engine,
) -> None:
    foreign = book(db_engine, doctor, make_committed_user(), at(monday, 8))
    near = book(db_engine, doctor, patient, soon(db_engine, 3))
    client = client_as(patient)

    assert reschedule(client, foreign.id, at(monday, 9)).status_code == 404
    response = reschedule(client, near.id, at(monday, 9))
    assert response.status_code == 409
    assert error_code(response) == "CANCELLATION_DEADLINE_PASSED"
    # The practice may move it until the start.
    staff = client_as(make_committed_user(Role.STAFF))
    assert reschedule(staff, near.id, at(monday, 9)).status_code == 200


def test_only_booked_appointments_that_have_not_started_can_be_moved(
    client_as: ClientFactory,
    make_committed_user: UserFactory,
    doctor: User,
    patient: User,
    monday: date,
    db_engine: Engine,
) -> None:
    staff = client_as(make_committed_user(Role.STAFF))
    started = book(db_engine, doctor, patient, soon(db_engine, 0) - timedelta(minutes=5))
    cancelled = book(db_engine, doctor, patient, at(monday, 8))
    assert cancel(staff, cancelled.id).status_code == 200

    for appointment_id in (started.id, cancelled.id):
        response = reschedule(staff, appointment_id, at(monday, 9))
        assert response.status_code == 409
        assert error_code(response) == "APPOINTMENT_NOT_RESCHEDULABLE"


def test_staff_moves_a_guest_appointment(
    client_as: ClientFactory, make_committed_user: UserFactory, doctor: User, monday: date
) -> None:
    guest_contact = new_guest()
    staff = client_as(make_committed_user(Role.STAFF))
    booked = staff.post(
        "/api/v1/appointments",
        json={
            "doctorId": str(doctor.id),
            "startsAt": iso(at(monday, 8)),
            "reason": "OTHER",
            "guest": guest_contact,
        },
    ).json()

    response = reschedule(staff, booked["id"], at(monday, 8, 30))

    assert response.status_code == 200
    assert response.json()["guest"] == guest_contact


def test_admins_do_not_reschedule(
    client_as: ClientFactory,
    make_committed_user: UserFactory,
    doctor: User,
    patient: User,
    monday: date,
    db_engine: Engine,
) -> None:
    admin = make_committed_user(Role.ADMIN)
    grant_access(db_engine, admin)
    appointment = book(db_engine, doctor, patient, at(monday, 8))

    response = reschedule(client_as(admin), appointment.id, at(monday, 9))
    assert response.status_code == 403
    assert error_code(response) == "FORBIDDEN"
    assert reschedule(client_as(None), appointment.id, at(monday, 9)).status_code == 401


@pytest.mark.parametrize(
    "body",
    [
        {},
        {"startsAt": "2030-01-07T08:00:00"},
        {"startsAt": "2030-01-07T08:00:00Z", "reason": "OTHER"},
    ],
)
def test_invalid_reschedule_bodies_are_rejected(
    client_as: ClientFactory,
    doctor: User,
    patient: User,
    monday: date,
    db_engine: Engine,
    body: dict[str, Any],
) -> None:
    appointment = book(db_engine, doctor, patient, at(monday, 8))

    response = client_as(patient).post(
        f"/api/v1/appointments/{appointment.id}/reschedule", json=body
    )

    assert response.status_code == 422
