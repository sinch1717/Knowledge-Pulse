import { Link } from "react-router-dom";
import { ArrowLeft } from "lucide-react";
import {
  Bar,
  CartesianGrid,
  Cell,
  ComposedChart,
  Line,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import type { Citation, InsightDetail, TrendPoint } from "@/lib/types";
import { axisTick, palette, tooltipStyle } from "@/lib/chart";
import { dateLabel, pct, WEAK_CONFIDENCE } from "@/lib/format";
import { Panel, SectionHeader } from "@/components/ui";

export function BackNavigation({ to, label }: { to: string; label: string }) {
  return (
    <Link to={to} className="mb-6 inline-flex items-center gap-1.5 text-small text-oxblood hover:underline hover:underline-offset-4">
      <ArrowLeft size={14} aria-hidden />
      {label}
    </Link>
  );
}

export function InsightHistoryChart({ history }: { history: TrendPoint[] }) {
  return (
    <Panel className="p-5">
      <SectionHeader
        title="Across periods"
        description="Bars show questions asked. The line shows how confidently the sources answered them."
      />
      <div className="h-60">
        <ResponsiveContainer width="100%" height="100%">
          <ComposedChart data={history} margin={{ top: 8, right: 0, bottom: 0, left: -18 }}>
            <CartesianGrid stroke={palette.rule} strokeDasharray="2 4" vertical={false} />
            <XAxis dataKey="period" tick={axisTick} axisLine={{ stroke: palette.rule }} tickLine={false} />
            <YAxis yAxisId="q" tick={axisTick} axisLine={false} tickLine={false} allowDecimals={false} />
            <YAxis
              yAxisId="c"
              orientation="right"
              domain={[0, 1]}
              ticks={[0, 0.5, 1]}
              tickFormatter={(v: number) => pct(v)}
              tick={axisTick}
              axisLine={false}
              tickLine={false}
            />
            <Tooltip
              cursor={{ fill: palette.paperSunk }}
              contentStyle={tooltipStyle}
              formatter={(v: number, name: string) =>
                name === "meanConfidence" ? [pct(v), "Mean confidence"] : [v, "Questions"]
              }
            />
            <Bar yAxisId="q" dataKey="queries" radius={[2, 2, 0, 0]} maxBarSize={56}>
              {history.map((_, n) => (
                <Cell key={n} fill={n === history.length - 1 ? palette.oxblood : palette.ruleStrong} />
              ))}
            </Bar>
            <Line
              yAxisId="c"
              type="monotone"
              dataKey="meanConfidence"
              stroke={palette.olive}
              strokeWidth={1.75}
              dot={{ r: 3, fill: palette.olive, strokeWidth: 0 }}
            />
          </ComposedChart>
        </ResponsiveContainer>
      </div>
    </Panel>
  );
}

export function CustomerQuestions({ questions }: { questions: InsightDetail["memberQueries"] }) {
  return (
    <section>
      <SectionHeader
        title="What customers asked"
        description="Verbatim, with the retrieval confidence the assistant managed on each."
      />
      <Panel>
        <ul>
          {questions.map((q) => (
            <li key={q.id} className="flex items-baseline gap-4 border-b border-rule px-4 py-3 last:border-b-0">
              <span
                className={`tabular w-12 shrink-0 font-mono text-small ${
                  q.confidence < WEAK_CONFIDENCE ? "text-oxblood" : "text-olive"
                }`}
              >
                {pct(q.confidence)}
              </span>
              <span className="min-w-0 flex-1 text-base">{q.text}</span>
              <time dateTime={q.askedAt} className="hidden shrink-0 text-micro text-ink-faint sm:block">
                {dateLabel(q.askedAt)}
              </time>
            </li>
          ))}
        </ul>
      </Panel>
    </section>
  );
}

export function EvidenceCard({ citation: c }: { citation: Citation }) {
  return (
    <Panel className="p-4">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <p className="text-small font-medium text-ink">{c.sourceLabel}</p>
        <span className="tabular font-mono text-micro text-ink-faint">similarity {c.similarity.toFixed(2)}</span>
      </div>
      <p className="mt-0.5 text-micro text-ink-faint">{c.headingPath}</p>
      <blockquote className="mt-3 border-l-2 border-rule-strong pl-3 text-small text-ink-soft">{c.excerpt}</blockquote>
    </Panel>
  );
}

export function WeakKnowledgeMatches({ chunks }: { chunks: Citation[] }) {
  return (
    <section>
      <SectionHeader
        title="Closest match in your sources"
        description="The passages retrieval kept returning. If they look unrelated to the questions, the answer is missing from the sources rather than badly worded."
      />
      <div className="grid gap-4 md:grid-cols-2">
        {chunks.map((c) => (
          <EvidenceCard key={c.chunkId} citation={c} />
        ))}
      </div>
    </section>
  );
}
