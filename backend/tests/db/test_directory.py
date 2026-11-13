"""A26 practice settings and A27 doctors list (#17) against a real database."""

import pytest
from sqlalchemy import Engine

from doctorholiday.models import Role, SessionState
from tests.db.conftest import ClientFactory, UserFactory, practice_settings

ALL_ROLES = list(Role)


@pytest.mark.parametrize("role", ALL_ROLES)
def test_every_role_lists_the_active_doctors_without_their_e_mail(
    client_as: ClientFactory, make_committed_user: UserFactory, role: Role
) -> None:
    doctor = make_committed_user(Role.DOCTOR)
    make_committed_user(Role.STAFF)

    response = client_as(make_committed_user(role)).get("/api/v1/doctors?limit=100")

    assert response.status_code == 200
    body = response.json()
    assert {"id": str(doctor.id), "displayName": doctor.display_name} in body["items"]
    assert all(set(item) == {"id", "displayName"} for item in body["items"])
    assert body["total"] >= 1
    assert body["limit"] == 100


def test_doctors_are_paginated_and_sorted_by_name(
    client_as: ClientFactory, make_committed_user: UserFactory
) -> None:
    make_committed_user(Role.DOCTOR)
    make_committed_user(Role.DOCTOR)
    client = client_as(make_committed_user())

    everyone = client.get("/api/v1/doctors?limit=100").json()
    first, second = (client.get(f"/api/v1/doctors?limit=1&offset={o}").json() for o in (0, 1))

    names = [(item["displayName"], item["id"]) for item in everyone["items"]]
    assert names == sorted(names)
    assert first["items"] == everyone["items"][:1]
    assert second["items"] == everyone["items"][1:2]
    assert first["total"] == everyone["total"]


@pytest.mark.parametrize("query", ["limit=0", "limit=101", "offset=-1", "offset=10001", "x=1"])
def test_invalid_pagination_is_rejected(
    client_as: ClientFactory, make_committed_user: UserFactory, query: str
) -> None:
    response = client_as(make_committed_user()).get(f"/api/v1/doctors?{query}")

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


@pytest.mark.parametrize("role", ALL_ROLES)
def test_every_role_reads_the_settings(
    client_as: ClientFactory, make_committed_user: UserFactory, db_engine: Engine, role: Role
) -> None:
    with practice_settings(db_engine, appointment_minutes=20, cancellation_deadline_hours=12):
        response = client_as(make_committed_user(role)).get("/api/v1/settings")

    assert response.status_code == 200
    body = response.json()
    assert body["appointmentMinutes"] == 20
    assert body["cancellationDeadlineHours"] == 12
    assert body["practiceName"]


@pytest.mark.parametrize("path", ["/api/v1/doctors", "/api/v1/settings"])
def test_a_session_is_required(
    client_as: ClientFactory, make_committed_user: UserFactory, path: str
) -> None:
    assert client_as(None).get(path).status_code == 401
    pending = client_as(make_committed_user(), SessionState.MFA_PENDING).get(path)
    assert pending.status_code == 403
    assert pending.json()["error"]["code"] == "MFA_REQUIRED"
