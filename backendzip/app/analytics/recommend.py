"""Turning a ranked list into things someone can actually do on Monday.

Category assignment is rule-based, and deliberately so. The rules encode a single
piece of reasoning: what the combination of volume and retrieval confidence tells
you about *where* the problem lives.

  Low confidence  → retrieval found nothing close. The corpus is missing this.
                    That is a documentation problem.
  High confidence, high volume, still asked constantly → the docs cover it and
                    people keep asking anyway. Either it is buried, in which case
                    it belongs in the FAQ, or the product itself is confusing.
  Unresolved individual conversations → a person, not a pattern. Reply to them.

The prose for each recommendation is written by the model, but what category it
lands in is decided by the rules, so a reviewer can always ask why and get an
answer that does not begin "the model decided".
"""

from __future__ import annotations

import logging
import uuid

from app import llm
from app.config import settings
from app.models import Recommendation, TopicCluster

log = logging.getLogger(__name__)

CATEGORY_BRIEF = {
    "documentation": (
        "Retrieval keeps failing on this topic, which means the source material does not "
        "cover it. Name the page or section to write or correct, and say what it must explain."
    ),
    "product": (
        "The documentation covers this adequately and customers are still confused, so the "
        "difficulty is in the product rather than in its explanation. Say what to change."
    ),
    "faq": (
        "High volume, answered well, asked in almost the same words every time. It belongs in "
        "the FAQ. Write the question as customers phrase it."
    ),
    "customer_issue": (
        "Individual conversations that ended without a usable answer and did not come back. "
        "Say what these people need and why they are worth a direct reply."
    ),
}


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


def choose_category(cluster: TopicCluster, median_volume: float) -> str:
    low_confidence = cluster.mean_confidence < settings.low_confidence_threshold

    if low_confidence and cluster.severity >= 0.65 and cluster.trend == "emerging":
        # Nothing in the corpus and it is blocking people and it is growing.
        # Writing a page will not fix a product that gives no feedback.
        return "product"
    if low_confidence:
        return "documentation"
    if cluster.query_count >= median_volume and cluster.severity < 0.5:
        return "faq"
    if cluster.severity >= 0.6 and cluster.query_count <= max(6, median_volume * 0.4):
        return "customer_issue"
    return "product" if cluster.severity >= 0.55 else "faq"


def write_recommendation(
    cluster: TopicCluster, category: str, samples: list[str], report_id: str
) -> Recommendation:
    brief = CATEGORY_BRIEF[category]
    prompt = f"""Topic: {cluster.name}
Questions asked: {cluster.query_count} this period, {cluster.previous_query_count} last period
Retrieval confidence: {cluster.mean_confidence:.2f} out of 1.0
Trend: {cluster.trend}

What customers actually said:
{chr(10).join('- ' + s for s in samples[:8])}

{brief}

Return JSON with exactly these keys:
  "headline": one imperative sentence, under twelve words
  "body": two to four sentences of plain explanation, no jargon, addressed to whoever owns the product
  "expected_effect": one sentence on what changes if they do it
{'  "faq_answer": the answer to publish, two to four sentences' if category == 'faq' else ''}"""

    defaults = {
        "headline": f"Look into: {cluster.name}",
        "body": (
            f"{cluster.query_count} customers asked about this. Mean retrieval confidence was "
            f"{cluster.mean_confidence:.2f}, and the trend is {cluster.trend}."
        ),
        "expected_effect": "Reduces repeat questions on this topic.",
        "faq_answer": None,
    }

    try:
        result = llm.complete_json(
            prompt,
            system=(
                "You advise a small product team. You write plainly, name specific actions, "
                "and never pad. You are given real customer questions; stay grounded in them."
            ),
            temperature=0.4,
            max_tokens=500,
        )
        if not isinstance(result, dict):
            raise llm.LLMError("expected an object")
    except llm.LLMError as exc:
        log.warning("Falling back to templated recommendation for %s: %s", cluster.name, exc)
        result = {}

    merged = {**defaults, **{k: v for k, v in result.items() if v}}

    return Recommendation(
        id=new_id("rec"),
        report_id=report_id,
        cluster_id=cluster.id,
        cluster_name=cluster.name,
        category=category,
        headline=str(merged["headline"])[:300],
        body=str(merged["body"]),
        expected_effect=str(merged["expected_effect"]),
        faq_answer=str(merged["faq_answer"]) if category == "faq" and merged.get("faq_answer") else None,
        supporting_queries=samples[:5],
        volume=cluster.query_count,
        growth=cluster.growth,
    )


def write_summary(period: str, clusters: list[TopicCluster], unanswered_rate: float) -> str:
    """The paragraph at the top of the report. The only place prose is allowed to roam."""
    lines = [
        f"- {c.name}: {c.query_count} questions ({c.previous_query_count} last period), "
        f"confidence {c.mean_confidence:.2f}, {c.trend}"
        for c in clusters[:8]
    ]
    prompt = (
        f"Reporting period: {period}\n"
        f"Share of questions answered poorly: {unanswered_rate:.0%}\n\n"
        f"Top topics by priority:\n" + "\n".join(lines) + "\n\n"
        "Write three or four sentences for the top of a monthly report, addressed to the person "
        "who runs this product. Lead with whatever actually changed this period. Mention which "
        "problems are long-running. Do not list every topic and do not use bullet points."
    )
    try:
        return llm.complete(
            prompt,
            system="You write short, direct summaries for busy non-technical readers.",
            temperature=0.4,
            max_tokens=350,
        )
    except llm.LLMError as exc:
        log.warning("Summary unavailable: %s", exc)
        emerging = [c.name for c in clusters if c.trend == "emerging"][:3]
        parts = [f"{len(clusters)} topics were identified in {period}, and {unanswered_rate:.0%} of "
                 f"questions were answered with low retrieval confidence."]
        if emerging:
            parts.append("Newly rising: " + "; ".join(emerging) + ".")
        return " ".join(parts)
