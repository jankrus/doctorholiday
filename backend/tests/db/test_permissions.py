"""Role x endpoint matrix of the operations built in #17 and #66, generated from `x-roles` and
`x-session-states` in openapi.yaml.

- No session: `401 UNAUTHENTICATED`.
- A session that is not `ACTIVE`: `403 MFA_REQUIRED` (BR-05).
- A role outside `x-roles`: `403 FORBIDDEN`, before the body or the object is looked at.
- A role in `x-roles` passes the role check: whatever the answer (404 for the random IDs, 422 for
  the missing body, 403 ACCESS_GRANT_REQUIRED for ADMIN without a TBAC grant), it is never
  401, FORBIDDEN or MFA_REQUIRED.

Object-level checks ("own only") are tested per endpoint in the other modules and for IDOR in
`test_idor.py`. That every route declares a rule at all is `tests/test_authorization.py` (#16).
"""

import uuid
from typing import Any

import pytest
from fastapi import FastAPI

from doctorholiday.auth.policy import routes
from doctorholiday.models import Role, SessionState
from tests.contract import operations
from tests.db.conftest import ClientFactory, UserFactory

# PUT /api/v1/settings (A20) is tagged `admin` and not part of #17.
TAGS = {"schedule", "appointments", "directory"}
# Operations with an ACTIVE session outside those tags (change password, A23).
EXTRA = {"changePassword"}

OPERATIONS = [
    (method, path, operation)
    for method, path, operation in operations()
    if TAGS & set(operation["tags"]) or operation["operationId"] in EXTRA
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


def test_every_implemented_active_session_operation_is_in_the_matrix(api_app: FastAPI) -> None:
    """Default deny (#16): an endpoint that needs an ACTIVE session cannot skip the matrix.

    A new endpoint with `x-session-states: [ACTIVE]` in the contract that is missing from `TAGS`
    fails here, so it cannot go live without its role x endpoint cases.
    """
    implemented = {
        (m, path) for route in routes(api_app) for m in route.methods or () for path in [route.path]
    }
    active_only = {
        operation["operationId"]
        for method, path, operation in operations()
        if (method.upper(), path) in implemented and operation.get("x-session-states") == ["ACTIVE"]
    }
    built = {operation["operationId"] for _, _, operation in OPERATIONS}

    assert active_only == built
    assert all(operation["x-session-states"] == ["ACTIVE"] for _, _, operation in OPERATIONS)
