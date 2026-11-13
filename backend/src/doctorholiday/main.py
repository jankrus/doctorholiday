"""Application factory."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI

from doctorholiday.api import auth, directory, health
from doctorholiday.config import Settings
from doctorholiday.db import create_db_engine, create_session_factory
from doctorholiday.errors import install_error_handlers
from doctorholiday.middleware import RequestBodyMiddleware, RequestContextMiddleware
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
    # The last one added runs first: request ID, then body checks, then routing.
    app.add_middleware(RequestBodyMiddleware)
    app.add_middleware(RequestContextMiddleware)
    install_error_handlers(app)
    app.include_router(health.router)
    app.include_router(auth.router)
    app.include_router(directory.router)
    return app
