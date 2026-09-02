"""Build the held-out evaluation set.

Fifty questions drawn from the indexed corpus, written so the answer is genuinely
present in the source material. These never enter the conversation log — they
exist only to score the assistant, and mixing them in would contaminate the
archive the analytics reads.

    python scripts/build_eval_set.py --count 50
"""

from __future__ import annotations

import argparse
import json
import logging
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import llm  # noqa: E402
from app.db import SessionLocal, create_tables  # noqa: E402
from app.models import Chunk  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)-7s | %(message)s",
                    datefmt="%H:%M:%S")
log = logging.getLogger("evalset")

PROMPT = """Passage:

{text}

Write two questions a customer would ask that this passage answers. Phrase them the
way a customer would, not the way the passage is written. Return a JSON array of
two strings."""


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--count", type=int, default=50)
    args = parser.parse_args()

    create_tables()
    db = SessionLocal()
    try:
        chunks = db.query(Chunk).filter(Chunk.word_count > 60).all()
        if not chunks:
            raise SystemExit("Nothing indexed. Add a source first.")

        random.seed(7)
        random.shuffle(chunks)

        questions: list[dict] = []
        for chunk in chunks:
            if len(questions) >= args.count:
                break
            try:
                pair = llm.complete_json(
                    PROMPT.format(text=chunk.text[:1200]),
                    system="You write natural customer questions, never exam questions.",
                    temperature=0.7,
                    max_tokens=200,
                )
            except llm.LLMError as exc:
                log.warning("Skipped a chunk: %s", exc)
                continue
            if isinstance(pair, list):
                for question in pair[:2]:
                    if len(questions) < args.count:
                        questions.append({
                            "question": str(question),
                            "source_chunk_id": chunk.id,
                            "heading_path": chunk.heading_path,
                        })
            if len(questions) % 10 == 0:
                log.info("%d/%d", len(questions), args.count)

        out = Path("data/eval_set.json")
        out.parent.mkdir(exist_ok=True)
        out.write_text(json.dumps(questions, indent=2))
        log.info("Wrote %d questions to %s", len(questions), out)
    finally:
        db.close()


if __name__ == "__main__":
    main()
