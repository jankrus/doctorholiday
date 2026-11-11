"""Validation layer (#13): every route validates strictly; enforced here for routes added later."""

import re
from pathlib import Path
from typing import Annotated, Any

import pytest
from fastapi import FastAPI
from fastapi.routing import APIRoute, RouteContext, iter_route_contexts
from pydantic import BaseModel, Field, TypeAdapter, ValidationError

from doctorholiday.api.auth import LoginRequest, RegisterRequest
from doctorholiday.validation import RequestModel, iter_dependants, reject_unknown_query_params

API_SOURCES = Path(__file__).resolve().parents[1] / "src" / "doctorholiday" / "api"

# String formats that bound the value themselves.
_BOUNDED_FORMATS = frozenset({"uuid", "date-time", "date", "time"})


def schema_violations(schema: Any, path: str = "$") -> list[str]:
    """Unbounded parts of a JSON schema: strings without maxLength, arrays without maxItems,
    objects that allow unknown properties."""
    violations: list[str] = []
    if isinstance(schema, dict):
        types = schema.get("type")
        types = types if isinstance(types, list) else [types]
        if (
            "string" in types
            and "maxLength" not in schema
            and "enum" not in schema
            and "const" not in schema
            and schema.get("format") not in _BOUNDED_FORMATS
        ):
            violations.append(f"{path}: string without maxLength")
        if "array" in types and "maxItems" not in schema:
            violations.append(f"{path}: array without maxItems")
        if "object" in types and schema.get("additionalProperties") is not False:
            violations.append(f"{path}: object allows unknown properties")
        for key, value in schema.items():
            violations.extend(schema_violations(value, f"{path}.{key}"))
    elif isinstance(schema, list):
        for index, value in enumerate(schema):
            violations.extend(schema_violations(value, f"{path}[{index}]"))
    return violations


def route_violations(route: RouteContext) -> list[str]:
    dependants = list(iter_dependants(route.dependant))
    violations: list[str] = []
    if reject_unknown_query_params not in {d.call for d in dependants}:
        violations.append("reject_unknown_query_params is not installed")
    for dependant in dependants:
        for param in dependant.body_params:
            model = param.field_info.annotation
            if not (isinstance(model, type) and issubclass(model, RequestModel)):
                violations.append(f"body {param.name}: not a RequestModel")
                continue
            violations.extend(
                f"body {param.name} {v}"
                for v in schema_violations(model.model_json_schema(mode="validation"))
            )
        for kind in ("path_params", "query_params", "header_params", "cookie_params"):
            for param in getattr(dependant, kind):
                adapter = TypeAdapter(Annotated[param.field_info.annotation, param.field_info])
                violations.extend(
                    f"{kind} {param.name} {v}"
                    for v in schema_violations(adapter.json_schema(mode="validation"))
                )
    return violations


def api_routes(app: FastAPI) -> list[RouteContext]:
    # Routes of included routers as they are served, i.e. with the app-level dependencies; plain
    # `app.routes` holds only wrappers for the included routers.
    return [
        ctx for ctx in iter_route_contexts(app.routes) if isinstance(ctx.original_route, APIRoute)
    ]


def test_app_has_routes(app: FastAPI) -> None:
    assert len(api_routes(app)) >= 6


def test_every_route_uses_the_validation_layer(app: FastAPI) -> None:
    violations = {
        f"{sorted(route.methods)} {route.path}": found
        for route in api_routes(app)
        if (found := route_violations(route))
    }

    assert violations == {}


def test_the_check_finds_unvalidated_routes(app: FastAPI) -> None:
    class Loose(BaseModel):  # extra fields ignored, not forbidden
        name: str

    class Unbounded(RequestModel):
        name: str
        tags: list[Annotated[str, Field(max_length=10)]]

    @app.post("/probe-loose")
    def probe_loose(body: Loose) -> None: ...

    @app.post("/probe-unbounded")
    def probe_unbounded(body: Unbounded, search: str = "") -> None: ...

    routes = {route.path: route for route in api_routes(app)}

    assert route_violations(routes["/probe-loose"]) == ["body body: not a RequestModel"]
    found = route_violations(routes["/probe-unbounded"])
    assert "body body $.properties.name: string without maxLength" in found
    assert "body body $.properties.tags: array without maxItems" in found
    assert "query_params search $: string without maxLength" in found


def test_no_endpoint_reads_the_raw_body() -> None:
    raw_access = re.compile(r"\.(json|body|form|stream)\(\)")
    offenders = [
        f"{path.name}:{number}"
        for path in API_SOURCES.glob("*.py")
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1)
        if raw_access.search(line)
    ]

    assert offenders == []


# ---------- Normalisation ----------


def test_email_is_trimmed_and_lowercased() -> None:
    body = LoginRequest.model_validate({"email": "  Patient@Example.COM ", "password": "x"})

    assert body.email == "patient@example.com"


def test_display_name_is_trimmed() -> None:
    body = RegisterRequest.model_validate(
        {"email": "a@example.com", "password": "p" * 12, "displayName": "  Dr. Holiday  "}
    )

    assert body.display_name == "Dr. Holiday"


@pytest.mark.parametrize("display_name", ["   ", "<script>", "a\nb", "x" * 101])
def test_invalid_display_names(display_name: str) -> None:
    with pytest.raises(ValidationError):
        RegisterRequest.model_validate(
            {"email": "a@example.com", "password": "p" * 12, "displayName": display_name}
        )


def test_password_is_not_trimmed() -> None:
    body = LoginRequest.model_validate({"email": "a@example.com", "password": "  secret  "})

    assert body.password.get_secret_value() == "  secret  "
