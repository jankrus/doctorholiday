"""Practice data for every logged-in user: active doctors (A27) and the settings (A26)."""

from fastapi import APIRouter

from doctorholiday.api.common import DEFAULT_LIMIT, Limit, Offset, Page
from doctorholiday.api.responses import DoctorRef, PracticeSettings
from doctorholiday.auth.dependencies import ActiveUser
from doctorholiday.db import DbSession
from doctorholiday.repositories import practice_settings, users

router = APIRouter(prefix="/api/v1", tags=["directory"])


@router.get("/doctors", operation_id="listDoctors", response_model=Page[DoctorRef])
def list_doctors(
    _user: ActiveUser, db: DbSession, limit: Limit = DEFAULT_LIMIT, offset: Offset = 0
) -> Page[DoctorRef]:
    # Every role may read this (x-roles: all four); an ACTIVE session is enough.
    doctors, total = users.page_active_doctors(db, limit=limit, offset=offset)
    return Page(limit=limit, offset=offset, total=total, items=[DoctorRef.of(d) for d in doctors])


@router.get("/settings", operation_id="getSettings", response_model=PracticeSettings)
def get_settings(_user: ActiveUser, db: DbSession) -> PracticeSettings:
    return PracticeSettings.of(practice_settings.get_practice_settings(db))
