"""Score the assistant against the held-out set.

    python scripts/run_evaluation.py

Costs one generation call and three judge calls per question, so fifty questions
is two hundred calls. Fine on Groq's free tier; check your quota on Gemini.
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import evaluation  # noqa: E402
from app.db import SessionLocal, create_tables  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)-7s | %(message)s",
                    datefmt="%H:%M:%S")
log = logging.getLogger("eval")


def main() -> None:
    create_tables()
    db = SessionLocal()
    try:
        questions = evaluation.load_question_set("data/eval_set.json")
        log.info("Scoring %d questions", len(questions))
        run = evaluation.run_evaluation(db, questions)
        log.info("faithfulness      %.2f", run.faithfulness)
        log.info("answer relevance  %.2f", run.answer_relevance)
        log.info("context relevance %.2f", run.context_relevance)
        if run.faithfulness < 0.80:
            log.warning("Faithfulness is below the 0.80 target set in NFR4.")
    finally:
        db.close()


if __name__ == "__main__":
    main()
