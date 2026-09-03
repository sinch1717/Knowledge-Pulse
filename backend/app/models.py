"""The seven entities from Section 7.2.4 of the project report, plus two join
and bookkeeping tables.

The chain that matters runs: message -> retrieved chunk ids -> chunk -> source.
Every finding downstream can be walked back along it, which is what makes
NFR5 (explainability) true rather than aspirational.
"""

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import Float, ForeignKey, Integer, JSON, String, Text, DateTime
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


def now() -> datetime:
    return datetime.now(timezone.utc)


class OrgProfile(Base):
    __tablename__ = "org_profile"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    name: Mapped[str] = mapped_column(String(200), default="KnowledgePulse")
    description: Mapped[str] = mapped_column(Text, default="")
    industry: Mapped[str] = mapped_column(String(200), default="")
    voice_description: Mapped[str] = mapped_column(
        Text,
        default="Professional, concise, friendly and helpful."
    )
class Source(Base):
    __tablename__ = "sources"

    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    kind: Mapped[str] = mapped_column(String(16))  # website | pdf | docx | text
    label: Mapped[str] = mapped_column(String(200))
    location: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(16), default="queued")
    page_count: Mapped[int] = mapped_column(Integer, default=0)
    chunk_count: Mapped[int] = mapped_column(Integer, default=0)
    last_indexed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    content_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)

    chunks: Mapped[list["Chunk"]] = relationship(back_populates="source", cascade="all, delete-orphan")


class Chunk(Base):
    __tablename__ = "chunks"

    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    source_id: Mapped[str] = mapped_column(ForeignKey("sources.id", ondelete="CASCADE"), index=True)
    heading_path: Mapped[str] = mapped_column(Text, default="")
    url: Mapped[str | None] = mapped_column(Text, nullable=True)
    text: Mapped[str] = mapped_column(Text)
    word_count: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)

    source: Mapped[Source] = relationship(back_populates="chunks")


class Conversation(Base):
    __tablename__ = "conversations"

    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    session_id: Mapped[str] = mapped_column(String(64), index=True)
    started_at: Mapped[datetime] = mapped_column(DateTime, default=now)
    # Set for generated traffic so the archive can always be audited or filtered.
    synthetic: Mapped[bool] = mapped_column(default=False)

    messages: Mapped[list["Message"]] = relationship(
        back_populates="conversation", cascade="all, delete-orphan"
    )


class Message(Base):
    __tablename__ = "messages"

    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    conversation_id: Mapped[str] = mapped_column(
        ForeignKey("conversations.id", ondelete="CASCADE"), index=True
    )
    role: Mapped[str] = mapped_column(String(12))  # customer | assistant
    text: Mapped[str] = mapped_column(Text)
    # Assistant turns only. Computed from retrieval similarity before generation.
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    retrieved_chunk_ids: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
    retrieved_scores: Mapped[list[float] | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now, index=True)
    # Reporting period this turn belongs to, e.g. "2026-08". Set on write so the
    # analytics batch never has to reason about calendars.
    period: Mapped[str] = mapped_column(String(16), index=True, default="")

    conversation: Mapped[Conversation] = relationship(back_populates="messages")


class TopicCluster(Base):
    __tablename__ = "topic_clusters"

    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    period: Mapped[str] = mapped_column(String(16), index=True)
    rank: Mapped[int] = mapped_column(Integer, default=0)
    name: Mapped[str] = mapped_column(Text)
    keywords: Mapped[list[str]] = mapped_column(JSON, default=list)
    query_count: Mapped[int] = mapped_column(Integer, default=0)
    previous_query_count: Mapped[int] = mapped_column(Integer, default=0)
    growth: Mapped[float] = mapped_column(Float, default=0.0)
    mean_confidence: Mapped[float] = mapped_column(Float, default=0.0)
    severity: Mapped[float] = mapped_column(Float, default=0.0)
    priority: Mapped[float] = mapped_column(Float, default=0.0)
    trend: Mapped[str] = mapped_column(String(16), default="stable")
    centroid: Mapped[list[float]] = mapped_column(JSON, default=list)
    previous_cluster_id: Mapped[str | None] = mapped_column(String(40), nullable=True)

    members: Mapped[list["ClusterMember"]] = relationship(
        back_populates="cluster", cascade="all, delete-orphan"
    )


class ClusterMember(Base):
    __tablename__ = "cluster_members"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    cluster_id: Mapped[str] = mapped_column(ForeignKey("topic_clusters.id", ondelete="CASCADE"), index=True)
    message_id: Mapped[str] = mapped_column(ForeignKey("messages.id", ondelete="CASCADE"))

    cluster: Mapped[TopicCluster] = relationship(back_populates="members")


class Report(Base):
    __tablename__ = "reports"

    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    period: Mapped[str] = mapped_column(String(16), index=True)
    generated_at: Mapped[datetime] = mapped_column(DateTime, default=now)
    conversation_count: Mapped[int] = mapped_column(Integer, default=0)
    query_count: Mapped[int] = mapped_column(Integer, default=0)
    unanswered_rate: Mapped[float] = mapped_column(Float, default=0.0)
    summary: Mapped[str] = mapped_column(Text, default="")

    recommendations: Mapped[list["Recommendation"]] = relationship(
        back_populates="report", cascade="all, delete-orphan"
    )


class Recommendation(Base):
    __tablename__ = "recommendations"

    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    report_id: Mapped[str] = mapped_column(ForeignKey("reports.id", ondelete="CASCADE"), index=True)
    cluster_id: Mapped[str] = mapped_column(String(40))
    cluster_name: Mapped[str] = mapped_column(Text)
    category: Mapped[str] = mapped_column(String(24))  # product|documentation|faq|customer_issue
    headline: Mapped[str] = mapped_column(Text)
    body: Mapped[str] = mapped_column(Text)
    faq_answer: Mapped[str | None] = mapped_column(Text, nullable=True)
    supporting_queries: Mapped[list[str]] = mapped_column(JSON, default=list)
    volume: Mapped[int] = mapped_column(Integer, default=0)
    growth: Mapped[float] = mapped_column(Float, default=0.0)
    expected_effect: Mapped[str] = mapped_column(Text, default="")

    report: Mapped[Report] = relationship(back_populates="recommendations")


class EvaluationRun(Base):
    __tablename__ = "evaluation_runs"

    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    ran_at: Mapped[datetime] = mapped_column(DateTime, default=now)
    question_count: Mapped[int] = mapped_column(Integer, default=0)
    faithfulness: Mapped[float] = mapped_column(Float, default=0.0)
    answer_relevance: Mapped[float] = mapped_column(Float, default=0.0)
    context_relevance: Mapped[float] = mapped_column(Float, default=0.0)
    failures: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
