"""ORM models of the PostgreSQL schema (docs/architecture/database.md).

The SQL migrations in `backend/migrations` are the source of truth: they create the tables, and
every check, exclusion and unique constraint lives there. These classes only mirror the columns
so queries are built by SQLAlchemy with bound parameters (AGENTS.md rule 4). They are never used
to create or alter tables; tests/db/test_schema.py fails if they drift from the migrated schema.

Columns with a database default are marked `FetchedValue()`: the insert leaves them out and
SQLAlchemy reads the value back with RETURNING, so the default exists in exactly one place.

There are no ORM relationships on purpose: every read is an explicit query, nothing loads
lazily, and no path leads from a `User` to its `Credential` (requirements.md, Credential).
"""

import enum
import uuid
from datetime import datetime, time
from ipaddress import IPv4Address, IPv6Address
from typing import Any

from sqlalchemy import (
    DateTime,
    Enum,
    FetchedValue,
    ForeignKey,
    LargeBinary,
    SmallInteger,
    Text,
    Time,
)
from sqlalchemy.dialects.postgresql import CITEXT, INET, JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

# Values match the CHECK constraints in V002 and the enums in backend/openapi.yaml one to one.


class Role(enum.StrEnum):
    PATIENT = "PATIENT"
    STAFF = "STAFF"
    DOCTOR = "DOCTOR"
    ADMIN = "ADMIN"


class SessionState(enum.StrEnum):
    MFA_PENDING = "MFA_PENDING"
    MFA_ENROLLMENT_REQUIRED = "MFA_ENROLLMENT_REQUIRED"
    ACTIVE = "ACTIVE"


class AppointmentStatus(enum.StrEnum):
    BOOKED = "BOOKED"
    CANCELLED = "CANCELLED"


class AppointmentReason(enum.StrEnum):
    CHECKUP = "CHECKUP"
    FOLLOW_UP = "FOLLOW_UP"
    VACCINATION = "VACCINATION"
    PRESCRIPTION = "PRESCRIPTION"
    CONSULTATION = "CONSULTATION"
    BLOOD_TEST = "BLOOD_TEST"
    BLOOD_TEST_FASTING = "BLOOD_TEST_FASTING"
    OTHER = "OTHER"


class AccessPurpose(enum.StrEnum):
    SUPPORT_REQUEST = "SUPPORT_REQUEST"
    INCIDENT_RESPONSE = "INCIDENT_RESPONSE"
    DATA_SUBJECT_REQUEST = "DATA_SUBJECT_REQUEST"
    AUDIT = "AUDIT"


class AuditAction(enum.StrEnum):
    USER_REGISTERED = "USER_REGISTERED"
    INVITATION_CREATED = "INVITATION_CREATED"
    INVITATION_ACCEPTED = "INVITATION_ACCEPTED"
    LOGIN = "LOGIN"
    LOGOUT = "LOGOUT"
    MFA_ENROLLED = "MFA_ENROLLED"
    MFA_VERIFIED = "MFA_VERIFIED"
    MFA_RECOVERY_CODE_USED = "MFA_RECOVERY_CODE_USED"
    MFA_RESET = "MFA_RESET"
    ADMIN_BOOTSTRAPPED = "ADMIN_BOOTSTRAPPED"
    PASSWORD_CHANGED = "PASSWORD_CHANGED"  # noqa: S105  # audit action name, not a secret
    ACCOUNT_DELETED = "ACCOUNT_DELETED"
    ROLE_CHANGED = "ROLE_CHANGED"
    USER_DEACTIVATED = "USER_DEACTIVATED"
    USER_REACTIVATED = "USER_REACTIVATED"
    PASSWORD_RESET_CODE_ISSUED = "PASSWORD_RESET_CODE_ISSUED"  # noqa: S105  # audit action name, not a secret
    PASSWORD_RESET = "PASSWORD_RESET"  # noqa: S105  # audit action name, not a secret
    WORKING_HOURS_CHANGED = "WORKING_HOURS_CHANGED"
    ABSENCE_CREATED = "ABSENCE_CREATED"
    ABSENCE_DELETED = "ABSENCE_DELETED"
    APPOINTMENT_BOOKED = "APPOINTMENT_BOOKED"
    APPOINTMENT_RESCHEDULED = "APPOINTMENT_RESCHEDULED"
    APPOINTMENT_CANCELLED = "APPOINTMENT_CANCELLED"
    APPOINTMENT_ACCESS_GRANTED = "APPOINTMENT_ACCESS_GRANTED"
    APPOINTMENT_ACCESS_EXPIRED = "APPOINTMENT_ACCESS_EXPIRED"
    APPOINTMENT_DATA_ACCESSED = "APPOINTMENT_DATA_ACCESSED"
    SETTINGS_UPDATED = "SETTINGS_UPDATED"
    ACCESS_DENIED = "ACCESS_DENIED"


