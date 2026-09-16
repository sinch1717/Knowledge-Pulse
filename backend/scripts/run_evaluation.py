"""Score the assistant against the held-out set.

    python scripts/run_evaluation.py

Costs one generation call and three judge calls per question, so fifty questions
is two hundred calls. Fine on Groq's free tier; check your quota on Gemini.
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import evaluation  # noqa: E402
from app.config import settings  # noqa: E402
from app.db import SessionLocal, create_tables  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)-7s | %(message)s",
                    datefmt="%H:%M:%S")
log = logging.getLogger("eval")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--organization-id",
        default=settings.default_organization_id,
        help=f"Organization tenant identifier (default: {settings.default_organization_id})",
    )
    args = parser.parse_args()

    create_tables()
    db = SessionLocal()
    try:
        questions = evaluation.load_question_set("data/eval_set.json")
        log.info("Scoring %d questions for organization '%s'", len(questions), args.organization_id)
        run = evaluation.run_evaluation(db, questions, organization_id=args.organization_id)
        log.info("faithfulness      %.2f", run.faithfulness)
        log.info("answer relevance  %.2f", run.answer_relevance)
        log.info("context relevance %.2f", run.context_relevance)
        if run.faithfulness < 0.80:
            log.warning("Faithfulness is below the 0.80 target set in NFR4.")
    finally:
        db.close()


if __name__ == "__main__":
    main()
