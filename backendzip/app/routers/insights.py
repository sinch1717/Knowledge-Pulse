from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.analytics import batch
from app.config import settings
from app.db import SessionLocal, get_db
from app.models import (
    Chunk,
    ClusterMember,
    EvaluationRun,
    Message,
    Report,
    TopicCluster,
)
from app.schemas import (
    CitationOut,
    EvaluationOut,
    InsightDetailOut,
    InsightOut,
    MemberQueryOut,
    OverviewOut,
    RecommendationOut,
    ReportOut,
    TrendPointOut,
)

router = APIRouter(prefix="/api", tags=["insights"])


def _current_period(db: Session) -> str | None:
    return db.query(func.max(TopicCluster.period)).scalar()


def _samples(db: Session, cluster_id: str, limit: int) -> list[str]:
    rows = (
        db.query(Message.text)
        .join(ClusterMember, ClusterMember.message_id == Message.id)
        .filter(ClusterMember.cluster_id == cluster_id)
        .order_by(Message.confidence.asc())
        .limit(limit)
        .all()
    )
    return [r[0] for r in rows]


def _insight_out(db: Session, c: TopicCluster) -> InsightOut:
    return InsightOut(
        id=c.id,
        rank=c.rank,
        name=c.name,
        keywords=c.keywords or [],
        queryCount=c.query_count,
        previousQueryCount=c.previous_query_count,
        growth=c.growth,
        meanConfidence=c.mean_confidence,
        severity=c.severity,
        priority=c.priority,
        trend=c.trend,
        sampleQueries=_samples(db, c.id, 3),
    )


# --------------------------------------------------------------------------
# Overview
# --------------------------------------------------------------------------

@router.get("/overview", response_model=OverviewOut)
def overview(db: Session = Depends(get_db)):
    period = _current_period(db) or db.query(func.max(Message.period)).scalar() or ""
    clusters = db.query(TopicCluster).filter(TopicCluster.period == period).all()

    questions = db.query(Message).filter(Message.role == "customer", Message.period == period).all()
    low = sum(1 for q in questions if (q.confidence or 0) < settings.low_confidence_threshold)
    confidences = [q.confidence for q in questions if q.confidence is not None]

    periods = [
        p[0]
        for p in db.query(Message.period)
        .filter(Message.role == "customer", Message.period != "")
        .distinct()
        .order_by(Message.period)
        .all()
    ]
    volume = []
    for p in periods[-6:]:
        rows = db.query(Message).filter(Message.role == "customer", Message.period == p).all()
        scores = [r.confidence for r in rows if r.confidence is not None]
        volume.append(
            TrendPointOut(
                period=p,
                queries=len(rows),
                meanConfidence=round(sum(scores) / len(scores), 4) if scores else 0.0,
            )
        )

    conversations = (
        db.query(func.count(func.distinct(Message.conversation_id)))
        .filter(Message.period == period)
        .scalar()
        or 0
    )

    return OverviewOut(
        period=period or "No data yet",
        conversationCount=conversations,
        queryCount=len(questions),
        topicCount=len(clusters),
        unansweredRate=round(low / len(questions), 4) if questions else 0.0,
        meanConfidence=round(sum(confidences) / len(confidences), 4) if confidences else 0.0,
        emergingCount=sum(1 for c in clusters if c.trend == "emerging"),
        volumeByPeriod=volume,
    )


# --------------------------------------------------------------------------
# Insights
# --------------------------------------------------------------------------

@router.get("/insights", response_model=list[InsightOut])
def list_insights(period: str | None = None, db: Session = Depends(get_db)):
    period = period or _current_period(db)
    if not period:
        return []
    rows = (
        db.query(TopicCluster)
        .filter(TopicCluster.period == period)
        .order_by(TopicCluster.rank)
        .all()
    )
    return [_insight_out(db, c) for c in rows]


