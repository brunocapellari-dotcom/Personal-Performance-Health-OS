from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from .config import Settings


class Base(DeclarativeBase):
    pass


class Database:
    def __init__(self, settings: Settings) -> None:
        settings.validate()
        connect_args: dict[str, Any] = {}
        if settings.database_url.startswith("sqlite"):
            connect_args["check_same_thread"] = False
        self.engine: Engine = create_engine(
            settings.database_url,
            pool_pre_ping=True,
            connect_args=connect_args,
        )
        self._sessions = sessionmaker(bind=self.engine, expire_on_commit=False, class_=Session)

    @contextmanager
    def session(self) -> Iterator[Session]:
        db = self._sessions()
        try:
            yield db
            db.commit()
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    def create_schema_for_tests(self, settings: Settings) -> None:
        if settings.is_production:
            raise RuntimeError("production schema changes must run through Alembic")
        from . import models  # noqa: F401

        Base.metadata.create_all(self.engine)
