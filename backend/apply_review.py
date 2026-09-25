"""Apply a review-decisions file to the matching data/research/<site>/questions.json.

Only sets "accepted" on the ids the review actually covered (here, a 30-question
sample per site); every other question is left exactly as it was, still null.
Writes a .bak alongside the original before touching it.

    python apply_review.py python_review.json data/research/python/questions.json
    python apply_review.py vue_review.json data/research/vue/questions.json
"""

from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path


def main() -> None:
    if len(sys.argv) != 3:
        raise SystemExit("usage: apply_review.py <review.json> <questions.json>")
    review_path, questions_path = Path(sys.argv[1]), Path(sys.argv[2])

    review = json.loads(review_path.read_text(encoding="utf-8"))
    questions = json.loads(questions_path.read_text(encoding="utf-8"))

    decisions = review["decisions"]
    applied = 0
    for q in questions:
        if q["id"] in decisions:
            q["accepted"] = decisions[q["id"]]["accepted"]
            applied += 1

    missing = set(decisions) - {q["id"] for q in questions}
    if missing:
        raise SystemExit(f"{questions_path} is missing ids the review expects: {sorted(missing)}")

    backup = questions_path.with_suffix(".json.bak")
    shutil.copy2(questions_path, backup)
    questions_path.write_text(json.dumps(questions, indent=2, ensure_ascii=False), encoding="utf-8")

    accepted = sum(1 for d in decisions.values() if d["accepted"])
    print(f"Applied {applied} decisions to {questions_path} (backup at {backup}).")
    print(f"{accepted}/{len(decisions)} accepted ({accepted / len(decisions):.1%}).")


if __name__ == "__main__":
    main()
