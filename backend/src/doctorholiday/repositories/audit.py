"""Security audit log (BR-19). Append-only: the database role cannot update or delete events."""

import uuid
from typing import Any

from sqlalchemy.orm import Session

from doctorholiday.models import AuditAction, AuditEvent, AuditOutcome, IPAddress


def audit_target(kind: str, object_id: uuid.UUID) -> str:
    """Audit target in the form `<type>:<uuid>`, e.g. `appointment:…`; never personal data."""
    return f"{kind}:{object_id}"


def record_event(
    session: Session,
    *,
    action: AuditAction,
    outcome: AuditOutcome,
    actor_id: uuid.UUID | None = None,
    target: str | None = None,
    ip: IPAddress | None = None,
    details: dict[str, Any] | None = None,
) -> AuditEvent:
    """Append an event to the request transaction.

    `details` takes allow-listed keys only (e.g. oldStartsAt/newStartsAt, BR-22); never copy
    request bodies or personal data into it.
    """
    event = AuditEvent(
        action=action,
        outcome=outcome,
        actor_id=actor_id,
        target=target,
        ip=ip,
        details=details,
    )
    session.add(event)
    session.flush()
    return event
