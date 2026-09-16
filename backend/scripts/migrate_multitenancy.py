"""Idempotent migration script to add multi-tenancy columns and indexes to SQLite.

Backfills existing data with org_default and verifies no NULL organization_id rows exist.
Safe to run repeatedly.

    python scripts/migrate_multitenancy.py
"""

from __future__ import annotations

import logging
import sqlite3
import sys
from pathlib import Path

# Add backend root to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import settings

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)-7s | %(message)s")
log = logging.getLogger("migration")

TENANT_TABLES = [
    "sources",
    "chunks",
    "conversations",
    "messages",
    "topic_clusters",
    "cluster_members",
    "reports",
    "recommendations",
    "evaluation_runs",
]

INDEXES = [
    # Single column indexes
    ("ix_sources_organization_id", "sources", ["organization_id"]),
    ("ix_chunks_organization_id", "chunks", ["organization_id"]),
    ("ix_conversations_organization_id", "conversations", ["organization_id"]),
    ("ix_messages_organization_id", "messages", ["organization_id"]),
    ("ix_topic_clusters_organization_id", "topic_clusters", ["organization_id"]),
    ("ix_cluster_members_organization_id", "cluster_members", ["organization_id"]),
    ("ix_reports_organization_id", "reports", ["organization_id"]),
    ("ix_recommendations_organization_id", "recommendations", ["organization_id"]),
    ("ix_evaluation_runs_organization_id", "evaluation_runs", ["organization_id"]),
    # Composite indexes
    ("ix_sources_org_created_at", "sources", ["organization_id", "created_at"]),
    ("ix_chunks_org_source_id", "chunks", ["organization_id", "source_id"]),
    ("ix_conversations_org_session_id", "conversations", ["organization_id", "session_id"]),
    ("ix_messages_org_period", "messages", ["organization_id", "period"]),
    ("ix_messages_org_created_at", "messages", ["organization_id", "created_at"]),
    ("ix_messages_org_conversation_id", "messages", ["organization_id", "conversation_id"]),
    ("ix_topic_clusters_org_period", "topic_clusters", ["organization_id", "period"]),
    ("ix_cluster_members_org_cluster_id", "cluster_members", ["organization_id", "cluster_id"]),
    ("ix_reports_org_period", "reports", ["organization_id", "period"]),
    ("ix_recommendations_org_report_id", "recommendations", ["organization_id", "report_id"]),
    ("ix_evaluation_runs_org_ran_at", "evaluation_runs", ["organization_id", "ran_at"]),
]


def get_sqlite_path() -> Path:
    db_url = settings.database_url
    if not db_url.startswith("sqlite"):
        raise RuntimeError(
            f"This migration script is designed for SQLite local development. Current DATABASE_URL: {db_url}"
        )
    clean_path = db_url.replace("sqlite:///", "").replace("sqlite://", "")
    return Path(clean_path).resolve()


def migrate() -> None:
    db_path = get_sqlite_path()
    log.info("Connecting to SQLite database at: %s", db_path)

    if not db_path.exists():
        log.info("Database file does not exist yet; creating tables via app.db.create_tables()...")
        from app.db import create_tables
        create_tables()
        log.info("Tables created with multi-tenancy schema.")
        return

    con = sqlite3.connect(str(db_path))
    con.row_factory = sqlite3.Row
    cur = con.cursor()

    try:
        cur.execute("PRAGMA foreign_keys = OFF;")

        # 1. Inspect existing tables
        cur.execute("SELECT name FROM sqlite_master WHERE type='table';")
        existing_tables = {row["name"] for row in cur.fetchall()}
        log.info("Found existing tables: %s", sorted(existing_tables))

        changes_made = 0

        # 2. Add organization_id column if missing & backfill
        for table in TENANT_TABLES:
            if table not in existing_tables:
                log.info("Table '%s' does not exist yet. Skipping column migration for it.", table)
                continue

            cur.execute(f"PRAGMA table_info({table});")
            columns = {col["name"]: col for col in cur.fetchall()}

            if "organization_id" not in columns:
                log.info("Adding 'organization_id' column to '%s'...", table)
                cur.execute(
                    f"ALTER TABLE {table} ADD COLUMN organization_id VARCHAR(64) NOT NULL DEFAULT '{settings.default_organization_id}';"
                )
                changes_made += 1
                log.info("Added 'organization_id' to '%s' with default '%s'.", table, settings.default_organization_id)
            else:
                log.info("Table '%s' already has 'organization_id' column.", table)

            # Ensure no existing rows have NULL or empty organization_id
            cur.execute(
                f"UPDATE {table} SET organization_id = ? WHERE organization_id IS NULL OR organization_id = '';",
                (settings.default_organization_id,),
            )
            if cur.rowcount > 0:
                log.info("Backfilled %d rows in '%s' with '%s'.", cur.rowcount, table, settings.default_organization_id)
                changes_made += 1

        con.commit()

        # 3. Create indexes
        for idx_name, table, cols in INDEXES:
            if table not in existing_tables:
                continue
            cols_joined = ", ".join(cols)
            sql = f"CREATE INDEX IF NOT EXISTS {idx_name} ON {table} ({cols_joined});"
            cur.execute(sql)

        con.commit()
        log.info("Indexes verified/created successfully.")

        # 4. Verify no NULL organization_id exists in any tenant table
        log.info("Verifying migration integrity...")
        for table in TENANT_TABLES:
            if table not in existing_tables:
                continue
            cur.execute(f"SELECT COUNT(*) FROM {table} WHERE organization_id IS NULL;")
            null_count = cur.fetchone()[0]
            if null_count > 0:
                raise RuntimeError(
                    f"Integrity check failed: Table '{table}' contains {null_count} rows with NULL organization_id!"
                )
            cur.execute(f"SELECT COUNT(*) FROM {table};")
            total_count = cur.fetchone()[0]
            log.info("  Table '%s': %d total rows, 0 NULL organization_id rows. (PASS)", table, total_count)

        log.info("Migration complete. Total structural/backfill operations: %d", changes_made)

    finally:
        cur.close()
        con.close()


if __name__ == "__main__":
    migrate()
