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
  mockPeriods,
  mockReport,
  mockReportHistory,
  mockSources,
} from "@/mock/data";
import type {
  BackendState,
  Citation,
  EvaluationRun,
  Insight,
  InsightDetail,
  Message,
  Overview,
  Report,
  ReportSummary,
  Source,
  SourceKind,
} from "@/lib/types";

const BASE = import.meta.env.VITE_API_BASE_URL ?? "";
export const usingMockData = BASE === "";

const delay = (ms = 260) => new Promise((r) => setTimeout(r, ms));

/** Turn a failed response into a readable message. FastAPI puts it in `detail`. */
async function failure(res: Response): Promise<Error> {
  const detail = await res
    .json()
    .then((b) => (typeof b?.detail === "string" ? b.detail : null))
    .catch(() => null);
  return new Error(detail ?? `Request failed with status ${res.status}`);
}

async function get<T>(path: string, fallback: T): Promise<T> {
  if (usingMockData) {
    await delay();
    return fallback;
  }
  const res = await fetch(`${BASE}${path}`);
  if (!res.ok) throw await failure(res);
  return (await res.json()) as T;
}

async function send<T>(method: "POST" | "DELETE", path: string, body?: unknown): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    method,
    headers: body instanceof FormData || body === undefined ? undefined : { "Content-Type": "application/json" },
    body: body instanceof FormData ? body : body === undefined ? undefined : JSON.stringify(body),
  });
  if (!res.ok) throw await failure(res);
  if (res.status === 204) return undefined as T;
  const text = await res.text();
  return (text ? JSON.parse(text) : undefined) as T;
}

const kindFromFilename = (name: string): SourceKind => {
  const ext = name.split(".").pop()?.toLowerCase();
  if (ext === "pdf") return "pdf";
  if (ext === "docx") return "docx";
  return "text";
};

export const api = {
  getOverview: () => get<Overview>("/api/overview", mockOverview),

  /** Reachability check for the Sources page. Never throws. */
  getHealth: async (): Promise<BackendState> => {
    if (usingMockData) return "mock";
    try {
      const res = await fetch(`${BASE}/api/health`);
      return res.ok ? "connected" : "unreachable";
    } catch {
      return "unreachable";
    }
  },

  // ---- sources -------------------------------------------------------------

  getSources: () => get<Source[]>("/api/sources", mockSources),

  addSource: async (payload: { kind: SourceKind; location: string; label?: string }) => {
    if (usingMockData) {
      await delay(500);
      const created: Source = {
        id: `src_${Math.random().toString(36).slice(2, 7)}`,
        kind: payload.kind,
        label: payload.label || payload.location.replace(/^https?:\/\//, "").split("/")[0],
        location: payload.location,
        status: "queued",
        pageCount: 0,
        chunkCount: 0,
        lastIndexedAt: null,
        contentHash: null,
      };
      return created;
    }
    return send<Source>("POST", "/api/sources", payload);
  },

  uploadSource: async (file: File, label?: string) => {
    if (usingMockData) {
      await delay(700);
      const created: Source = {
        id: `src_${Math.random().toString(36).slice(2, 7)}`,
        kind: kindFromFilename(file.name),
        label: label || file.name.replace(/\.[^.]+$/, ""),
        location: file.name,
        status: "indexing",
        pageCount: 0,
        chunkCount: 0,
        lastIndexedAt: null,
        contentHash: null,
      };
      return created;
    }
    const form = new FormData();
    form.append("file", file);
    if (label) form.append("label", label);
    return send<Source>("POST", "/api/sources/upload", form);
  },

  reindexSource: async (id: string) => {
    if (usingMockData) {
      await delay(400);
      return;
    }
    await send<unknown>("POST", `/api/sources/${id}/reindex`);
  },

  deleteSource: async (id: string) => {
    if (usingMockData) {
      await delay(400);
      return;
    }
    await send<unknown>("DELETE", `/api/sources/${id}`);
  },

  // ---- analytics -----------------------------------------------------------

  runAnalytics: async () => {
    if (usingMockData) {
      await delay(1200);
      return;
    }
    await send<unknown>("POST", "/api/analytics/run");
  },

  getPeriods: () => get<string[]>("/api/periods", mockPeriods),

  getInsights: (period?: string) =>
    get<Insight[]>(`/api/insights${period ? `?period=${encodeURIComponent(period)}` : ""}`, mockInsights),

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

  // ---- reports and evaluation ---------------------------------------------

  getReport: () => get<Report>("/api/reports/latest", mockReport),

  getReports: () => get<ReportSummary[]>("/api/reports", mockReportHistory),

  getEvaluation: () => get<EvaluationRun>("/api/evaluation/latest", mockEvaluation),

  // ---- chat ----------------------------------------------------------------

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
    return send<Message>("POST", "/api/chat", { question, session_id: sessionId });
  },
};
