"""Users and their credentials."""

import uuid

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from doctorholiday.db import violated_constraint
from doctorholiday.models import Credential, Role, User
from doctorholiday.repositories.errors import EmailAlreadyRegisteredError


def create_user(
    session: Session, *, email: str, display_name: str, role: Role, password_hash: str
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
