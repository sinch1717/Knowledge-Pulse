"""Database wiring. Deliberately small.

No Alembic yet. The schema is created from the models on startup, which is right
for a project that has not been deployed. Add migrations the first time you need
to change a table that holds data you care about.
"""

import os
from collections.abc import Iterator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import settings

connect_args = {"check_same_thread": False} if settings.database_url.startswith("sqlite") else {}

if settings.database_url.startswith("sqlite"):
    os.makedirs(os.path.dirname(settings.database_url.replace("sqlite:///", "")) or ".", exist_ok=True)

engine = create_engine(settings.database_url, connect_args=connect_args, future=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


def get_db() -> Iterator[Session]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def create_tables() -> None:
    from app import models  # noqa: F401  (import registers the mappings)

    Base.metadata.create_all(bind=engine)
