"""Application factory."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI

from doctorholiday.api import appointments, auth, directory, health, schedule
from doctorholiday.auth.policy import enforce_default_deny
from doctorholiday.config import Settings
from doctorholiday.db import create_db_engine, create_session_factory
from doctorholiday.errors import install_error_handlers
from doctorholiday.middleware import (
    CsrfMiddleware,
    RequestBodyMiddleware,
    RequestContextMiddleware,
    SecurityHeadersMiddleware,
)
from doctorholiday.validation import reject_unknown_query_params


def create_app(settings: Settings) -> FastAPI:
    engine = create_db_engine(settings)

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        yield
        engine.dispose()

    # No interactive docs or generated schema: the contract is backend/openapi.yaml, and the
    # running service should not advertise its framework or surface. debug=False (the default,
    # set explicitly) keeps tracebacks out of responses; uvicorn's Server header is off too.
    app = FastAPI(
        title="Doctor Holiday API",
        debug=False,
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
        lifespan=lifespan,
        dependencies=[Depends(reject_unknown_query_params)],
    )
    app.state.settings = settings
    app.state.engine = engine
    app.state.session_factory = create_session_factory(engine)
    # The last one added runs first: response headers, request ID, body checks, CSRF check, then
    # routing. No CORS middleware on purpose: same origin via the ingress (see CsrfMiddleware).
    app.add_middleware(CsrfMiddleware, allowed_origins=settings.allowed_origins)
    app.add_middleware(RequestBodyMiddleware)
    app.add_middleware(RequestContextMiddleware)
    app.add_middleware(SecurityHeadersMiddleware)
    install_error_handlers(app)
    app.include_router(health.router)
    app.include_router(auth.router)
    app.include_router(directory.router)
    app.include_router(schedule.router)
    app.include_router(appointments.router)
    enforce_default_deny(app)
    return app
