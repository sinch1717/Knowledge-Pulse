"""Small, idempotent schema upgrades run on every start.

There is still no Alembic. The only change so far is adding workspace_id to the
existing tables, which `create_all` cannot do because it never alters a table
that already exists. `ALTER TABLE ... ADD COLUMN` with a default works the same
on SQLite and Postgres, so existing rows land in the default workspace.

Safe to run any number of times.
"""

from __future__ import annotations

import logging

from sqlalchemy import inspect, text

from app.db import SessionLocal, create_tables, engine
from app.models import DEFAULT_WORKSPACE_ID, Source, Workspace

log = logging.getLogger(__name__)

WORKSPACE_TABLES = [
    "sources",
    "conversations",
    "messages",
    "topic_clusters",
    "reports",
    "evaluation_runs",
]

# A source in one of these states when the server starts was interrupted: the
# thread doing the work died with the previous process.
IN_FLIGHT = ("queued", "crawling", "indexing", "stopping")


def _add_workspace_columns() -> None:
    inspector = inspect(engine)
    existing_tables = set(inspector.get_table_names())
    with engine.begin() as conn:
        for table in WORKSPACE_TABLES:
            if table not in existing_tables:
                continue
            columns = {c["name"] for c in inspector.get_columns(table)}
            if "workspace_id" in columns:
                continue
            log.info("Adding workspace_id to %s", table)
            conn.execute(
                text(
                    f"ALTER TABLE {table} ADD COLUMN workspace_id VARCHAR(40) "
                    f"NOT NULL DEFAULT '{DEFAULT_WORKSPACE_ID}'"
                )
            )
            conn.execute(text(f"CREATE INDEX IF NOT EXISTS ix_{table}_workspace_id ON {table} (workspace_id)"))


def _ensure_default_workspace() -> None:
    db = SessionLocal()
    try:
        if db.get(Workspace, DEFAULT_WORKSPACE_ID) is None:
            db.add(
                Workspace(
                    id=DEFAULT_WORKSPACE_ID,
                    name="Default workspace",
                    description="Everything created before workspaces existed.",
                )
            )
            db.commit()
    finally:
        db.close()


def _reset_interrupted_sources() -> None:
    db = SessionLocal()
    try:
        stuck = db.query(Source).filter(Source.status.in_(IN_FLIGHT)).all()
        for source in stuck:
            # A source that was indexed before keeps its old chunks, because the
            # pipeline only replaces them at the very end.
            source.status = "ready" if source.chunk_count else "stopped"
            source.error = "Interrupted by a server restart. Reindex to try again."
        if stuck:
            log.warning("Reset %d interrupted source(s)", len(stuck))
            db.commit()
    finally:
        db.close()


def upgrade() -> None:
    create_tables()
    _add_workspace_columns()
    _ensure_default_workspace()
    _reset_interrupted_sources()
