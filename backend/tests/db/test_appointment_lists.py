"""Own appointments (A11) and all appointments (A12), paginated and filtered (BR-20), #17."""

from datetime import date, time, timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, func, update
from sqlalchemy.orm import Session

from doctorholiday.models import AccessPurpose, AdminAccessGrant, AuditAction, Role, User
from tests.db.conftest import ClientFactory, UserFactory
from tests.db.helpers import at, audit_events, book, iso, new_guest, next_monday, set_hours


@pytest.fixture
def monday(db_engine: Engine) -> date:
    return next_monday(db_engine)


@pytest.fixture
def doctor(make_committed_user: UserFactory, db_engine: Engine) -> User:
    doctor = make_committed_user(Role.DOCTOR)
    set_hours(db_engine, doctor, (1, time(8), time(12)))
    return doctor


def ids(response: Any) -> list[str]:
    assert response.status_code == 200, response.json()
    return [item["id"] for item in response.json()["items"]]


def grant_access(engine: Engine, admin: User, *, minutes_ago: int = 0) -> AdminAccessGrant:
    with Session(engine, expire_on_commit=False) as session, session.begin():
        created = func.now() - timedelta(minutes=minutes_ago)
        grant = AdminAccessGrant(
            admin_id=admin.id,
            purpose=AccessPurpose.AUDIT,
            created_at=created,
            expires_at=created + timedelta(minutes=30),
        )
        session.add(grant)
    return grant


# ---------- Own appointments ----------


def test_a_patient_lists_only_their_own_appointments_without_patient_data(
    client_as: ClientFactory,
    make_committed_user: UserFactory,
    doctor: User,
    monday: date,
    db_engine: Engine,
) -> None:
    patient, other = make_committed_user(), make_committed_user()
    later = book(db_engine, doctor, patient, at(monday, 11))
    sooner = book(db_engine, doctor, patient, at(monday, 8))
    book(db_engine, doctor, other, at(monday, 9))

    response = client_as(patient).get("/api/v1/appointments/me")

    assert ids(response) == [str(sooner.id), str(later.id)]
    assert response.json()["total"] == 2
    assert response.headers["Cache-Control"] == "no-store"
    for item in response.json()["items"]:
        assert "patient" not in item
        assert "guest" not in item


def test_own_appointments_are_filtered_and_paginated(
    client_as: ClientFactory,
    make_committed_user: UserFactory,
    doctor: User,
    monday: date,
    db_engine: Engine,
) -> None:
    patient = make_committed_user()
    rows = [book(db_engine, doctor, patient, at(monday, 8, 15 * i)) for i in range(4)]
    client = client_as(patient)
    assert client.post(f"/api/v1/appointments/{rows[1].id}/cancel").status_code == 200

    def listed(**params: Any) -> list[str]:
        return ids(client.get("/api/v1/appointments/me", params=params))

    assert listed(status="CANCELLED") == [str(rows[1].id)]
    assert listed(status="BOOKED") == [str(r.id) for r in (rows[0], rows[2], rows[3])]
    window = {"from": iso(at(monday, 8, 15)), "to": iso(at(monday, 8, 45))}
    assert listed(**window) == [str(rows[1].id), str(rows[2].id)]
    page = client.get("/api/v1/appointments/me", params={"limit": 2, "offset": 1}).json()
    assert [item["id"] for item in page["items"]] == [str(rows[1].id), str(rows[2].id)]
    assert (page["limit"], page["offset"], page["total"]) == (2, 1, 4)


@pytest.mark.parametrize(
    "query",
    ["patientId=00000000-0000-0000-0000-000000000000", "doctorId=x", "limit=101", "status=GONE"],
)
def test_own_list_rejects_other_parameters(
    client_as: ClientFactory, make_committed_user: UserFactory, query: str
) -> None:
    response = client_as(make_committed_user()).get(f"/api/v1/appointments/me?{query}")

    assert response.status_code == 422


@pytest.mark.parametrize("role", [Role.STAFF, Role.DOCTOR, Role.ADMIN])
def test_only_patients_have_an_own_list(
    client_as: ClientFactory, make_committed_user: UserFactory, role: Role
) -> None:
    response = client_as(make_committed_user(role)).get("/api/v1/appointments/me")

    assert response.status_code == 403
    assert client_as(None).get("/api/v1/appointments/me").status_code == 401


# ---------- All appointments ----------


