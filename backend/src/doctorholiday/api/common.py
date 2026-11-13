"""Helpers shared by the API routers: client IP, pagination and the response field types."""

from datetime import UTC, datetime
from ipaddress import ip_address
from typing import Annotated

from fastapi import Query, Request
from pydantic import BaseModel, ConfigDict, PlainSerializer
from pydantic.alias_generators import to_camel

from doctorholiday.models import IPAddress
from doctorholiday.validation import RequestModel

NO_STORE = {"Cache-Control": "no-store"}


def client_ip(request: Request) -> IPAddress | None:
    # The direct peer; behind ingress-nginx that is the proxy until forwarded headers are handled
    # (#75).
    if request.client is None:
        return None
    try:
        return ip_address(request.client.host)
    except ValueError:
        return None


# Pagination of every list (BR-20, `Limit` and `Offset` in openapi.yaml).
Limit = Annotated[int, Query(ge=1, le=100)]
Offset = Annotated[int, Query(ge=0, le=10_000)]
DEFAULT_LIMIT = 20


def utc_iso(value: datetime) -> str:
    # The contract's Timestamp: the server returns UTC with `Z`, whatever the session time zone
    # of the database connection is.
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


UtcDatetime = Annotated[datetime, PlainSerializer(utc_iso, return_type=str)]


class CamelRequest(RequestModel):
    """Request body with the contract's camelCase field names (`doctorId`, `startsAt`, ...)."""

    model_config = ConfigDict(alias_generator=to_camel)


class ResponseModel(BaseModel):
    """Response body with camelCase field names; built by field name in the code."""

    model_config = ConfigDict(alias_generator=to_camel, validate_by_name=True)


class Page[T](ResponseModel):
    """`PageMeta` plus `items` (BR-20)."""

    limit: int
    offset: int
    total: int
    items: list[T]