class AuditOutcome(enum.StrEnum):
    SUCCESS = "SUCCESS"
    FAILURE = "FAILURE"
    DENIED = "DENIED"


IPAddress = IPv4Address | IPv6Address


class Base(DeclarativeBase):
    type_annotation_map = {  # noqa: RUF012  # SQLAlchemy reads this class attribute
        datetime: DateTime(timezone=True),
        time: Time(),
        str: Text(),
        bytes: LargeBinary(),
        # None is SQL NULL, not JSON null (which audit_events_details_check rejects)
        dict[str, Any]: JSONB(none_as_null=True),
        # text + CHECK in the database (database.md, Enums); validated in Python as well
        enum.Enum: Enum(enum.Enum, native_enum=False, create_constraint=False),
    }


def _user_fk(*, ondelete: str | None = None) -> ForeignKey:
    return ForeignKey("users.id", ondelete=ondelete)


_DB_DEFAULT = FetchedValue()


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, server_default=_DB_DEFAULT)
    # NULL only after account deletion (BR-13)
    email: Mapped[str | None] = mapped_column(CITEXT())
    display_name: Mapped[str | None]
    role: Mapped[Role]
    is_active: Mapped[bool] = mapped_column(server_default=_DB_DEFAULT)
    created_at: Mapped[datetime] = mapped_column(server_default=_DB_DEFAULT)
    deleted_at: Mapped[datetime | None]
    mfa_offer_declined_at: Mapped[datetime | None]


class Credential(Base):
    """Only the auth module reads this table."""

    __tablename__ = "credentials"

    user_id: Mapped[uuid.UUID] = mapped_column(_user_fk(ondelete="CASCADE"), primary_key=True)
    password_hash: Mapped[str]
    mfa_secret_enc: Mapped[bytes | None]
    mfa_enabled: Mapped[bool] = mapped_column(server_default=_DB_DEFAULT)
    totp_last_step: Mapped[int | None]
    password_changed_at: Mapped[datetime] = mapped_column(server_default=_DB_DEFAULT)

    def __repr__(self) -> str:
        # Never render the hash or the MFA secret, e.g. in a traceback.
        return f"Credential(user_id={self.user_id!r})"


class UserSession(Base):
    """Server-side login session; named UserSession to avoid confusion with the ORM Session."""

    __tablename__ = "sessions"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, server_default=_DB_DEFAULT)
    token_hash: Mapped[bytes]
    user_id: Mapped[uuid.UUID] = mapped_column(_user_fk(ondelete="CASCADE"))
    state: Mapped[SessionState]
    created_at: Mapped[datetime] = mapped_column(server_default=_DB_DEFAULT)
    last_seen_at: Mapped[datetime] = mapped_column(server_default=_DB_DEFAULT)
    expires_at: Mapped[datetime]


class RecoveryCode(Base):
    __tablename__ = "recovery_codes"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, server_default=_DB_DEFAULT)
    user_id: Mapped[uuid.UUID] = mapped_column(_user_fk(ondelete="CASCADE"))
    code_hash: Mapped[str]
    used_at: Mapped[datetime | None]
    created_at: Mapped[datetime] = mapped_column(server_default=_DB_DEFAULT)


class PasswordResetCode(Base):
    __tablename__ = "password_reset_codes"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, server_default=_DB_DEFAULT)
    user_id: Mapped[uuid.UUID] = mapped_column(_user_fk(ondelete="CASCADE"))
    code_hash: Mapped[str]
    issued_by_id: Mapped[uuid.UUID] = mapped_column(_user_fk())
    created_at: Mapped[datetime] = mapped_column(server_default=_DB_DEFAULT)
    expires_at: Mapped[datetime]
    used_at: Mapped[datetime | None]
    failed_attempts: Mapped[int] = mapped_column(SmallInteger, server_default=_DB_DEFAULT)


class Invitation(Base):
    __tablename__ = "invitations"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, server_default=_DB_DEFAULT)
    email: Mapped[str] = mapped_column(CITEXT())
    role: Mapped[Role]
    display_name: Mapped[str]
    token_hash: Mapped[bytes]
    invited_by_id: Mapped[uuid.UUID] = mapped_column(_user_fk())
    created_at: Mapped[datetime] = mapped_column(server_default=_DB_DEFAULT)
    expires_at: Mapped[datetime]
    accepted_at: Mapped[datetime | None]
    user_id: Mapped[uuid.UUID | None] = mapped_column(_user_fk())


