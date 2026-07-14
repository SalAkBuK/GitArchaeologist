from __future__ import annotations

import os
from collections.abc import Generator
from pathlib import Path

from fastapi import Request
from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker


class Base(DeclarativeBase):
    pass


def default_database_url() -> str:
    backend_directory = Path(__file__).resolve().parents[2]
    return f"sqlite:///{(backend_directory / 'git_archaeologist.db').as_posix()}"


class Database:
    def __init__(self, url: str | None = None) -> None:
        self.url = url or os.getenv("DATABASE_URL") or default_database_url()
        connect_args = {"check_same_thread": False} if self.url.startswith("sqlite") else {}
        self.engine: Engine = create_engine(self.url, connect_args=connect_args)
        self.session_factory = sessionmaker(
            bind=self.engine,
            class_=Session,
            expire_on_commit=False,
        )

    def create_schema(self) -> None:
        # Importing registers the model on Base.metadata before create_all runs.
        from app.models.artifact import ArtifactModel  # noqa: F401

        Base.metadata.create_all(self.engine)

    def dispose(self) -> None:
        self.engine.dispose()


def get_db(request: Request) -> Generator[Session, None, None]:
    database: Database = request.app.state.database
    with database.session_factory() as session:
        yield session
