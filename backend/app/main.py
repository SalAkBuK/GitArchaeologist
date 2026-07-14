from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.routes import router
from app.database.session import Database


def create_app(database_url: str | None = None) -> FastAPI:
    database = Database(database_url)

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        database.create_schema()
        yield
        database.dispose()

    application = FastAPI(
        title="GitArchaeologist AI API",
        version="0.1.0",
        lifespan=lifespan,
    )
    application.state.database = database
    application.include_router(router)
    return application


app = create_app()
