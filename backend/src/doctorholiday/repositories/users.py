"""Users and their credentials; doctors and patients as the schedule and bookings need them."""

import uuid
from collections.abc import Iterable, Sequence

from sqlalchemy import ColumnElement, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from doctorholiday.db import violated_constraint
from doctorholiday.models import Credential, Role, User
from doctorholiday.repositories.errors import EmailAlreadyRegisteredError


def create_user(
    session: Session, *, email: str, display_name: str | None, role: Role, password_hash: str
) -> User:
    """Insert a user with its credentials. `password_hash` must already be an Argon2id hash."""
    user = User(email=email, display_name=display_name, role=role)
    try:
        with session.begin_nested():
            session.add(user)
            session.flush()
            session.add(Credential(user_id=user.id, password_hash=password_hash))
            session.flush()
    except IntegrityError as exc:
        if violated_constraint(exc) == "users_email_key":
            raise EmailAlreadyRegisteredError from None
        raise
    return user


def get_user(session: Session, user_id: uuid.UUID) -> User | None:
    return session.get(User, user_id)


def get_user_by_email(session: Session, email: str) -> User | None:
    # citext column: the comparison is case-insensitive. Deleted users have no e-mail (BR-13).
    return session.scalars(select(User).where(User.email == email)).one_or_none()


def get_credential(session: Session, user_id: uuid.UUID) -> Credential | None:
    """For the auth module only."""
    return session.get(Credential, user_id)


def _active_doctor_clause() -> tuple[ColumnElement[bool], ...]:
    return (User.role == Role.DOCTOR, User.is_active.is_(True), User.deleted_at.is_(None))


def get_active_doctor(session: Session, doctor_id: uuid.UUID, *, lock: bool = False) -> User | None:
    """The user if it is an active, not deleted `DOCTOR` (BR-08, BR-09, BR-12), else None.

    `lock=True` serialises the writes that depend on the doctor's schedule and bookings
    (`FOR NO KEY UPDATE` until the transaction ends): bookings, reschedulings, absences and
    working hours of one doctor then run one after the other, so a check before a write (e.g. "no
    booked appointment in this absence") cannot be invalidated by a concurrent write, and
    conflicting inserts on the exclusion constraints never deadlock (#74). It does not block the
    `FOR KEY SHARE` locks that foreign key checks take on the same row.
    """
    statement = select(User).where(User.id == doctor_id, *_active_doctor_clause())
    if lock:
        statement = statement.with_for_update(key_share=True)
    return session.scalars(statement.execution_options(populate_existing=True)).one_or_none()


def list_active_doctors(session: Session, *, doctor_id: uuid.UUID | None = None) -> Sequence[User]:
    """Active doctors sorted by display name, optionally only one."""
    statement = select(User).where(*_active_doctor_clause())
    if doctor_id is not None:
        statement = statement.where(User.id == doctor_id)
    return session.scalars(statement.order_by(User.display_name, User.id)).all()


def page_active_doctors(session: Session, *, limit: int, offset: int) -> tuple[Sequence[User], int]:
    """A page of active doctors sorted by display name, and their total count."""
    total = session.scalar(select(func.count()).select_from(User).where(*_active_doctor_clause()))
    items = session.scalars(
        select(User)
        .where(*_active_doctor_clause())
        .order_by(User.display_name, User.id)
        .limit(limit)
        .offset(offset)
    ).all()
    return items, total or 0


def get_users(session: Session, user_ids: Iterable[uuid.UUID]) -> dict[uuid.UUID, User]:
    """Users by ID in one query, e.g. the doctors and patients of a page of appointments."""
    ids = set(user_ids)
    if not ids:
        return {}
    return {user.id: user for user in session.scalars(select(User).where(User.id.in_(ids)))}


def get_active_patient_by_email(session: Session, email: str) -> User | None:
    """The active `PATIENT` with this e-mail, for bookings by staff (BR-09); else None."""
    return session.scalars(
        select(User).where(
            User.email == email,
            User.role == Role.PATIENT,
            User.is_active.is_(True),
            User.deleted_at.is_(None),
        )
    ).one_or_none()


def lock_user(session: Session, user_id: uuid.UUID) -> None:
    """Lock the user's row until the transaction ends (`FOR NO KEY UPDATE`), e.g. so concurrent
    bookings of one patient cannot both pass the open-appointment limit (BR-09)."""
    session.execute(select(User.id).where(User.id == user_id).with_for_update(key_share=True))
