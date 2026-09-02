"""Reference-free evaluation of the assistant.

These are the three RAGAS metrics, implemented directly rather than by importing
the `ragas` package. The reason is dependency weight: ragas pulls in a large and
fast-moving LangChain tree, and this project needs three metric definitions, not a
framework. The definitions below follow the paper.

  Faithfulness      — of the claims in the answer, how many are supported by the
                      retrieved passages? Catches the model inventing things.
  Answer relevance  — does the answer address the question that was asked?
                      Catches fluent, on-topic, useless replies.
  Context relevance — of the retrieved passages, how much was actually needed?
                      Catches a retriever that returns five things to find one.

Reference-free means no human-written gold answers, which is the whole point: the
suite can be re-run after every change to the corpus or the chunker, at no cost
beyond the API calls.
"""

from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy.orm import Session

from app import llm
from app.models import EvaluationRun
from app.rag import engine

log = logging.getLogger(__name__)

JUDGE_SYSTEM = (
    "You are a strict evaluator. You return only a number between 0 and 1 with two "
    "decimal places, and nothing else. No explanation."
)


def _score(prompt: str) -> float:
    try:
        raw = llm.complete(prompt, system=JUDGE_SYSTEM, temperature=0.0, max_tokens=12)
        value = float("".join(ch for ch in raw if ch.isdigit() or ch == ".").strip(".") or 0)
        return max(0.0, min(1.0, value))
    except (llm.LLMError, ValueError) as exc:
        log.warning("Judge call failed: %s", exc)
        return 0.0


def faithfulness(answer: str, context: str) -> float:
    return _score(
        f"Passages:\n{context}\n\nAnswer:\n{answer}\n\n"
        "What proportion of the factual claims in the answer are supported by the passages? "
        "An answer that correctly says it could not find something scores 1.0."
    )


def answer_relevance(question: str, answer: str) -> float:
    return _score(
        f"Question:\n{question}\n\nAnswer:\n{answer}\n\n"
        "How directly does the answer address the question? Judge relevance only, "
        "not whether it is correct."
    )


def context_relevance(question: str, context: str) -> float:
    return _score(
        f"Question:\n{question}\n\nRetrieved passages:\n{context}\n\n"
        "What proportion of these passages is relevant to answering the question?"
    )


def load_question_set(path: str) -> list[str]:
    file = Path(path)
    if not file.exists():
        raise FileNotFoundError(
            f"No evaluation set at {path}. Create it with scripts/build_eval_set.py."
        )
    payload = json.loads(file.read_text())
    return [item["question"] if isinstance(item, dict) else str(item) for item in payload]


def run_evaluation(db: Session, questions: list[str]) -> EvaluationRun:
    scores = {"faithfulness": [], "answer_relevance": [], "context_relevance": []}
    failures: list[dict] = []

    for n, question in enumerate(questions, start=1):
        hits, _ = engine.retrieve_only(question)
        context = "\n\n".join(h["text"] for h in hits) or "(nothing retrieved)"
        try:
            answer = llm.complete(engine.build_prompt(question, hits), system=engine.SYSTEM_PROMPT)
        except llm.LLMError as exc:
            log.warning("Skipping %s: %s", question[:50], exc)
            continue

        row = {
            "faithfulness": faithfulness(answer, context),
            "answer_relevance": answer_relevance(question, answer),
            "context_relevance": context_relevance(question, context),
        }
        for metric, value in row.items():
            scores[metric].append(value)
            if value < 0.5:
                failures.append({"question": question, "metric": metric, "score": round(value, 2)})

        if n % 10 == 0:
            log.info("Evaluated %d/%d", n, len(questions))

    def mean(values: list[float]) -> float:
        return round(sum(values) / len(values), 4) if values else 0.0

    failures.sort(key=lambda f: f["score"])

    run = EvaluationRun(
        id=f"eval_{uuid.uuid4().hex[:10]}",
        ran_at=datetime.now(timezone.utc),
        question_count=len(scores["faithfulness"]),
        faithfulness=mean(scores["faithfulness"]),
        answer_relevance=mean(scores["answer_relevance"]),
        context_relevance=mean(scores["context_relevance"]),
        failures=failures[:12],
    )
    db.add(run)
    db.commit()
    return run
