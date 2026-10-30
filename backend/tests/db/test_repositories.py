from datetime import UTC, datetime, timedelta
from ipaddress import IPv4Address

import pytest
from sqlalchemy.orm import Session

from doctorholiday.models import (
    Appointment,
    AppointmentReason,
    AppointmentStatus,
    AuditAction,
    AuditEvent,
    AuditOutcome,
    Role,
    User,
)
from doctorholiday.repositories import appointments, audit, users
from doctorholiday.repositories.errors import EmailAlreadyRegisteredError, TimeAlreadyBookedError
from tests.db.conftest import DUMMY_PASSWORD_HASH, UserFactory

NINE = datetime(2030, 1, 7, 9, 0, tzinfo=UTC)
SLOT = timedelta(minutes=15)


def _book(session: Session, doctor: User, patient: User, starts_at: datetime) -> Appointment:
    return appointments.book_appointment(
        session,
        doctor_id=doctor.id,
        starts_at=starts_at,
        ends_at=starts_at + SLOT,
        booked_by_id=patient.id,
        reason=AppointmentReason.CHECKUP,
        patient_id=patient.id,
    )


class TestUsers:
    def test_create_fills_database_defaults_and_credentials(self, db_session: Session) -> None:
        user = users.create_user(
            db_session,
            email="Anna.Muster@Example.test",
            display_name="Anna Muster",
            role=Role.PATIENT,
            password_hash=DUMMY_PASSWORD_HASH,
        )

        assert user.id is not None
        assert user.is_active is True
        assert user.created_at.tzinfo is not None
        credential = users.get_credential(db_session, user.id)
        assert credential is not None
        assert credential.mfa_enabled is False
        assert DUMMY_PASSWORD_HASH not in repr(credential)

    def test_email_lookup_is_case_insensitive(
        self, db_session: Session, make_user: UserFactory
    ) -> None:
        user = make_user()
        assert users.get_user_by_email(db_session, user.email.upper()) == user

    def test_duplicate_email_in_other_case_is_a_conflict(
        self, db_session: Session, make_user: UserFactory
    ) -> None:
        user = make_user()
        with pytest.raises(EmailAlreadyRegisteredError) as exc_info:
            users.create_user(
                db_session,
                email=user.email.upper(),
                display_name="Someone",
                role=Role.PATIENT,
                password_hash=DUMMY_PASSWORD_HASH,
            )
        # No database text (with the e-mail in its DETAIL line) travels with the domain error.
        assert exc_info.value.__suppress_context__
        # The conflict rolled back its savepoint only; the transaction still runs queries.
        assert users.get_user_by_email(db_session, user.email) == user


class TestAppointments:
    def test_overlapping_booking_is_rejected(
        self, db_session: Session, make_user: UserFactory
    ) -> None:
        doctor, patient = make_user(Role.DOCTOR), make_user()
        _book(db_session, doctor, patient, NINE)

        with pytest.raises(TimeAlreadyBookedError):
            _book(db_session, doctor, make_user(), NINE + timedelta(minutes=10))

        assert (
            len(
                appointments.list_booked_for_doctor(
                    db_session, doctor.id, starts_before=NINE + 2 * SLOT, ends_after=NINE
                )
            )
            == 1
        )

    def test_back_to_back_and_other_doctors_are_allowed(
        self, db_session: Session, make_user: UserFactory
    ) -> None:
        doctor, other_doctor, patient = make_user(Role.DOCTOR), make_user(Role.DOCTOR), make_user()
        _book(db_session, doctor, patient, NINE)
        _book(db_session, doctor, patient, NINE + SLOT)
        _book(db_session, other_doctor, patient, NINE)

    def test_cancelled_time_can_be_booked_again(
        self, db_session: Session, make_user: UserFactory
    ) -> None:
        doctor, patient = make_user(Role.DOCTOR), make_user()
        first = _book(db_session, doctor, patient, NINE)

        appointments.cancel_appointment(db_session, first, cancelled_by_id=patient.id)
        second = _book(db_session, doctor, patient, NINE)

        assert first.status is AppointmentStatus.CANCELLED
        assert first.cancelled_at is not None
        assert appointments.list_booked_for_doctor(
            db_session, doctor.id, starts_before=NINE + SLOT, ends_after=NINE
        ) == [second]

    def test_guest_booking(self, db_session: Session, make_user: UserFactory) -> None:
        doctor, staff = make_user(Role.DOCTOR), make_user(Role.STAFF)
        booked = appointments.book_appointment(
            db_session,
            doctor_id=doctor.id,
            starts_at=NINE,
            ends_at=NINE + SLOT,
            booked_by_id=staff.id,
            reason=AppointmentReason.VACCINATION,
            guest_name="Max Gast",
            guest_phone="+4915112345678",
        )
        db_session.expire_all()
        loaded = appointments.get_appointment(db_session, booked.id)
        assert loaded is not None
        assert loaded.reason is AppointmentReason.VACCINATION
        assert loaded.status is AppointmentStatus.BOOKED
        assert loaded.patient_id is None

    def test_list_returns_only_overlapping_booked_appointments(
        self, db_session: Session, make_user: UserFactory
    ) -> None:
        doctor, patient = make_user(Role.DOCTOR), make_user()
        before = _book(db_session, doctor, patient, NINE - SLOT)
        inside = _book(db_session, doctor, patient, NINE)
        _book(db_session, doctor, patient, NINE + SLOT)  # starts exactly at the window's end

        assert appointments.list_booked_for_doctor(
            db_session, doctor.id, starts_before=NINE + SLOT, ends_after=NINE - timedelta(minutes=5)
        ) == [before, inside]


class TestAudit:
    def test_record_event_round_trip(self, db_session: Session, make_user: UserFactory) -> None:
        actor = make_user()
        event = audit.record_event(
            db_session,
            action=AuditAction.APPOINTMENT_RESCHEDULED,
            outcome=AuditOutcome.SUCCESS,
            actor_id=actor.id,
            target=audit.audit_target("user", actor.id),
            ip=IPv4Address("192.0.2.10"),
            details={"oldStartsAt": "2030-01-07T09:00:00Z"},
        )
        db_session.expire_all()

        loaded = db_session.get(AuditEvent, event.id)
        assert loaded is not None
        assert loaded.action is AuditAction.APPOINTMENT_RESCHEDULED
        assert loaded.ip == IPv4Address("192.0.2.10")
        assert loaded.details == {"oldStartsAt": "2030-01-07T09:00:00Z"}
        assert loaded.timestamp.tzinfo is not None

    def test_event_without_details_stores_sql_null(self, db_session: Session) -> None:
        event = audit.record_event(
            db_session, action=AuditAction.LOGIN, outcome=AuditOutcome.FAILURE
        )
        db_session.expire_all()
        assert db_session.get(AuditEvent, event.id).details is None