class PracticeSettings(Base):
    """Single row (id = 1), created by migration V003."""

    __tablename__ = "practice_settings"

    id: Mapped[int] = mapped_column(SmallInteger, primary_key=True, server_default=_DB_DEFAULT)
    practice_name: Mapped[str]
    cancellation_deadline_hours: Mapped[int] = mapped_column(server_default=_DB_DEFAULT)
    appointment_minutes: Mapped[int] = mapped_column(server_default=_DB_DEFAULT)
    updated_at: Mapped[datetime] = mapped_column(server_default=_DB_DEFAULT)
    # NULL means the practice setup is still pending (BR-18)
    updated_by_id: Mapped[uuid.UUID | None] = mapped_column(_user_fk())


class AdminBootstrap(Base):
    """Single row (id = 1), created by migration V003; locked at login (BR-04)."""

    __tablename__ = "admin_bootstrap"

    id: Mapped[int] = mapped_column(SmallInteger, primary_key=True, server_default=_DB_DEFAULT)
    bootstrapped: Mapped[bool] = mapped_column(server_default=_DB_DEFAULT)
    admin_id: Mapped[uuid.UUID | None] = mapped_column(_user_fk())
    bootstrapped_at: Mapped[datetime | None]


class AdminAccessGrant(Base):
    __tablename__ = "admin_access_grants"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, server_default=_DB_DEFAULT)
    admin_id: Mapped[uuid.UUID] = mapped_column(_user_fk())
    purpose: Mapped[AccessPurpose]
    created_at: Mapped[datetime] = mapped_column(server_default=_DB_DEFAULT)
    expires_at: Mapped[datetime]
    expiry_logged_at: Mapped[datetime | None]


class WorkingHours(Base):
    """Local time in Europe/Berlin (BR-08)."""

    __tablename__ = "working_hours"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, server_default=_DB_DEFAULT)
    doctor_id: Mapped[uuid.UUID] = mapped_column(_user_fk())
    weekday: Mapped[int] = mapped_column(SmallInteger)  # ISO, 1 = Monday
    start_time: Mapped[time]
    end_time: Mapped[time]
    updated_by_id: Mapped[uuid.UUID] = mapped_column(_user_fk())
    updated_at: Mapped[datetime] = mapped_column(server_default=_DB_DEFAULT)


class Absence(Base):
    __tablename__ = "absences"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, server_default=_DB_DEFAULT)
    doctor_id: Mapped[uuid.UUID] = mapped_column(_user_fk())
    starts_at: Mapped[datetime]
    ends_at: Mapped[datetime]
    created_by_id: Mapped[uuid.UUID] = mapped_column(_user_fk())
    created_at: Mapped[datetime] = mapped_column(server_default=_DB_DEFAULT)


class Appointment(Base):
    """Never deleted (BR-11)."""

    __tablename__ = "appointments"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, server_default=_DB_DEFAULT)
    doctor_id: Mapped[uuid.UUID] = mapped_column(_user_fk())
    starts_at: Mapped[datetime]
    ends_at: Mapped[datetime]
    patient_id: Mapped[uuid.UUID | None] = mapped_column(_user_fk())
    guest_name: Mapped[str | None]
    guest_phone: Mapped[str | None]
    guest_erased_at: Mapped[datetime | None]
    booked_by_id: Mapped[uuid.UUID] = mapped_column(_user_fk())
    reason: Mapped[AppointmentReason]
    status: Mapped[AppointmentStatus] = mapped_column(server_default=_DB_DEFAULT)
    created_at: Mapped[datetime] = mapped_column(server_default=_DB_DEFAULT)
    cancelled_at: Mapped[datetime | None]
    cancelled_by_id: Mapped[uuid.UUID | None] = mapped_column(_user_fk())


class AuditEvent(Base):
    """Append-only: the application role may only SELECT and INSERT (V004)."""

    __tablename__ = "audit_events"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, server_default=_DB_DEFAULT)
    actor_id: Mapped[uuid.UUID | None] = mapped_column(_user_fk())
    action: Mapped[AuditAction]
    target: Mapped[str | None]
    ip: Mapped[IPAddress | None] = mapped_column(INET())
    timestamp: Mapped[datetime] = mapped_column(server_default=_DB_DEFAULT)
    outcome: Mapped[AuditOutcome]
    details: Mapped[dict[str, Any] | None]
