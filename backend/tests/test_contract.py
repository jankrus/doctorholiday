"""The app serves the operations of backend/openapi.yaml as specified (#17).

Responses are checked in the database tests by `tests.contract.install`; this module checks the
routes, request bodies and query parameters statically, and the response check itself.
"""

from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.routing import APIRoute, iter_route_contexts
from httpx2 import Request, Response
from pydantic import BaseModel

from tests import contract
from tests.contract import operations, spec, violations

_API_PREFIXES = ("/api/", "/healthz", "/readyz")


def _routes(app: FastAPI) -> list[APIRoute]:
    # As served: plain `app.routes` holds only wrappers for the included routers.
    routes = [
        ctx.original_route
        for ctx in iter_route_contexts(app.routes)
        if isinstance(ctx.original_route, APIRoute)
        and ctx.original_route.path.startswith(_API_PREFIXES)
    ]
    assert routes, "no routes found; the checks below would pass vacuously"
    return routes


def _resolve(node: dict[str, Any]) -> dict[str, Any]:
    while "$ref" in node:
        target: Any = spec()
        for part in node["$ref"].removeprefix("#/").split("/"):
            target = target[part]
        node = target
    return node


def _spec_operation(route: APIRoute, method: str) -> dict[str, Any] | None:
    return spec()["paths"].get(route.path, {}).get(method.lower())


def test_every_route_is_an_operation_of_the_contract(app: FastAPI) -> None:
    mismatches = [
        f"{method} {route.path}: {route.operation_id!r}"
        for route in _routes(app)
        for method in route.methods
        if (operation := _spec_operation(route, method)) is None
        or operation["operationId"] != route.operation_id
    ]

    assert mismatches == []


def _body_model(route: APIRoute) -> type[BaseModel] | None:
    params = route.dependant.body_params
    if not params:
        return None
    model = params[0].field_info.annotation
    assert isinstance(model, type)
    assert issubclass(model, BaseModel)
    return model


def test_request_bodies_match_the_contract(app: FastAPI) -> None:
    mismatches: dict[str, Any] = {}
    for route in _routes(app):
        method = next(iter(route.methods))
        operation = _spec_operation(route, method)
        assert operation is not None
        model = _body_model(route)
        declared = operation.get("requestBody")
        if model is None or declared is None:
            assert model is None, f"{method} {route.path}: body not in the contract"
            assert declared is None, f"{method} {route.path}: body not read"
            continue
        schema = _resolve(declared["content"]["application/json"]["schema"])
        if "oneOf" in schema:
            continue  # no such route yet; checked when one is built
        ours = model.model_json_schema(mode="validation", by_alias=True)
        if set(ours["properties"]) != set(schema["properties"]) or set(
            ours.get("required", [])
        ) != set(schema.get("required", [])):
            mismatches[f"{method} {route.path}"] = {
                "properties": sorted(ours["properties"]),
                "required": sorted(ours.get("required", [])),
            }

    assert mismatches == {}


def test_query_parameters_match_the_contract(app: FastAPI) -> None:
    mismatches: dict[str, Any] = {}
    for route in _routes(app):
        method = next(iter(route.methods))
        operation = _spec_operation(route, method)
        assert operation is not None
        declared = {
            param["name"]: param.get("required", False)
            for param in map(_resolve, operation.get("parameters", []))
            if param["in"] == "query"
        }
        ours = {
            param.alias: param.field_info.is_required() for param in route.dependant.query_params
        }
        if ours != declared:
            mismatches[f"{method} {route.path}"] = {"ours": ours, "contract": declared}

    assert mismatches == {}


def test_the_schedule_appointment_and_directory_operations_are_served(app: FastAPI) -> None:
    served = {route.operation_id for route in _routes(app)}
    tagged = {
        operation["operationId"]
        for _, _, operation in operations()
        if {"schedule", "appointments", "directory"} & set(operation["tags"])
    }

    assert tagged
    assert tagged <= served


# ---------- The response check ----------


def _response(status: int, body: object, path: str = "/api/v1/doctors", **headers: str) -> Response:
    return Response(status, json=body, headers=headers, request=Request("GET", f"https://t{path}"))


_DOCTOR = {"id": "3f2c9a4e-8b1d-4c6a-9e2f-7a5b0c1d2e3f", "displayName": "Dr. Who"}


def test_a_conforming_response_passes() -> None:
    page = {"limit": 20, "offset": 0, "total": 1, "items": [_DOCTOR]}

    assert violations(_response(200, page)) == []


def test_undeclared_fields_are_violations() -> None:
    page = {"limit": 20, "offset": 0, "total": 1, "items": [{**_DOCTOR, "email": "x@y.de"}]}

    assert violations(_response(200, page))
    assert violations(_response(200, {**page, "items": [_DOCTOR], "extra": 1}))


def test_timestamps_must_be_utc() -> None:
    settings = {
        "practiceName": "P",
        "cancellationDeadlineHours": 24,
        "appointmentMinutes": 15,
        "updatedAt": "2030-01-07T10:00:00+01:00",
    }

    assert violations(_response(200, settings, "/api/v1/settings"))
    settings["updatedAt"] = "2030-01-07T09:00:00Z"
    assert violations(_response(200, settings, "/api/v1/settings")) == []


def test_undeclared_statuses_are_violations() -> None:
    error = {"error": {"code": "CONFLICT", "message": "m", "requestId": _DOCTOR["id"]}}

    assert violations(_response(409, error))
    assert violations(_response(404, error)) == []  # applies to every path


def test_missing_no_store_is_a_violation() -> None:
    schedule = {"doctor": _DOCTOR, "workingHours": [], "absences": []}
    path = f"/api/v1/doctors/{_DOCTOR['id']}/schedule"

    assert violations(_response(200, schedule, path))
    assert violations(_response(200, schedule, path, **{"Cache-Control": "no-store"})) == []


@pytest.mark.parametrize(
    ("url_path", "expected"),
    [
        ("/api/v1/appointments/me", "/api/v1/appointments/me"),
        ("/api/v1/appointments/abc/cancel", "/api/v1/appointments/{id}/cancel"),
        ("/api/v1/nope", None),
    ],
)
def test_paths_are_matched_literal_first(url_path: str, expected: str | None) -> None:
    assert contract.find_path(url_path) == expected
