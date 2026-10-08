"""Kubernetes probes (FR-29, FR-30, BR-21): no auth, status word only, no error details."""

from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Response, status
from pydantic import BaseModel
from sqlalchemy import Engine

from doctorholiday.db import check_database, get_engine

router = APIRouter(tags=["health"])


class Liveness(BaseModel):
    status: Literal["ok"] = "ok"


class Readiness(BaseModel):
    status: Literal["ready", "not_ready"]


@router.get("/healthz", operation_id="liveness")
def liveness() -> Liveness:
    return Liveness()


@router.get(
    "/readyz",
    operation_id="readiness",
    responses={status.HTTP_503_SERVICE_UNAVAILABLE: {"model": Readiness}},
)
def readiness(response: Response, engine: Annotated[Engine, Depends(get_engine)]) -> Readiness:
    if check_database(engine):
        return Readiness(status="ready")
    response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return Readiness(status="not_ready")
