"""Application factory."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from doctorholiday.api import health
from doctorholiday.config import Settings
from doctorholiday.db import create_db_engine, create_session_factory
from doctorholiday.middleware import RequestContextMiddleware


def create_app(settings: Settings) -> FastAPI:
    engine = create_db_engine(settings)

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        yield
        engine.dispose()

    # No interactive docs or generated schema: the contract is backend/openapi.yaml, and the
    # running service should not advertise its framework or surface.
    app = FastAPI(
        title="Doctor Holiday API",
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
        lifespan=lifespan,
    )
    app.state.settings = settings
    app.state.engine = engine
    app.state.session_factory = create_session_factory(engine)
    app.add_middleware(RequestContextMiddleware)
    app.include_router(health.router)
    return app
