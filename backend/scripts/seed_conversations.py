"""Generate a conversation archive.

The system mines conversations. A new system has none, and clustering needs a few
hundred before topics mean anything, plus at least three periods before growth is
measurable. So the archive is generated. The procedure is documented in
docs/DATA.md and the reasoning belongs in the paper, not hidden in a script.

Two things to be clear about. The questions are synthetic. Everything downstream
of them — retrieval, confidence scoring, clustering, ranking — is real, because
each generated question is replayed through the live chat endpoint rather than
written straight into the database. The confidence numbers in the log were
genuinely computed.

    python scripts/seed_conversations.py --questions 800
"""

from __future__ import annotations

import argparse
import json
import logging
import random
import sys
import uuid
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import llm  # noqa: E402
from app.db import SessionLocal, create_tables  # noqa: E402
from app.models import Chunk, Source  # noqa: E402
from app.rag import engine  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)-7s | %(message)s",
                    datefmt="%H:%M:%S")
log = logging.getLogger("seed")

TOPIC_PROMPT = """Here are the section headings from a company's documentation site:

{headings}

The company is: {label}

List 8 things their customers would realistically contact support about. Cover the
obvious ones, but include at least four that the headings above do NOT appear to
cover — real customers ask about things nobody documented.

Return a JSON object with a single key "topics".
The value of "topics" must be an array of objects with these keys:
  "topic": short phrase
  "covered": true if the headings above look like they explain it, false if not
  "severity": "blocking" if it stops the customer working, "annoying", or "curious"
"""

QUESTION_PROMPT = """Write {n} different support questions about this one topic:

Topic: {topic}
Company: {label}

Write them the way real customers type: short, lowercase, sometimes no question mark,
occasional typo, occasional missing context. Vary them properly — different words,
different angles, different levels of frustration.

Return a JSON object with a single key "questions".
The value of "questions" must be an array of strings.
"""


def load_corpus_headings(db, limit: int = 60) -> tuple[str, str]:
    source = db.query(Source).filter(Source.status == "ready").first()
    if source is None:
        raise SystemExit(
            "No indexed source found. Add and index a website first, then run this again."
        )
    headings = (
        db.query(Chunk.heading_path)
        .filter(Chunk.source_id == source.id)
        .distinct()
        .limit(limit)
        .all()
    )
    return source.label, "\n".join(f"- {h[0]}" for h in headings if h[0])


def build_topic_frame(label: str, headings: str) -> list[dict]:
    result = llm.complete_json(
        TOPIC_PROMPT.format(headings=headings, label=label),
        system="You know how support queues actually look. You are specific, never generic.",
        temperature=0.7,
        max_tokens=1500,
    )

    if isinstance(result, dict):
        topics = result.get("topics", [])
    else:
        topics = result

    if not isinstance(topics, list):
        raise SystemExit(f"Expected a list of topics, got {type(topics)}")
    log.info("Topic frame: %d topics, %d of them uncovered",
             len(topics), sum(1 for t in topics if not t.get("covered", True)))
    return topics


def allocate(topics: list[dict], total: int, periods: list[str]) -> dict:
    """Decide how many questions each topic gets in each period.

    Volumes follow a long tail, because real support traffic does. Three shapes are
    planted on purpose so the analytics has something to find:

      - one topic near zero in period 1 that spikes in period 3. This is the
        emerging concern. If the trend detector misses it, F4 is broken.
      - several uncovered topics with steady volume, which should read as
        recurring documentation gaps.
      - well-covered high-volume topics, which should become FAQ candidates.
    """
    random.seed(42)
    weights = [1.0 / (i + 1.4) ** 0.85 for i in range(len(topics))]
    random.shuffle(weights)
    total_weight = sum(weights)

    # The planted emerging topic: pick an uncovered, blocking one if there is one.
    candidates = [
        i for i, t in enumerate(topics)
        if not t.get("covered", True) and t.get("severity") == "blocking"
    ] or [len(topics) - 1]
    emerging_index = candidates[0]
    log.info("Planted emerging concern: %s", topics[emerging_index]["topic"])

    plan: dict = {p: {} for p in periods}
    per_period = total // len(periods)

    for index, topic in enumerate(topics):
        share = weights[index] / total_weight
        for position, period in enumerate(periods):
            if index == emerging_index:
                # Near zero, then a trickle, then a spike.
                count = [1, 4, max(12, int(per_period * 0.14))][min(position, 2)]
            else:
                drift = 1.0 + random.uniform(-0.18, 0.22)
                count = max(0, round(per_period * share * drift))
            if count:
                plan[period][index] = count

    return plan, emerging_index


