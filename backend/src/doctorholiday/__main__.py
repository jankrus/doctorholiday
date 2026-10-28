"""Entry point: `python -m doctorholiday`.

uvicorn handles SIGTERM/SIGINT: it stops accepting connections, lets running requests finish
(up to `timeout_graceful_shutdown`), runs the lifespan shutdown and exits with 0.
"""

import logging
import sys

import uvicorn

from doctorholiday.config import ConfigError, LogLevel, load_settings
from doctorholiday.logs import configure_logging
from doctorholiday.main import create_app

logger = logging.getLogger("doctorholiday")


def main() -> int:
    configure_logging(LogLevel.INFO)
    try:
        settings = load_settings()
    except ConfigError as exc:
        logger.critical("invalid configuration, exiting", extra={"errors": exc.errors})
        return 1
    configure_logging(settings.log_level)

    uvicorn.run(
        create_app(settings),
        host="0.0.0.0",  # noqa: S104 - container: the pod network is the boundary, see #41
        port=settings.port,
        log_config=None,
        access_log=False,
        server_header=False,
        timeout_graceful_shutdown=10,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
