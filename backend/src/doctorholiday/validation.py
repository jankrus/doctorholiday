"""Validation layer (#13, SR-03): strict request models, shared field types, query checks.

- Request bodies subclass `RequestModel` (`extra="forbid"` = `additionalProperties: false`).
- String fields use the types below or carry their own `max_length`; `tests/test_validation.py`
  fails for any route whose body, path, query, header or cookie parameters are unbounded.
- `reject_unknown_query_params` is installed on the whole app (`create_app`): a query parameter
  the route does not declare is a `422`, like an unknown body field.
- Size limit and JSON-only bodies are checked earlier, in `RequestBodyMiddleware`.
"""

import logging
from collections.abc import Iterator
from typing import Annotated

from fastapi import Request, status
from fastapi.dependencies.models import Dependant
from fastapi.routing import APIRoute
from pydantic import (
    BaseModel,
    BeforeValidator,
    ConfigDict,
    EmailStr,
    Field,
    SecretStr,
    StringConstraints,
)

from doctorholiday.errors import VALIDATION_MESSAGE, ApiError, ErrorCode

logger = logging.getLogger(__name__)


class RequestModel(BaseModel):
    """Base for every request body: unknown fields are rejected, not ignored."""

    model_config = ConfigDict(extra="forbid")


def _normalise_email(value: object) -> object:
    # Trimmed and lowercased before validation, so case variants and stray spaces from a form
    # map to one account and one rate-limit counter. users.email is citext as well.
    return value.strip().lower() if isinstance(value, str) else value


# Field types as in backend/openapi.yaml.
Email = Annotated[EmailStr, BeforeValidator(_normalise_email), Field(min_length=3, max_length=254)]
# Passwords are SecretStr so they never show up in a repr or traceback, and they are not trimmed
# (BR-01).
NewPassword = Annotated[SecretStr, Field(min_length=12, max_length=128)]
Password = Annotated[SecretStr, Field(min_length=1, max_length=128)]
# Trimmed; no control characters or angle brackets.
DisplayName = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True, min_length=1, max_length=100, pattern=r"^[^\x00-\x1F\x7F<>]+$"
    ),
]


def iter_dependants(dependant: Dependant) -> Iterator[Dependant]:
    """The dependant and all its sub-dependencies, depth first."""
    yield dependant
    for sub in dependant.dependencies:
        yield from iter_dependants(sub)


def declared_query_params(route: APIRoute) -> frozenset[str]:
    names: set[str] = set()
    for dependant in iter_dependants(route.dependant):
        for param in dependant.query_params:
            annotation = param.field_info.annotation
            if isinstance(annotation, type) and issubclass(annotation, BaseModel):
                # A query parameter model (Annotated[Model, Query()]) declares its fields.
                names.update(info.alias or name for name, info in annotation.model_fields.items())
            else:
                names.add(param.alias)
    return frozenset(names)


def reject_unknown_query_params(request: Request) -> None:
    route = request.scope.get("route")
    if not isinstance(route, APIRoute):
        return
    unknown = set(request.query_params) - declared_query_params(route)
    if unknown:
        # Count only: names and values come from the client and may carry personal data.
        logger.info("unknown query parameters", extra={"count": len(unknown)})
        raise ApiError(
            status.HTTP_422_UNPROCESSABLE_CONTENT, ErrorCode.VALIDATION_ERROR, VALIDATION_MESSAGE
        )
