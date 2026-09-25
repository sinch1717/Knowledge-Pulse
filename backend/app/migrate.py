"""Small, idempotent schema upgrades run on every start.

There is still no Alembic. `create_all` never alters a table that already
exists, so columns added since a database was created are added here with
`ALTER TABLE ... ADD COLUMN ... DEFAULT`, which works the same on SQLite and
Postgres. Existing rows take the default, which is the right owner for them:

    workspace_id     -> "ws_default"   (everything from before workspaces)
    organization_id  -> "org_default"  (everything from before tenancy)

A database created by the organisation-only branch has organization_id but no
workspaces. Its rows for organisations other than the default are moved into
that organisation's own default workspace, not left in "ws_default".

Safe to run any number of times.
"""

from __future__ import annotations

import logging

from sqlalchemy import inspect, text

from app.config import settings
from app.db import Base, SessionLocal, create_tables, engine
from app.models import DEFAULT_WORKSPACE_ID, Source
from app.tenant import default_workspace_id, ensure_default_workspace

log = logging.getLogger(__name__)

# Tables a workspace owns directly. Chunks, cluster members and recommendations
# hang off a source, cluster or report, so they reach a workspace through it.
WORKSPACE_TABLES = [
    "sources",
    "conversations",
    "messages",
    "topic_clusters",
    "reports",
    "evaluation_runs",
]

# Every tenant-owned table.
ORGANIZATION_TABLES = [
    "workspaces",
    *WORKSPACE_TABLES,
    "chunks",
    "cluster_members",
    "recommendations",
]

# A source in one of these states when the server starts was interrupted: the
# thread doing the work died with the previous process.
IN_FLIGHT = ("queued", "crawling", "indexing", "stopping")


def _add_column(table: str, column: str, ddl: str) -> None:
    inspector = inspect(engine)
    if table not in inspector.get_table_names():
        return
    if column in {c["name"] for c in inspector.get_columns(table)}:
        return
    log.info("Adding %s to %s", column, table)
    with engine.begin() as conn:
        conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {column} {ddl}"))


def _add_columns() -> None:
    _add_column("messages", "citations", "JSON")
    for table in WORKSPACE_TABLES:
        _add_column(table, "workspace_id", f"VARCHAR(40) NOT NULL DEFAULT '{DEFAULT_WORKSPACE_ID}'")
    for table in ORGANIZATION_TABLES:
        _add_column(
            table,
            "organization_id",
            f"VARCHAR(64) NOT NULL DEFAULT '{settings.default_organization_id}'",
        )


def _create_indexes() -> None:
    """Every index the models declare, created if missing.

    Covers the single-column and composite indexes on columns that were just
    added, which `create_all` skips for tables that already existed.
    """
    for table in Base.metadata.sorted_tables:
        for index in table.indexes:
            index.create(bind=engine, checkfirst=True)


def _reconcile_organisation_rows() -> None:
    """Move rows of non-default organisations out of the default workspace.

    Only does anything on a database from the organisation-only branch, where
    workspace_id was just added with the default for every row.
    """
    default_org = settings.default_organization_id
    orgs: set[str] = set()
    with engine.connect() as conn:
        for table in WORKSPACE_TABLES:
            rows = conn.execute(
                text(
                    f"SELECT DISTINCT organization_id FROM {table} "
                    f"WHERE workspace_id = :ws AND organization_id != :org"
                ),
                {"ws": DEFAULT_WORKSPACE_ID, "org": default_org},
            )
            orgs.update(r[0] for r in rows)
    if not orgs:
        return

    db = SessionLocal()
    try:
        for org in sorted(orgs):
            ensure_default_workspace(db, org)
    finally:
        db.close()

    with engine.begin() as conn:
        for org in sorted(orgs):
            for table in WORKSPACE_TABLES:
                conn.execute(
                    text(
                        f"UPDATE {table} SET workspace_id = :target "
                        f"WHERE workspace_id = :ws AND organization_id = :org"
                    ),
                    {"target": default_workspace_id(org), "ws": DEFAULT_WORKSPACE_ID, "org": org},
                )
    log.info("Moved data for %d organisation(s) into their own default workspace", len(orgs))


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
    _add_columns()
    _create_indexes()
    db = SessionLocal()
    try:
        # "ws_default" belongs to the default organisation. Created here rather
        # than on first request so the scripts can rely on it.
        ensure_default_workspace(db, settings.default_organization_id)
    finally:
        db.close()
    _reconcile_organisation_rows()
    _reset_interrupted_sources()