@pytest.mark.parametrize("role", [Role.STAFF, Role.DOCTOR])
def test_the_practice_lists_all_appointments_with_patient_and_guest(
    client_as: ClientFactory,
    make_committed_user: UserFactory,
    doctor: User,
    monday: date,
    db_engine: Engine,
    role: Role,
) -> None:
    patient = make_committed_user()
    staff = client_as(make_committed_user(Role.STAFF))
    own = book(db_engine, doctor, patient, at(monday, 8))
    guest = new_guest()
    guest_booking = staff.post(
        "/api/v1/appointments",
        json={
            "doctorId": str(doctor.id),
            "startsAt": iso(at(monday, 9)),
            "reason": "OTHER",
            "guest": guest,
        },
    ).json()

    response = client_as(make_committed_user(role)).get(
        "/api/v1/appointments", params={"doctorId": str(doctor.id)}
    )

    assert ids(response) == [str(own.id), guest_booking["id"]]
    first, second = response.json()["items"]
    assert first["patient"]["id"] == str(patient.id)
    assert first["patient"]["email"] == patient.email
    assert "guest" not in first
    assert second["guest"] == guest
    assert "patient" not in second


def test_all_appointments_are_filtered_and_paginated(
    client_as: ClientFactory,
    make_committed_user: UserFactory,
    doctor: User,
    monday: date,
    db_engine: Engine,
) -> None:
    patient = make_committed_user()
    other_doctor = make_committed_user(Role.DOCTOR)
    rows = [book(db_engine, doctor, patient, at(monday, 8, 15 * i)) for i in range(3)]
    book(db_engine, other_doctor, patient, at(monday, 8))
    client = client_as(make_committed_user(Role.STAFF))
    assert client.post(f"/api/v1/appointments/{rows[0].id}/cancel").status_code == 200

    def listed(**params: Any) -> list[str]:
        return ids(
            client.get("/api/v1/appointments", params={"doctorId": str(doctor.id), **params})
        )

    assert listed() == [str(r.id) for r in rows]
    assert listed(status="CANCELLED") == [str(rows[0].id)]
    assert listed(**{"from": iso(at(monday, 8, 15))}) == [str(rows[1].id), str(rows[2].id)]
    assert listed(to=iso(at(monday, 8, 15))) == [str(rows[0].id)]
    assert listed(limit=1, offset=2) == [str(rows[2].id)]
    assert client.get("/api/v1/appointments", params={"limit": 101}).status_code == 422


def test_a_deleted_patient_appears_without_e_mail_and_name(
    client_as: ClientFactory,
    make_committed_user: UserFactory,
    doctor: User,
    monday: date,
    db_engine: Engine,
) -> None:
    patient = make_committed_user()
    book(db_engine, doctor, patient, at(monday, 8))
    with Session(db_engine) as session, session.begin():
        session.execute(
            update(User)
            .where(User.id == patient.id)
            .values(email=None, display_name=None, is_active=False, deleted_at=func.now())
        )

    response = client_as(make_committed_user(Role.STAFF)).get(
        "/api/v1/appointments", params={"doctorId": str(doctor.id)}
    )

    assert response.json()["items"][0]["patient"] == {"id": str(patient.id), "deleted": True}


def test_patients_cannot_list_all_appointments(
    client_as: ClientFactory, make_committed_user: UserFactory
) -> None:
    response = client_as(make_committed_user()).get("/api/v1/appointments")

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "FORBIDDEN"
    assert client_as(None).get("/api/v1/appointments").status_code == 401


def test_an_admin_lists_only_with_an_active_grant_and_each_access_is_audited(
    client_as: ClientFactory,
    make_committed_user: UserFactory,
    doctor: User,
    monday: date,
    db_engine: Engine,
) -> None:
    admin = make_committed_user(Role.ADMIN)
    book(db_engine, doctor, make_committed_user(), at(monday, 8))
    client: TestClient = client_as(admin)
    path = f"/api/v1/appointments?doctorId={doctor.id}"

    def denied() -> None:
        response = client.get(path)
        assert response.status_code == 403
        assert response.json()["error"]["code"] == "ACCESS_GRANT_REQUIRED"

    denied()  # no grant
    grant_access(db_engine, admin, minutes_ago=31)
    denied()  # expired a minute ago

    grant = grant_access(db_engine, admin)
    assert len(ids(client.get(path))) == 1
    assert len(ids(client.get(path))) == 1
    events = audit_events(
        db_engine, AuditAction.APPOINTMENT_DATA_ACCESSED, f"admin_access_grant:{grant.id}"
    )
    assert len(events) == 2
    assert all(event.actor_id == admin.id for event in events)
