"""The scheduled job. Reads a period's conversations, writes topics and a report.

Runs start to finish in one function because that is what it is: a batch. Splitting
it across a queue would add moving parts without adding anything.

Idempotent. Re-running for a period deletes that period's clusters and report
first, so you can tune the weights and run it again without cleaning up by hand.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone

import numpy as np
from sqlalchemy import func
from sqlalchemy.orm import Session

from app import embeddings
from app.analytics import clustering, recommend, trends
from app.config import settings
from app.models import (
    ClusterMember,
    Conversation,
    Message,
    Recommendation,
    Report,
    TopicCluster,
)

log = logging.getLogger(__name__)


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


def previous_period(period: str) -> str:
    year, month = (int(p) for p in period.split("-"))
    return f"{year - 1}-12" if month == 1 else f"{year}-{month - 1:02d}"


def run_batch(db: Session, period: str, organization_id: str) -> Report | None:
    log.info("Analytics batch starting for %s (organization %s)", period, organization_id)

    questions = (
        db.query(Message)
        .filter(
            Message.role == "customer",
            Message.period == period,
            Message.organization_id == organization_id,
        )
        .order_by(Message.created_at)
        .all()
    )
    if len(questions) < settings.hdbscan_min_cluster_size * 2:
        log.warning(
            "Only %d questions in %s for org %s; nothing to analyse",
            len(questions),
            period,
            organization_id,
        )
        return None

    _clear_period(db, period, organization_id)

    texts = [q.text for q in questions]
    confidences = [q.confidence if q.confidence is not None else 0.0 for q in questions]

    log.info("Embedding %d questions", len(texts))
    vectors = embeddings.embed(texts)

    clusters = clustering.cluster_queries(texts, vectors, confidences)
    if not clusters:
        log.warning("No topics emerged for %s (organization %s)", period, organization_id)
        return None

    prior = (
        db.query(TopicCluster)
        .filter(
            TopicCluster.period == previous_period(period),
            TopicCluster.organization_id == organization_id,
        )
        .all()
    )
    max_volume = max(len(c.indices) for c in clusters)

    rows: list[TopicCluster] = []
    for cluster in clusters:
        matched, _ = trends.match_to_previous(cluster.centroid, prior)
        previous_count = matched.query_count if matched else 0
        count = len(cluster.indices)
        growth = trends.compute_growth(count, previous_count)

        row = TopicCluster(
            id=new_id("ins"),
            organization_id=organization_id,
            period=period,
            name=cluster.name,
            keywords=cluster.keywords,
            query_count=count,
            previous_query_count=previous_count,
            growth=growth,
            mean_confidence=cluster.mean_confidence,
            severity=cluster.severity,
            trend=trends.classify_trend(count, previous_count, growth),
            centroid=[float(x) for x in cluster.centroid],
            previous_cluster_id=matched.id if matched else None,
            priority=trends.priority_score(
                volume_norm=count / max_volume,
                growth=growth,
                mean_confidence=cluster.mean_confidence,
                severity=cluster.severity,
            ),
        )
        db.add(row)
        db.flush()
        for index in cluster.indices:
            db.add(
                ClusterMember(
                    organization_id=organization_id,
                    cluster_id=row.id,
                    message_id=questions[index].id,
                )
            )
        rows.append(row)

    rows.sort(key=lambda r: -r.priority)
    for position, row in enumerate(rows, start=1):
        row.rank = position
    db.commit()

    report = _build_report(db, period, rows, questions, organization_id)
    log.info(
        "Batch complete for %s (org %s): %d topics, %d recommendations",
        period,
        organization_id,
        len(rows),
        len(report.recommendations),
    )
    return report


def _clear_period(db: Session, period: str, organization_id: str) -> None:
    old_clusters = (
        db.query(TopicCluster)
        .filter(TopicCluster.period == period, TopicCluster.organization_id == organization_id)
        .all()
    )
    for cluster in old_clusters:
        db.delete(cluster)
    for old_report in (
        db.query(Report)
        .filter(Report.period == period, Report.organization_id == organization_id)
        .all()
    ):
        db.delete(old_report)
    db.commit()


def _build_report(
    db: Session,
    period: str,
    rows: list[TopicCluster],
    questions: list[Message],
    organization_id: str,
) -> Report:
    low = sum(1 for q in questions if (q.confidence or 0) < settings.low_confidence_threshold)
    unanswered_rate = round(low / len(questions), 4)

    conversation_count = (
        db.query(func.count(func.distinct(Message.conversation_id)))
        .filter(Message.period == period, Message.organization_id == organization_id)
        .scalar()
        or 0
    )

    report = Report(
        id=new_id("rep"),
        organization_id=organization_id,
        period=period,
        generated_at=datetime.now(timezone.utc),
        conversation_count=conversation_count,
        query_count=len(questions),
        unanswered_rate=unanswered_rate,
        summary=recommend.write_summary(period, rows, unanswered_rate),
    )
    db.add(report)
    db.flush()

    # Only the top of the ranked list becomes a recommendation. A report with
    # eighteen actions on it is a report nobody acts on.
    top = rows[:6]
    volumes = sorted(r.query_count for r in rows)
    median_volume = volumes[len(volumes) // 2] if volumes else 0

    for row in top:
        samples = _sample_questions(db, row.id, limit=8)
        category = recommend.choose_category(row, median_volume)
        db.add(
            recommend.write_recommendation(
                row, category, samples, report.id, organization_id=organization_id
            )
        )

    db.commit()
    db.refresh(report)
    return report


def _sample_questions(db: Session, cluster_id: str, limit: int = 5) -> list[str]:
    """Prefer the lowest-confidence questions: they show the failure most clearly."""
    result = (
        db.query(Message.text)
        .join(ClusterMember, ClusterMember.message_id == Message.id)
        .filter(ClusterMember.cluster_id == cluster_id)
        .order_by(Message.confidence.asc())
        .limit(limit)
        .all()
    )
    return [r[0] for r in result]


def latest_period(db: Session, organization_id: str | None = None) -> str | None:
    query = db.query(func.max(Message.period)).filter(Message.role == "customer")
    if organization_id:
        query = query.filter(Message.organization_id == organization_id)
    row = query.scalar()
    return row or None


def run_for_all_periods(db: Session, organization_id: str) -> list[Report]:
    """Used after seeding, when several months arrive at once. Order matters —
    each period needs the previous one already clustered to compute growth."""
    periods = [
        p[0]
        for p in db.query(Message.period)
        .filter(Message.role == "customer", Message.organization_id == organization_id)
        .distinct()
        .order_by(Message.period)
        if p[0]
    ]
    reports = []
    for period in periods:
        report = run_batch(db, period, organization_id=organization_id)
        if report:
            reports.append(report)
    return reports