def generate_questions(topic: str, label: str, n: int) -> list[str]:
    import time

    try:
        result = llm.complete_json(
            QUESTION_PROMPT.format(n=min(n, 5), topic=topic, label=label),
            system="You imitate real customer writing, including its messiness.",
            temperature=0.8,
            max_tokens=900,
        )

        time.sleep(4)

        if isinstance(result, dict):
            questions = result.get("questions", [])
        else:
            questions = result

        return [str(q) for q in questions if str(q).strip()] if isinstance(questions, list) else []

    except llm.LLMError as exc:
        log.warning("Generation failed for '%s': %s", topic, exc)
        time.sleep(4)
        return []


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--questions", type=int, default=800)
    parser.add_argument("--periods", type=int, default=3)
    parser.add_argument("--dry-run", action="store_true", help="Write the question set, do not replay it")
    args = parser.parse_args()

    create_tables()
    db = SessionLocal()
    try:
        label, headings = load_corpus_headings(db)
        log.info("Generating traffic for: %s", label)

        today = datetime.now(timezone.utc).replace(day=15, hour=10, minute=0, second=0, microsecond=0)
        periods = []
        for back in range(args.periods - 1, -1, -1):
            month = today.replace(day=15) - timedelta(days=30 * back)
            periods.append(month.strftime("%Y-%m"))
        log.info("Periods: %s", ", ".join(periods))

        topics = build_topic_frame(label, headings)
        plan, emerging_index = allocate(topics, args.questions, periods)

        # ---- generate ---------------------------------------------------
        pool: dict[int, list[str]] = {}
        needed = Counter()
        for period_plan in plan.values():
            for index, count in period_plan.items():
                needed[index] += count

        for index, count in needed.items():
            topic = topics[index]["topic"]
            questions: list[str] = []
            while len(questions) < count:
                fresh = generate_questions(topic, label, count - len(questions))
                if not fresh:
                    break
                questions.extend(fresh)
            pool[index] = questions
            log.info("  %-45s %d questions", topic[:45], len(questions))

        # ---- write the audit trail --------------------------------------
        out_dir = Path("data")
        out_dir.mkdir(exist_ok=True)
        audit = {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "source_label": label,
            "periods": periods,
            "emerging_topic": topics[emerging_index]["topic"],
            "topics": topics,
            "questions": {topics[i]["topic"]: qs for i, qs in pool.items()},
        }
        (out_dir / "seed_questions.json").write_text(json.dumps(audit, indent=2))
        log.info("Wrote data/seed_questions.json")

        if args.dry_run:
            log.info("Dry run; not replaying through the chat endpoint")
            return

        # ---- replay through the live pipeline ---------------------------
        # This is the part that matters. Each question goes through real
        # retrieval and real confidence scoring, so nothing in the archive is
        # fabricated except the wording of the question itself.
        cursors = {i: 0 for i in pool}
        replayed = 0
        for position, period in enumerate(periods):
            base = datetime.strptime(period + "-02", "%Y-%m-%d").replace(tzinfo=timezone.utc)
            for index, count in plan[period].items():
                available = pool.get(index, [])
                for _ in range(count):
                    if cursors[index] >= len(available):
                        break
                    question = available[cursors[index]]
                    cursors[index] += 1
                    when = base + timedelta(
                        days=random.randint(0, 25), hours=random.randint(8, 21),
                        minutes=random.randint(0, 59),
                    )
                    engine.answer(
                        db,
                        question,
                        session_id=f"seed_{uuid.uuid4().hex[:10]}",
                        synthetic=True,
                        created_at=when,
                    )
                    replayed += 1
                    if replayed % 25 == 0:
                        log.info("Replayed %d questions (%s)", replayed, period)
            log.info("Period %s done (%d/%d)", period, position + 1, len(periods))

        log.info("Seeded %d conversations. Next: python scripts/run_analytics.py", replayed)
    finally:
        db.close()


if __name__ == "__main__":
    main()
