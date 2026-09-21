// These mirror the seven entities in the report's data model (Section 7.2.4).
// Keep them in sync with the Pydantic schemas once the backend lands.

export type SourceKind = "website" | "pdf" | "docx" | "text";
export type SourceStatus = "queued" | "crawling" | "indexing" | "ready" | "failed";

export interface Source {
  id: string;
  kind: SourceKind;
  label: string;
  location: string; // URL or original filename
  status: SourceStatus;
  pageCount: number;
  chunkCount: number;
  lastIndexedAt: string | null;
  contentHash: string | null;
  error?: string;
}

export interface Citation {
  chunkId: string;
  sourceLabel: string;
  headingPath: string;
  similarity: number;
  excerpt: string;
}

export interface Message {
  id: string;
  role: "customer" | "assistant";
  text: string;
  createdAt: string;
  confidence?: number; // retrieval confidence, assistant turns only
  citations?: Citation[];
}

export type TrendState = "recurring" | "emerging" | "stable";

export interface Insight {
  id: string;
  rank: number;
  name: string;
  keywords: string[];
  queryCount: number;
  previousQueryCount: number;
  growth: number; // -1..n, period over period
  meanConfidence: number; // 0..1
  severity: number; // 0..1, inferred
  priority: number; // 0..1, weighted composite
  trend: TrendState;
  sampleQueries: string[];
}

export interface TrendPoint {
  period: string;
  queries: number;
  meanConfidence: number;
}

export interface InsightDetail extends Insight {
  history: TrendPoint[];
  memberQueries: { id: string; text: string; confidence: number; askedAt: string }[];
  weakestChunks: Citation[];
}

export type ActionCategory = "product" | "documentation" | "faq" | "customer_issue";

export interface Recommendation {
  id: string;
  category: ActionCategory;
  headline: string;
  body: string;
  insightId: string;
  insightName: string;
  supportingQueries: string[];
  volume: number;
  growth: number;
  expectedEffect: string;
  faqAnswer?: string; // FAQ recommendations carry a draft answer
}

export interface Report {
  id: string;
  period: string;
  generatedAt: string;
  conversationCount: number;
  queryCount: number;
  unansweredRate: number;
  summary: string;
  recommendations: Recommendation[];
}

export interface EvaluationRun {
  id: string;
  ranAt: string;
  questionCount: number;
  faithfulness: number;
  answerRelevance: number;
  contextRelevance: number;
  failures: { question: string; metric: string; score: number }[];
}

export interface Overview {
  period: string;
  conversationCount: number;
  queryCount: number;
  topicCount: number;
  unansweredRate: number;
  meanConfidence: number;
  emergingCount: number;
  volumeByPeriod: TrendPoint[];
}
