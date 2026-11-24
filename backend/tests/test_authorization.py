"""Default deny and the role rule of every route (#16).

- The app refuses to start if a route has no authorization rule.
- Every route of the app is in `openapi.yaml` and lets through exactly the roles of `x-roles`;
  the contract is the machine-readable copy of the permission matrix
  (docs/architecture/roles-and-permissions.md).
- The behaviour per role (role x endpoint) is tested in `tests/db/test_permissions.py`.
"""

import pytest
from fastapi import APIRouter, Depends, FastAPI

from doctorholiday.auth.dependencies import (
    public,
    reject_session,
    require_roles,
)
from doctorholiday.auth.policy import enforce_default_deny, route_roles, routes, routes_without_rule
from doctorholiday.models import Role
from tests.contract import operations

ALL = {role.value for role in Role}


def _app_with(*dependencies: object) -> FastAPI:
    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
    router = APIRouter()

    @router.get("/thing", dependencies=list(dependencies))  # type: ignore[arg-type]
    def thing() -> dict[str, str]:
        return {}

    app.include_router(router)
    return app


def test_a_route_without_an_authorization_rule_stops_the_app() -> None:
    app = _app_with()

    assert routes_without_rule(app) == ["GET /thing"]
    with pytest.raises(RuntimeError, match="GET /thing"):
        enforce_default_deny(app)


def test_an_unrelated_dependency_is_not_a_rule() -> None:
    app = _app_with(Depends(lambda: None))

    with pytest.raises(RuntimeError):
        enforce_default_deny(app)


@pytest.mark.parametrize(
    "dependency",
    [
        Depends(require_roles(Role.ADMIN)),
        Depends(public),
        Depends(reject_session),
    ],
)
def test_a_route_with_an_explicit_rule_starts(dependency: object) -> None:
    enforce_default_deny(_app_with(dependency))


def test_the_rules_of_a_route_add_up_to_their_intersection() -> None:
    # ActiveUser lets every role through, require_roles narrows it down.
    app = _app_with(
        Depends(require_roles(Role.STAFF, Role.ADMIN)), Depends(require_roles(Role.ADMIN))
    )
    route = next(routes(app))

    assert route_roles(route) == {"ADMIN"}


def test_the_real_app_has_a_rule_on_every_route(app: FastAPI) -> None:
    assert routes_without_rule(app) == []


def test_every_route_of_the_app_matches_the_permission_matrix(app: FastAPI) -> None:
    contract = {
        (method.upper(), path): frozenset(operation["x-roles"])
        for method, path, operation in operations()
    }
    implemented = {
        (method, route.path): route_roles(route)
        for route in routes(app)
        for method in route.methods or ()
    }

    assert implemented, "no routes found"
    for key, roles in implemented.items():
        assert key in contract, f"{key} is not in openapi.yaml"
        assert roles == contract[key], (
            f"{key}: code {sorted(roles or [])}, contract {sorted(contract[key])}"
        )


def test_the_helpers_carry_their_roles() -> None:
    from doctorholiday.auth.dependencies import AUTHZ_ATTRIBUTE, _require_active_user

    assert getattr(_require_active_user, AUTHZ_ATTRIBUTE) == ALL
    assert getattr(reject_session, AUTHZ_ATTRIBUTE) == {"ANONYMOUS"}
