"""IDOR (#16): patient A cannot read, cancel or modify patient B's appointment.

A foreign appointment looks exactly like one that does not exist (`404 NOT_FOUND`), so IDs cannot
be probed. The same checks per endpoint, with their other rules, live in
`test_cancel_reschedule.py` and `test_appointment_lists.py`.
"""

import uuid
from datetime import date, time

import pytest
from sqlalchemy import Engine

from doctorholiday.models import Role, User
from tests.db.conftest import ClientFactory, UserFactory
from tests.db.helpers import at, book, get_appointment, iso, next_monday, set_hours


@pytest.fixture
def monday(db_engine: Engine) -> date:
    return next_monday(db_engine)


@pytest.fixture
def doctor(make_committed_user: UserFactory, db_engine: Engine) -> User:
    doctor = make_committed_user(Role.DOCTOR)
    set_hours(db_engine, doctor, (1, time(8), time(12)))
    return doctor


def test_patient_a_cannot_read_cancel_or_modify_the_appointment_of_patient_b(
    client_as: ClientFactory,
    make_committed_user: UserFactory,
    doctor: User,
    monday: date,
    db_engine: Engine,
) -> None:
    patient_a, patient_b = make_committed_user(), make_committed_user()
    starts_at = at(monday, 8)
    appointment_b = book(db_engine, doctor, patient_b, starts_at)
    client_a = client_as(patient_a)

    # Read: neither the list of own appointments nor any other patient route shows it.
    listed = client_a.get("/api/v1/appointments/me")
    assert listed.status_code == 200
    assert str(appointment_b.id) not in [item["id"] for item in listed.json()["items"]]
    assert client_as(patient_a).get("/api/v1/appointments").status_code == 403

    # Cancel and modify: identical to an unknown ID, and nothing changed.
    unknown = uuid.uuid4()
    for path in ("cancel", "reschedule"):
        body = {"startsAt": iso(at(monday, 9))} if path == "reschedule" else None
        foreign = client_a.post(f"/api/v1/appointments/{appointment_b.id}/{path}", json=body)
        missing = client_a.post(f"/api/v1/appointments/{unknown}/{path}", json=body)
        assert foreign.status_code == 404
        assert foreign.json()["error"]["code"] == missing.json()["error"]["code"] == "NOT_FOUND"
        assert foreign.json()["error"]["message"] == missing.json()["error"]["message"]

    unchanged = get_appointment(db_engine, appointment_b.id)
    assert unchanged.status == "BOOKED"
    assert unchanged.starts_at == starts_at
