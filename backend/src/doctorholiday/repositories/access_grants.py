"""Time-limited admin access to appointment data (TBAC, BR-17).

Creating grants (A19) is #55; the appointment endpoints only check for an active one.
"""

import uuid

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from doctorholiday.models import AdminAccessGrant


def active_grant(session: Session, admin_id: uuid.UUID) -> AdminAccessGrant | None:
    """The admin's grant that is active now (database clock), if any; at most one exists
    (`admin_access_grants_no_overlap`)."""
    return session.scalars(
        select(AdminAccessGrant).where(
            AdminAccessGrant.admin_id == admin_id,
            AdminAccessGrant.created_at <= func.now(),
            AdminAccessGrant.expires_at > func.now(),
        )
    ).one_or_none()