@router.get("/insights/{insight_id}", response_model=InsightDetailOut)
def get_insight(insight_id: str, db: Session = Depends(get_db)):
    cluster = db.get(TopicCluster, insight_id)
    if cluster is None:
        raise HTTPException(404, "No insight with that id")

    # Walk the chain of previous_cluster_id links backwards to build the history.
    history: list[TrendPointOut] = []
    node: TopicCluster | None = cluster
    seen: set[str] = set()
    while node is not None and node.id not in seen:
        seen.add(node.id)
        history.append(
            TrendPointOut(
                period=node.period, queries=node.query_count, meanConfidence=node.mean_confidence
            )
        )
        node = db.get(TopicCluster, node.previous_cluster_id) if node.previous_cluster_id else None
    history.reverse()

    members = (
        db.query(Message)
        .join(ClusterMember, ClusterMember.message_id == Message.id)
        .filter(ClusterMember.cluster_id == cluster.id)
        .order_by(Message.confidence.asc())
        .limit(25)
        .all()
    )

    # The passages retrieval kept returning for the worst-scoring questions.
    weakest: list[CitationOut] = []
    seen_chunks: set[str] = set()
    for message in members[:5]:
        for chunk_id, score in zip(message.retrieved_chunk_ids or [], message.retrieved_scores or []):
            if chunk_id in seen_chunks or len(weakest) >= 3:
                continue
            chunk = db.get(Chunk, chunk_id)
            if chunk is None:
                continue
            seen_chunks.add(chunk_id)
            weakest.append(
                CitationOut(
                    chunkId=chunk.id,
                    sourceLabel=chunk.source.label if chunk.source else "unknown",
                    headingPath=chunk.heading_path,
                    similarity=round(float(score), 4),
                    excerpt=chunk.text[:320],
                )
            )

    base = _insight_out(db, cluster)
    return InsightDetailOut(
        **base.model_dump(),
        history=history,
        memberQueries=[
            MemberQueryOut(
                id=m.id, text=m.text, confidence=m.confidence or 0.0, askedAt=m.created_at
            )
            for m in members
        ],
        weakestChunks=weakest,
    )


# --------------------------------------------------------------------------
# Reports
# --------------------------------------------------------------------------

def _report_out(report: Report) -> ReportOut:
    return ReportOut(
        id=report.id,
        period=report.period,
        generatedAt=report.generated_at,
        conversationCount=report.conversation_count,
        queryCount=report.query_count,
        unansweredRate=report.unanswered_rate,
        summary=report.summary,
        recommendations=[
            RecommendationOut(
                id=r.id,
                category=r.category,
                headline=r.headline,
                body=r.body,
                insightId=r.cluster_id,
                insightName=r.cluster_name,
                supportingQueries=r.supporting_queries or [],
                volume=r.volume,
                growth=r.growth,
                expectedEffect=r.expected_effect,
                faqAnswer=r.faq_answer,
            )
            for r in report.recommendations
        ],
    )


@router.get("/reports/latest", response_model=ReportOut)
def latest_report(db: Session = Depends(get_db)):
    report = db.query(Report).order_by(Report.period.desc()).first()
    if report is None:
        raise HTTPException(404, "No report yet. Run the analytics batch first.")
    return _report_out(report)


@router.get("/reports", response_model=list[ReportOut])
def list_reports(db: Session = Depends(get_db)):
    return [_report_out(r) for r in db.query(Report).order_by(Report.period.desc()).all()]


# --------------------------------------------------------------------------
# Batch trigger
# --------------------------------------------------------------------------

def _run_batch_task(period: str | None) -> None:
    db = SessionLocal()
    try:
        if period:
            batch.run_batch(db, period)
        else:
            batch.run_for_all_periods(db)
    finally:
        db.close()


@router.post("/analytics/run", status_code=202)
def trigger_batch(tasks: BackgroundTasks, period: str | None = None):
    """Kick off the analytics batch. Returns immediately; it takes minutes."""
    tasks.add_task(_run_batch_task, period)
    return {"status": "started", "period": period or "all periods"}


# --------------------------------------------------------------------------
# Evaluation
# --------------------------------------------------------------------------

@router.get("/evaluation/latest", response_model=EvaluationOut)
def latest_evaluation(db: Session = Depends(get_db)):
    run = db.query(EvaluationRun).order_by(EvaluationRun.ran_at.desc()).first()
    if run is None:
        raise HTTPException(404, "No evaluation run yet. Run scripts/run_evaluation.py.")
    return EvaluationOut(
        id=run.id,
        ranAt=run.ran_at,
        questionCount=run.question_count,
        faithfulness=run.faithfulness,
        answerRelevance=run.answer_relevance,
        contextRelevance=run.context_relevance,
        failures=run.failures or [],
    )
