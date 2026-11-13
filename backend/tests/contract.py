"""Responses checked against the API contract `backend/openapi.yaml` (#17).

`install(client)` validates every response a TestClient receives: the status must be declared for
the operation (or be one of the statuses that apply to every path), the JSON body must match the
declared schema and a declared `Cache-Control: no-store` must be sent.

The check is stricter than the contract itself in two ways, so leaks fail the tests:
- Response objects are closed (`unevaluatedProperties: false`): a field the contract does not
  declare, e.g. guest data in a patient's view, is a violation.
- Timestamps must be UTC with `Z`, as the contract's `Timestamp` description demands.
"""

import copy
import json
import re
from collections.abc import Iterator
from datetime import datetime
from functools import cache
from pathlib import Path
from typing import Any

import yaml
from fastapi.testclient import TestClient
from httpx2 import Response
from jsonschema import Draft202012Validator, FormatChecker
from referencing import Registry, Resource
from referencing.jsonschema import DRAFT202012

OPENAPI = Path(__file__).resolve().parents[1] / "openapi.yaml"
_SPEC_URI = "urn:doctorholiday:openapi"
_METHODS = ("get", "put", "post", "delete", "patch")
# info.description, "Applies to every path": not repeated per operation.
GLOBAL_STATUSES = frozenset({404, 405, 413, 415, 422, 500})


@cache
def spec() -> dict[str, Any]:
    return yaml.safe_load(OPENAPI.read_text(encoding="utf-8"))


def operations() -> Iterator[tuple[str, str, dict[str, Any]]]:
    """(method, path, operation) of every operation in the contract."""
    for path, item in spec()["paths"].items():
        for method in _METHODS:
            if method in item:
                yield method, path, item[method]


def _all_of_members(schemas: dict[str, Any]) -> set[str]:
    refs: set[str] = set()

    def walk(node: Any) -> None:
        if isinstance(node, dict):
            for member in node.get("allOf", []):
                if "$ref" in member:
                    refs.add(member["$ref"].rsplit("/", 1)[-1])
            for value in node.values():
                walk(value)
        elif isinstance(node, list):
            for value in node:
                walk(value)

    walk(schemas)
    return refs


def _close(node: Any, *, exempt: bool = False) -> None:
    """Add `unevaluatedProperties: false` to every object schema. Members of an `allOf` are
    exempt (the allOf itself is closed), because a closed member would reject the properties the
    other members declare."""
    if isinstance(node, list):
        for value in node:
            _close(value)
        return
    if not isinstance(node, dict):
        return
    if "allOf" in node:
        node.setdefault("unevaluatedProperties", False)
        for member in node["allOf"]:
            _close(member, exempt=True)
    elif "properties" in node and "additionalProperties" not in node and not exempt:
        node["unevaluatedProperties"] = False
    for key, value in node.items():
        if key == "properties":
            for prop in value.values():
                _close(prop)
        elif key != "allOf":
            _close(value)


@cache
def _registry() -> Registry:
    document = copy.deepcopy(spec())
    schemas = document["components"]["schemas"]
    exempt = _all_of_members(schemas)
    for name, schema in schemas.items():
        _close(schema, exempt=name in exempt)
    return Registry().with_resource(_SPEC_URI, Resource(document, specification=DRAFT202012))


_FORMATS = FormatChecker()


@_FORMATS.checks("date-time", raises=ValueError)
def _utc_timestamp(value: object) -> bool:
    if not isinstance(value, str):
        return True
    if not value.endswith("Z"):
        return False
    datetime.fromisoformat(value)
    return True


def _validator(ref: str) -> Draft202012Validator:
    return Draft202012Validator(
        {"$ref": f"{_SPEC_URI}{ref}"}, registry=_registry(), format_checker=_FORMATS
    )


def _path_regex(path: str) -> re.Pattern[str]:
    segments = ("[^/]+" if part.startswith("{") else re.escape(part) for part in path.split("/"))
    return re.compile("^" + "/".join(segments) + "$")


@cache
def _path_patterns() -> list[tuple[re.Pattern[str], str]]:
    # Literal paths first, so /appointments/me never matches a template.
    paths = sorted(spec()["paths"], key=lambda path: path.count("{"))
    return [(_path_regex(path), path) for path in paths]


def find_path(url_path: str) -> str | None:
    for pattern, path in _path_patterns():
        if pattern.match(url_path):
            return path
    return None


def _resolve(node: dict[str, Any]) -> dict[str, Any]:
    while "$ref" in node:
        target: Any = spec()
        for part in node["$ref"].removeprefix("#/").split("/"):
            target = target[part]
        node = target
    return node


def violations(response: Response) -> list[str]:
    """Where `response` breaks the contract; empty if it conforms."""
    request = response.request
    path = find_path(request.url.path)
    method = request.method.lower()
    status = response.status_code
    error_schema = "#/components/schemas/Error"

    operation = spec()["paths"][path].get(method) if path else None
    if operation is None or str(status) not in operation["responses"]:
        if status not in GLOBAL_STATUSES:
            where = f"{method.upper()} {path or request.url.path}"
            return [f"{where}: status {status} is not declared"]
        declared: dict[str, Any] = {
            "content": {"application/json": {"schema": {"$ref": error_schema}}}
        }
    else:
        declared = _resolve(operation["responses"][str(status)])

    found: list[str] = []
    content = declared.get("content", {}).get("application/json")
    if content is None:
        if response.content:
            found.append(f"{status}: body sent, none declared")
    else:
        try:
            body = response.json()
        except json.JSONDecodeError:
            return [f"{status}: body is not JSON"]
        schema = content["schema"]
        ref = schema["$ref"].removeprefix("#") if "$ref" in schema else None
        if ref is None:
            return [f"{status}: inline response schemas are not supported by this check"]
        found.extend(
            f"{status} {'/'.join(map(str, error.absolute_path))}: {error.message}"
            for error in _validator("#" + ref).iter_errors(body)
        )
    for name, header in declared.get("headers", {}).items():
        if header.get("$ref", "").endswith("/NoStore") and response.headers.get(name) != "no-store":
            found.append(f"{status}: header {name} is not no-store")
    return found


# Routes that tests add to the app themselves, e.g. /test/active-user; not part of the contract.
TEST_ONLY_PREFIX = "/test/"


def check(response: Response) -> None:
    response.read()
    if response.request.url.path.startswith(TEST_ONLY_PREFIX):
        return
    found = violations(response)
    assert not found, f"{response.request.method} {response.request.url.path}: {found}"


def install(client: TestClient) -> TestClient:
    """Validate every response of `client` against the contract."""
    client.event_hooks = {
        **client.event_hooks,
        "response": [*client.event_hooks["response"], check],
    }
    return client
