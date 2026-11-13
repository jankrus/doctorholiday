"""Role x endpoint matrix of the operations built in #17, generated from `x-roles` and
`x-session-states` in openapi.yaml.

- No session: `401 UNAUTHENTICATED`.
- A session that is not `ACTIVE`: `403 MFA_REQUIRED` (BR-05).
- A role outside `x-roles`: `403 FORBIDDEN`, before the body or the object is looked at.
- A role in `x-roles` passes the role check: whatever the answer (404 for the random IDs, 422 for
  the missing body, 403 ACCESS_GRANT_REQUIRED for ADMIN without a TBAC grant), it is never
  401, FORBIDDEN or MFA_REQUIRED.

Object-level checks ("own only") are tested per endpoint in the other modules. The central,
default-deny matrix over every route is #16.
"""

import uuid
from typing import Any

import pytest

from doctorholiday.models import Role, SessionState
from tests.contract import operations
from tests.db.conftest import ClientFactory, UserFactory

# PUT /api/v1/settings (A20) is tagged `admin` and not part of #17.
TAGS = {"schedule", "appointments", "directory"}

OPERATIONS = [
    (method, path, operation)
    for method, path, operation in operations()
    if TAGS & set(operation["tags"])
]
CASES = [
    pytest.param(
        method,
        path,
        role,
        role.value in operation["x-roles"],
        id=f"{operation['operationId']}-{role}",
    )
    for method, path, operation in OPERATIONS
    for role in Role
]


def _url(path: str) -> str:
    # A random ID for every path parameter; unknown objects answer 404 after the role check.
    url = path.replace("{id}", str(uuid.uuid4()))
    if path == "/api/v1/availability":
        url += "?from=2030-01-07T00:00:00Z&to=2030-01-08T00:00:00Z"
    return url


def _call(client: Any, method: str, path: str) -> Any:
    # No body: the role check runs before the body is validated.
    return client.request(method.upper(), _url(path))


@pytest.mark.parametrize(("method", "path", "role", "allowed"), CASES)
def test_the_role_matrix(
    client_as: ClientFactory,
    make_committed_user: UserFactory,
    method: str,
    path: str,
    role: Role,
    allowed: bool,
) -> None:
    response = _call(client_as(make_committed_user(role)), method, path)

    code = response.json()["error"]["code"] if response.status_code >= 400 else None
    if allowed:
        assert response.status_code != 401
        assert code not in {"FORBIDDEN", "MFA_REQUIRED"}, response.json()
    else:
        assert response.status_code == 403
        assert code == "FORBIDDEN"


@pytest.mark.parametrize(
    ("method", "path"), [pytest.param(m, p, id=o["operationId"]) for m, p, o in OPERATIONS]
)
def test_no_session_is_401_and_an_unfinished_login_is_mfa_required(
    client_as: ClientFactory, make_committed_user: UserFactory, method: str, path: str
) -> None:
    anonymous = _call(client_as(None), method, path)
    assert anonymous.status_code == 401
    assert anonymous.json()["error"]["code"] == "UNAUTHENTICATED"

    for state in (SessionState.MFA_PENDING, SessionState.MFA_ENROLLMENT_REQUIRED):
        pending = _call(client_as(make_committed_user(Role.STAFF), state), method, path)
        assert pending.status_code == 403
        assert pending.json()["error"]["code"] == "MFA_REQUIRED"


def test_every_operation_is_in_the_matrix() -> None:
    built = {operation["operationId"] for _, _, operation in OPERATIONS}

    assert len(built) == 12
    assert all(operation["x-session-states"] == ["ACTIVE"] for _, _, operation in OPERATIONS)
