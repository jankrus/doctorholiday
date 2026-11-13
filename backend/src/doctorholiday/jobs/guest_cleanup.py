"""Erase guest contact data (BR-24): `python -m doctorholiday.jobs.guest_cleanup`.

Run once a day (`make -C backend cleanup-guests` locally; a Kubernetes CronJob with the backend
image and its configuration in the cluster). Guest name and phone are erased 30 days after the
appointment ended or was cancelled; the job sets `guest_erased_at`, and the appointment keeps
only doctor, time, reason and status. It is idempotent: a second run the same day erases
nothing, and a missed day is caught up by the next run.

It uses the backend's configuration (`DATABASE_URL` and the other variables are validated as at
startup) and the same database role, which may update `appointments`. It logs only the number of
erased appointments, never guest data.
"""

import logging
import sys

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from doctorholiday.config import ConfigError, LogLevel, load_settings
from doctorholiday.db import create_db_engine
from doctorholiday.logs import configure_logging
from doctorholiday.repositories.appointments import erase_expired_guest_data

logger = logging.getLogger("doctorholiday.jobs.guest_cleanup")


def main() -> int:
    configure_logging(LogLevel.INFO)
    try:
        settings = load_settings()
    except ConfigError as exc:
        logger.critical("invalid configuration, exiting", extra={"errors": exc.errors})
        return 1
    configure_logging(settings.log_level)

    engine = create_db_engine(settings)
    try:
        with Session(engine) as session, session.begin():
            erased = erase_expired_guest_data(session)
    except SQLAlchemyError:
        logger.exception("guest data cleanup failed")
        return 1
    finally:
        engine.dispose()
    logger.info("guest data cleanup finished", extra={"erasedAppointments": erased})
    return 0


if __name__ == "__main__":
    sys.exit(main())
