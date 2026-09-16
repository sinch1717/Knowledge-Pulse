"""Run the analytics batch.

    python scripts/run_analytics.py            # every period, oldest first
    python scripts/run_analytics.py --period 2026-08

Order matters when running several: each period needs the one before it already
clustered, or growth has nothing to compare against.
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.analytics import batch  # noqa: E402
from app.config import settings  # noqa: E402
from app.db import SessionLocal, create_tables  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)-7s %(name)s | %(message)s",
                    datefmt="%H:%M:%S")
log = logging.getLogger("analytics")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--organization-id",
        default=settings.default_organization_id,
        help=f"Organization tenant identifier (default: {settings.default_organization_id})",
    )
    parser.add_argument("--period", help="e.g. 2026-08. Omit to run every period in order.")
    args = parser.parse_args()

    create_tables()
    db = SessionLocal()
    try:
        log.info("Running analytics for organization: %s", args.organization_id)
        reports = (
            [batch.run_batch(db, args.period, organization_id=args.organization_id)]
            if args.period
            else batch.run_for_all_periods(db, organization_id=args.organization_id)
        )
        for report in [r for r in reports if r]:
            log.info(
                "%s: %d questions, %.0f%% poorly answered, %d recommendations",
                report.period, report.query_count, report.unanswered_rate * 100,
                len(report.recommendations),
            )
        if not any(reports):
            log.warning("No reports produced for org %s. Is there enough conversation data?", args.organization_id)
    finally:
        db.close()


if __name__ == "__main__":
    main()
