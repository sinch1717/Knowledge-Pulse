"""Response shapes. These are the contract with the frontend.

Field names are camelCase because that is what src/lib/types.ts expects; the
aliasing happens here rather than making the frontend translate.
"""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict


class Base(BaseModel):
    model_config = ConfigDict(populate_by_name=True)


class CitationOut(Base):
    chunkId: str
    sourceLabel: str
    headingPath: str
    similarity: float
    excerpt: str


class SourceOut(Base):
    id: str
    kind: str
    label: str
    location: str
    status: str
    pageCount: int
    chunkCount: int
    lastIndexedAt: datetime | None
    contentHash: str | None
    error: str | None = None


class SourceCreate(Base):
    kind: Literal["website", "pdf", "docx", "text"] = "website"
    location: str
    label: str | None = None


class ChatRequest(Base):
    question: str
    session_id: str


class MessageOut(Base):
    id: str
    role: str
    text: str
    createdAt: datetime
    confidence: float | None = None
    citations: list[CitationOut] = []


class InsightOut(Base):
    id: str
    rank: int
    name: str
    keywords: list[str]
    queryCount: int
    previousQueryCount: int
    growth: float
    meanConfidence: float
    severity: float
    priority: float
    trend: str
    sampleQueries: list[str]


class TrendPointOut(Base):
    period: str
    queries: int
    meanConfidence: float


class MemberQueryOut(Base):
    id: str
    text: str
    confidence: float
    askedAt: datetime


class InsightDetailOut(InsightOut):
    history: list[TrendPointOut]
    memberQueries: list[MemberQueryOut]
    weakestChunks: list[CitationOut]


class RecommendationOut(Base):
    id: str
    category: str
    headline: str
    body: str
    insightId: str
    insightName: str
    supportingQueries: list[str]
    volume: int
    growth: float
    expectedEffect: str
    faqAnswer: str | None = None


class ReportOut(Base):
    id: str
    period: str
    generatedAt: datetime
    conversationCount: int
    queryCount: int
    unansweredRate: float
    summary: str
    recommendations: list[RecommendationOut]


class EvaluationOut(Base):
    id: str
    ranAt: datetime
    questionCount: int
    faithfulness: float
    answerRelevance: float
    contextRelevance: float
    failures: list[dict]


class OverviewOut(Base):
    period: str
    conversationCount: int
    queryCount: int
    topicCount: int
    unansweredRate: float
    meanConfidence: float
    emergingCount: int
    volumeByPeriod: list[TrendPointOut]
