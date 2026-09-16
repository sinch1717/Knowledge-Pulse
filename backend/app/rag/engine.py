"""Retrieval, confidence, generation, logging.

The important sequencing decision is that confidence is computed *before* the
generator runs, from the similarity distribution of the retrieved chunks alone.
That is the whole point of F2. A language model will write a fluent, assured
paragraph whether or not it had anything to work from, so its own sense of
certainty tells you nothing about whether your corpus contained the answer.
Retrieval similarity does, and it stays a valid diagnostic months later when the
generated text is long forgotten.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app import embeddings, llm, vector_store
from app.config import settings
from app.models import Conversation, Message

log = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are a support assistant for one organisation. You answer only \
from the passages given to you.

Rules:
- If the passages contain the answer, give it plainly and briefly.
- If they only partly cover the question, answer the part you can and say clearly \
which part you could not find.
- If they do not cover it at all, say so directly. Do not guess, and do not fill the \
gap from general knowledge.
- Write the way a helpful colleague would. No preamble, no restating the question."""


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


def current_period(when: datetime | None = None) -> str:
    when = when or datetime.now(timezone.utc)
    return when.strftime("%Y-%m")


def compute_confidence(similarities: list[float]) -> float:
    """Blend the best match with the average of the rest.

    A single strong hit surrounded by noise is weaker evidence than several
    consistent hits, so neither the maximum nor the mean alone is right. The
    weighting is configurable; 0.6 on the top match is the default.
    """
    if not similarities:
        return 0.0
    top = max(similarities)
    mean = sum(similarities) / len(similarities)
    w = settings.confidence_top_weight
    return round(max(0.0, min(1.0, w * top + (1 - w) * mean)), 4)


def build_prompt(question: str, hits: list[dict]) -> str:
    passages = []
    for n, hit in enumerate(hits, start=1):
        meta = hit["meta"]
        passages.append(
            f"[{n}] Source: {meta.get('source_label', 'unknown')}\n"
            f"Section: {meta.get('heading_path', '')}\n"
            f"{hit['text']}"
        )
    joined = "\n\n".join(passages) if passages else "(no passages were found)"
    return f"Passages:\n\n{joined}\n\nQuestion: {question}"


def answer(
    db: Session,
    question: str,
    session_id: str,
    synthetic: bool = False,
    created_at: datetime | None = None,
) -> Message:
    """Answer one question and persist both turns. Returns the assistant message."""
    created_at = created_at or datetime.now(timezone.utc)
    period = current_period(created_at)

    conversation = (
        db.query(Conversation).filter(Conversation.session_id == session_id).one_or_none()
    )
    if conversation is None:
        conversation = Conversation(
            id=new_id("conv"), session_id=session_id, started_at=created_at, synthetic=synthetic
        )
        db.add(conversation)
        db.flush()

    # --- retrieve -------------------------------------------------------
    query_vector = embeddings.embed_one(question)
    hits = vector_store.search(query_vector, settings.retrieval_top_k)
    similarities = [h["similarity"] for h in hits]
    confidence = compute_confidence(similarities)

    # --- log the customer turn ------------------------------------------
    db.add(
        Message(
            id=new_id("msg"),
            conversation_id=conversation.id,
            role="customer",
            text=question,
            confidence=confidence,  # carried on the query too, so clustering can use it
            retrieved_chunk_ids=[h["chunk_id"] for h in hits],
            retrieved_scores=similarities,
            created_at=created_at,
            period=period,
        )
    )

    # --- generate --------------------------------------------------------
    if not hits:
        text = (
            "There is nothing indexed yet, so I have no sources to answer from. "
            "Add a knowledge source and try again."
        )
    else:
        try:
            text = llm.complete(build_prompt(question, hits), system=SYSTEM_PROMPT)
        except llm.LLMError as exc:
            # NFR3: degrade to returning what was retrieved rather than failing.
            log.warning("Generation unavailable, returning passages: %s", exc)
            text = (
                "The answer service is unavailable, so here is the closest material "
                "from the sources:\n\n" + "\n\n".join(h["text"][:400] for h in hits[:2])
            )

    assistant = Message(
        id=new_id("msg"),
        conversation_id=conversation.id,
        role="assistant",
        text=text,
        confidence=confidence,
        retrieved_chunk_ids=[h["chunk_id"] for h in hits],
        retrieved_scores=similarities,
        created_at=created_at,
        period=period,
    )
    db.add(assistant)
    db.commit()

    assistant.citations_payload = [  # type: ignore[attr-defined]
        {
            "chunkId": h["chunk_id"],
            "sourceLabel": h["meta"].get("source_label", "unknown"),
            "headingPath": h["meta"].get("heading_path", ""),
            "similarity": round(h["similarity"], 4),
            "excerpt": h["text"][:320],
        }
        for h in hits
    ]
    return assistant


def retrieve_only(question: str) -> tuple[list[dict], float]:
    """Used by the evaluation harness, which needs context without logging a turn."""
    hits = vector_store.search(embeddings.embed_one(question), settings.retrieval_top_k)
    return hits, compute_confidence([h["similarity"] for h in hits])
