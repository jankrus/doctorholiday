"""Seed data for local development only (#12): `make seed` (= `python -m doctorholiday.seed`).

Creates one account per role, two doctors with working hours and two booked appointments, so the
app is clickable on a fresh database. It is a one-off command, never part of the app's startup,
and refuses to run unless

- `SEED_DEV_DATA=true` is set (the cluster manifests never set it), and
- `DATABASE_URL` points at this machine (localhost, 127.0.0.1 or ::1).

All seeded accounts share the password from `SEED_PASSWORD`, which the developer chooses; no
password is part of the code. It must satisfy the same policy as a registration (BR-01). Seeding
twice changes nothing: if the seeded admin already exists, the command stops.

The seeded admin is recorded in `admin_bootstrap`, so the first-login bootstrap (#15) does not
promote another account. The practice setup stays pending (`practice_settings.updated_by_id` is
NULL), as on a fresh installation.
"""

import sys
from dataclasses import dataclass
from datetime import UTC, datetime, time, timedelta
from typing import Annotated
from urllib.parse import urlsplit

from pydantic import Field, SecretStr, ValidationError
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy import create_engine, func, select, update
from sqlalchemy.orm import Session

from doctorholiday.auth.passwords import hash_password, is_common_password
from doctorholiday.models import AdminBootstrap, AppointmentReason, Role, User, WorkingHours
from doctorholiday.repositories.appointments import book_appointment
from doctorholiday.repositories.users import create_user, get_user_by_email

_LOCAL_HOSTS = frozenset({"localhost", "127.0.0.1", "::1"})


@dataclass(frozen=True)
class SeedAccount:
    email: str
    display_name: str
    role: Role


ADMIN = SeedAccount("dev-admin@example.com", "Dev Admin", Role.ADMIN)
STAFF = SeedAccount("dev-staff@example.com", "Dev Staff", Role.STAFF)
DOCTORS = (
    SeedAccount("dev-doctor-1@example.com", "Dr. Dev One", Role.DOCTOR),
    SeedAccount("dev-doctor-2@example.com", "Dr. Dev Two", Role.DOCTOR),
)
PATIENTS = (
    SeedAccount("dev-patient-1@example.com", "Dev Patient One", Role.PATIENT),
    SeedAccount("dev-patient-2@example.com", "Dev Patient Two", Role.PATIENT),
)
ACCOUNTS = (ADMIN, STAFF, *DOCTORS, *PATIENTS)

# Local time in Europe/Berlin (BR-08): Monday to Friday, 08:00-12:00 and 14:00-17:00.
WORKING_HOURS = tuple(
    (weekday, start, end)
    for weekday in range(1, 6)
    for start, end in ((time(8), time(12)), (time(14), time(17)))
)


class SeedSettings(BaseSettings):
    model_config = SettingsConfigDict(frozen=True, extra="ignore")

    database_url: SecretStr
    seed_dev_data: bool = False
    seed_password: Annotated[SecretStr, Field(min_length=12, max_length=128)]


class SeedRefusedError(Exception):
    """The command must not run here. The message is safe to print: it never holds a value."""


def check_allowed(settings: SeedSettings) -> None:
    if not settings.seed_dev_data:
        raise SeedRefusedError("SEED_DEV_DATA is not true; seed data is for local development")
    url = settings.database_url.get_secret_value()
    if not url.startswith("postgresql+psycopg://"):
        raise SeedRefusedError("DATABASE_URL must start with postgresql+psycopg://")
    if urlsplit(url).hostname not in _LOCAL_HOSTS:
        raise SeedRefusedError("DATABASE_URL must point at localhost; seed data is local only")
    password = settings.seed_password.get_secret_value()
    if any(is_common_password(password, email=account.email) for account in ACCOUNTS):
        raise SeedRefusedError("SEED_PASSWORD is too common (BR-01); choose another one")


def _next_monday(now: datetime) -> datetime:
    days = 7 - now.weekday()  # 1-7 days ahead, never today
    return datetime.combine(now.date() + timedelta(days=days), time(), tzinfo=UTC)


def seed(session: Session, password: str, *, now: datetime) -> bool:
    """Insert the seed data in the caller's transaction. False if it is already there."""
    if get_user_by_email(session, ADMIN.email) is not None:
        return False

    users: dict[SeedAccount, User] = {
        account: create_user(
            session,
            email=account.email,
            display_name=account.display_name,
            role=account.role,
            # Hashed per account, so every row has its own salt.
            password_hash=hash_password(password),
        )
        for account in ACCOUNTS
    }

    session.execute(
        update(AdminBootstrap)
        .where(AdminBootstrap.id == 1, AdminBootstrap.bootstrapped.is_(False))
        .values(bootstrapped=True, admin_id=users[ADMIN].id, bootstrapped_at=func.now())
    )

    for doctor in DOCTORS:
        doctor_id = users[doctor].id
        session.add_all(
            WorkingHours(
                doctor_id=doctor_id,
                weekday=weekday,
                start_time=start,
                end_time=end,
                updated_by_id=doctor_id,
            )
            for weekday, start, end in WORKING_HOURS
        )
    session.flush()

    # 08:00 and 09:00 UTC are inside the morning hours in winter and summer time alike.
    monday = _next_monday(now)
    for patient, doctor, starts_at in (
        (PATIENTS[0], DOCTORS[0], monday + timedelta(hours=8)),
        (PATIENTS[1], DOCTORS[1], monday + timedelta(days=1, hours=9)),
    ):
        book_appointment(
            session,
            doctor_id=users[doctor].id,
            starts_at=starts_at,
            ends_at=starts_at + timedelta(minutes=15),
            booked_by_id=users[patient].id,
            reason=AppointmentReason.CHECKUP,
            patient_id=users[patient].id,
        )
    return True


def main() -> int:
    try:
        settings = SeedSettings()  # type: ignore[call-arg]  # filled from the environment
        check_allowed(settings)
    except ValidationError as exc:
        # Variable names only: pydantic's default string form contains the input values.
        names = sorted({str(error["loc"][0]).upper() for error in exc.errors()})
        sys.stderr.write(f"seed: invalid or missing: {', '.join(names)}\n")
        return 2
    except SeedRefusedError as exc:
        sys.stderr.write(f"seed: refused: {exc}\n")
        return 2

    engine = create_engine(settings.database_url.get_secret_value(), hide_parameters=True)
    try:
        with Session(engine) as session, session.begin():
            now = session.execute(select(func.now())).scalar_one()
            seeded = seed(session, settings.seed_password.get_secret_value(), now=now)
    finally:
        engine.dispose()

    if not seeded:
        sys.stdout.write("seed: already seeded, nothing changed\n")
        return 0
    sys.stdout.write("seed: created these accounts, all with the password from SEED_PASSWORD:\n")
    for account in ACCOUNTS:
        sys.stdout.write(f"  {account.role:<8} {account.email}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
