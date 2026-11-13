"""The single practice settings row (id = 1, created by migration V003; BR-18)."""

from sqlalchemy.orm import Session

from doctorholiday.models import PracticeSettings


def get_practice_settings(session: Session) -> PracticeSettings:
    return session.get_one(PracticeSettings, 1)
