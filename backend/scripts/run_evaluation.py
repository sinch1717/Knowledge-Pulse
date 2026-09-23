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
from app.db import SessionLocal  # noqa: E402
from app.migrate import upgrade  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)-7s | %(message)s",
                    datefmt="%H:%M:%S")
log = logging.getLogger("eval")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workspace", default="ws_default")
    parser.add_argument("--set", default=None, help="Question file. Default: data/eval_set_<workspace>.json, "
                        "falling back to data/eval_set.json")
    args = parser.parse_args()

    upgrade()
    db = SessionLocal()
    try:
        path = args.set or f"data/eval_set_{args.workspace}.json"
        if not args.set and not Path(path).exists():
            path = "data/eval_set.json"
        questions = evaluation.load_question_set(path)
        log.info("Scoring %d questions from %s in %s", len(questions), path, args.workspace)
        run = evaluation.run_evaluation(db, questions, args.workspace)
        log.info("faithfulness      %.2f", run.faithfulness)
        log.info("answer relevance  %.2f", run.answer_relevance)
        log.info("context relevance %.2f", run.context_relevance)
        if run.faithfulness < 0.80:
            log.warning("Faithfulness is below the 0.80 target set in NFR4.")
    finally:
        db.close()


if __name__ == "__main__":
    main()
