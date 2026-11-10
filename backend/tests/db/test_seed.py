"""Dev seed data (#12) in a rolled-back transaction, so the shared test database stays as is."""

from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from doctorholiday import seed
from doctorholiday.auth.passwords import verify_password
from doctorholiday.models import (
    AdminBootstrap,
    Appointment,
    AppointmentStatus,
    Credential,
    User,
    WorkingHours,
)

PASSWORD = "seed passphrase for tests"
NOW = datetime(2030, 1, 9, 15, 30, tzinfo=UTC)  # a Wednesday


def _seeded_users(session: Session) -> dict[str, User]:
    emails = [account.email for account in seed.ACCOUNTS]
    return {u.email or "": u for u in session.scalars(select(User).where(User.email.in_(emails)))}


def test_seed_creates_every_role_with_the_seed_password(db_session: Session) -> None:
    assert seed.seed(db_session, PASSWORD, now=NOW)

    users = _seeded_users(db_session)
    assert {email: user.role for email, user in users.items()} == {
        account.email: account.role for account in seed.ACCOUNTS
    }
    hashes = [db_session.get(Credential, user.id).password_hash for user in users.values()]  # type: ignore[union-attr]
    assert all(verify_password(h, PASSWORD) for h in hashes)
    assert len(set(hashes)) == len(hashes)  # salted per account


def test_seed_records_the_admin_as_bootstrapped(db_session: Session) -> None:
    seed.seed(db_session, PASSWORD, now=NOW)

    bootstrap = db_session.get(AdminBootstrap, 1)
    db_session.refresh(bootstrap)
    assert bootstrap is not None
    assert bootstrap.bootstrapped
    assert bootstrap.admin_id == _seeded_users(db_session)[seed.ADMIN.email].id


def test_seed_creates_working_hours_and_future_appointments(db_session: Session) -> None:
    seed.seed(db_session, PASSWORD, now=NOW)
    users = _seeded_users(db_session)

    for doctor in seed.DOCTORS:
        hours = db_session.scalar(
            select(func.count())
            .select_from(WorkingHours)
            .where(WorkingHours.doctor_id == users[doctor.email].id)
        )
        assert hours == 10
    appointments = db_session.scalars(
        select(Appointment).where(
            Appointment.patient_id.in_([users[p.email].id for p in seed.PATIENTS])
        )
    ).all()
    assert len(appointments) == 2
    for appointment in appointments:
        assert appointment.status is AppointmentStatus.BOOKED
        assert NOW < appointment.starts_at < NOW + timedelta(days=8)
        assert appointment.starts_at.weekday() in (0, 1)


def test_seeding_twice_changes_nothing(db_session: Session) -> None:
    assert seed.seed(db_session, PASSWORD, now=NOW)
    assert not seed.seed(db_session, "another seed passphrase", now=NOW)

    assert len(_seeded_users(db_session)) == len(seed.ACCOUNTS)
