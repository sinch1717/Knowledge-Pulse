// One place where the interface talks to the outside world.
//
// If VITE_API_BASE_URL is empty the app serves mock data, so the frontend can be
// developed and demonstrated with no backend running. Once FastAPI is up, set the
// variable and every screen switches over. Nothing else in the app changes.

import {
  mockEvaluation,
  mockInsightDetail,
  mockInsights,
  mockOverview,
  mockReport,
  mockSources,
} from "@/mock/data";
import type {
  Citation,
  EvaluationRun,
  Insight,
  InsightDetail,
  Message,
  Overview,
  Report,
  Source,
} from "@/lib/types";

const BASE = import.meta.env.VITE_API_BASE_URL ?? "";
export const usingMockData = BASE === "";

const delay = (ms = 260) => new Promise((r) => setTimeout(r, ms));

async function get<T>(path: string, fallback: T): Promise<T> {
  if (usingMockData) {
    await delay();
    return fallback;
  }
  const res = await fetch(`${BASE}${path}`);
  if (!res.ok) {
    // The backend explains itself in `detail` — "No report yet, run the analytics
    // batch first" is far more useful to show than "404".
    const detail = await res
      .json()
      .then((b) => b?.detail)
      .catch(() => null);
    throw new Error(detail ?? `Request failed with status ${res.status}`);
  }
  return (await res.json()) as T;
}
export type OrgProfile = {
  name: string;
  description: string;
  industry: string;
  voice_description: string;
};
getOrgProfile: () =>
  get<OrgProfile>("/api/org-profile", {
    name: "KnowledgePulse",
    description: "Reads the support archive and ranks what customers are stuck on.",
    industry: "",
    voice_description: "Professional, concise, friendly and helpful.",
  }),

export const api = {
  getOverview: () => get<Overview>("/api/overview", mockOverview),

  getSources: () => get<Source[]>("/api/sources", mockSources),

  addSource: async (payload: { kind: "website" | "pdf" | "docx" | "text"; location: string }) => {
    if (usingMockData) {
      await delay(500);
      const created: Source = {
        id: `src_${Math.random().toString(36).slice(2, 7)}`,
        kind: payload.kind,
        label: payload.location.replace(/^https?:\/\//, "").split("/")[0],
        location: payload.location,
        status: "queued",
        pageCount: 0,
        chunkCount: 0,
        lastIndexedAt: null,
        contentHash: null,
      };
      return created;
    }
    const res = await fetch(`${BASE}/api/sources`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    if (!res.ok) throw new Error(await res.text());
    return (await res.json()) as Source;
  },

  getInsights: () => get<Insight[]>("/api/insights", mockInsights),

  getInsight: async (id: string) => {
    if (usingMockData) {
      await delay();
      const detail = mockInsightDetail[id];
      if (detail) return detail;
      // Synthesise a plausible detail view for the other mock insights.
      const base = mockInsights.find((i) => i.id === id);
      if (!base) throw new Error("No insight with that id");
      return {
        ...base,
        history: [
          { period: "Jun", queries: Math.round(base.previousQueryCount * 0.8), meanConfidence: base.meanConfidence + 0.06 },
          { period: "Jul", queries: base.previousQueryCount, meanConfidence: base.meanConfidence + 0.03 },
          { period: "Aug", queries: base.queryCount, meanConfidence: base.meanConfidence },
        ],
        memberQueries: base.sampleQueries.map((text, n) => ({
          id: `q_${id}_${n}`,
          text,
          confidence: base.meanConfidence,
          askedAt: "2026-08-21T10:00:00Z",
        })),
        weakestChunks: [] as Citation[],
      } satisfies InsightDetail;
    }
    return get<InsightDetail>(`/api/insights/${id}`, {} as InsightDetail);
  },

  getReport: () => get<Report>("/api/reports/latest", mockReport),

  getEvaluation: () => get<EvaluationRun>("/api/evaluation/latest", mockEvaluation),

  ask: async (question: string, sessionId: string): Promise<Message> => {
    if (usingMockData) {
      await delay(900);
      return {
        id: `msg_${Date.now()}`,
        role: "assistant",
        text: "Recurring invoices are generated on the schedule you set and sent to the client's registered email. If a charge did not go through, the invoice will still show as unpaid and you can send a reminder from the invoice page.\n\nI could not find anything in the indexed sources about mandate revocation or bank decline reasons, so this answer may not cover what you are asking.",
        createdAt: new Date().toISOString(),
        confidence: 0.28,
        citations: [
          {
            chunkId: "chk_00412",
            sourceLabel: "Kestrel documentation",
            headingPath: "Payments › Recurring invoices",
            similarity: 0.34,
            excerpt:
              "Recurring invoices are generated on the schedule you set and sent to the client's registered email address.",
          },
          {
            chunkId: "chk_00877",
            sourceLabel: "Kestrel onboarding handbook",
            headingPath: "Getting paid › Payment methods",
            similarity: 0.31,
            excerpt:
              "Clients can pay by card, net banking or UPI. Payment status appears on the invoice within a few minutes.",
          },
        ],
      };
    }
    const res = await fetch(`${BASE}/api/chat`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ question, session_id: sessionId }),
    });
    if (!res.ok) throw new Error(await res.text());
    return (await res.json()) as Message;
  },
};
