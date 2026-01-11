from __future__ import annotations

from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

_engine = create_engine("sqlite:///./tsbot.db", connect_args={"check_same_thread": False})
_SessionLocal = sessionmaker(bind=_engine, autocommit=False, autoflush=False)


class Base(DeclarativeBase):
    pass


def create_db_and_tables() -> None:
    from . import models  # noqa: F401

    Base.metadata.create_all(_engine)


def new_session() -> Session:
    return _SessionLocal()


def get_session() -> Generator[Session, None, None]:
    session = _SessionLocal()
    try:
        yield session
    finally:
        session.close()
