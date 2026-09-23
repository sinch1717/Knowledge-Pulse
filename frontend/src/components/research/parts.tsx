import { useMemo, useState } from "react";
import clsx from "clsx";
import { Bar, BarChart, CartesianGrid, Legend, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import type { ResearchResult, ResearchSummary } from "@/lib/types";
import { axisTick, palette, tooltipStyle } from "@/lib/chart";
import { dateLabel, pct } from "@/lib/format";
import { Panel, SectionHeader } from "@/components/ui";

export const chunkerCopy: Record<string, { label: string; note: string; colour: string }> = {
  fixed: { label: "Fixed window", note: "Word windows with overlap, ignoring structure", colour: palette.inkFaint },
  recursive: { label: "Recursive", note: "Whole paragraphs, then sentences, up to the size", colour: palette.ochre },
  heading: { label: "Heading-aware", note: "Cut at headings; window only long sections", colour: palette.olive },
  heading_ctx: { label: "Heading + path", note: "Heading-aware, with the heading path embedded", colour: palette.oxblood },
};

const label = (chunker: string) => chunkerCopy[chunker]?.label ?? chunker;
const num = (v: number | null | undefined, digits = 3) => (v == null ? "–" : v.toFixed(digits));
const share = (v: number | null | undefined) => (v == null ? "–" : pct(v, 1));

// ---------------------------------------------------------------------------

export function RunMeta({ run }: { run: ResearchSummary }) {
  return (
    <div className="flex flex-wrap gap-x-5 gap-y-1 text-small text-ink-soft">
      <span>Run {dateLabel(run.created_at)}</span>
      <span>Embedding model {run.embedding_model.split("/").pop()}</span>
      <span>Top {run.k} retrieved</span>
      <span>Gap threshold {run.tau}</span>
      <span>Overlap {run.overlap} words</span>
    </div>
  );
}

export function SitesTable({ run }: { run: ResearchSummary }) {
  return (
    <section>
      <SectionHeader
        title="Documentation sites"
        description="Each site was crawled once and frozen, so every chunker read identical pages."
      />
      <Panel className="overflow-x-auto">
        <table className="w-full min-w-[44rem] text-left">
          <thead>
            <tr className="border-b border-rule-strong text-micro text-ink-faint">
              <th className="px-4 py-3 font-medium">Site</th>
              <th className="px-4 py-3 font-medium">Built with</th>
              <th className="px-4 py-3 text-right font-medium">Pages</th>
              <th className="px-4 py-3 text-right font-medium">Words</th>
              <th className="px-4 py-3 font-medium">Crawled</th>
              <th className="px-4 py-3 text-right font-medium">Questions</th>
              <th className="px-4 py-3 text-right font-medium">Accepted on review</th>
            </tr>
          </thead>
          <tbody>
            {run.sites.map((s) => (
              <tr key={s.site} className="border-b border-rule text-small last:border-b-0">
                <td className="px-4 py-3 font-medium">{s.name}</td>
                <td className="px-4 py-3 text-ink-soft">{s.generator}</td>
                <td className="tabular px-4 py-3 text-right">{s.pages}</td>
                <td className="tabular px-4 py-3 text-right">{s.words.toLocaleString()}</td>
                <td className="px-4 py-3 text-ink-soft">{s.crawled_at ? dateLabel(s.crawled_at) : "–"}</td>
                <td className="tabular px-4 py-3 text-right">{s.questions}</td>
                <td className="tabular px-4 py-3 text-right">
                  {s.review.reviewed
                    ? `${s.review.accepted_of_reviewed} of ${s.review.reviewed} (${pct(s.review.acceptance_rate ?? 0)})`
                    : "Not reviewed"}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </Panel>
    </section>
  );
}

// ---------------------------------------------------------------------------

type ChartMetric = "mrr" | "recallk" | "hitk" | "auroc";

export function ComparisonChart({ results, k }: { results: ResearchResult[]; k: number }) {
  const [metric, setMetric] = useState<ChartMetric>("mrr");
  const metrics: { key: ChartMetric; label: string }[] = [
    { key: "mrr", label: "MRR" },
    { key: "recallk", label: `Recall@${k}` },
    { key: "hitk", label: `Hit@${k}` },
    { key: "auroc", label: "Gap AUROC" },
  ];
  const chunkers = [...new Set(results.map((r) => r.chunker))];
  const data = useMemo(() => {
    const sites = [...new Set(results.map((r) => r.site))];
    return sites.map((site) => {
      const row: Record<string, string | number | null> = { site };
      for (const r of results.filter((x) => x.site === site)) row[r.chunker] = r.retrieval[metric];
      return row;
    });
  }, [results, metric]);

  return (
    <Panel className="p-5">
      <SectionHeader
        title="Chunkers side by side"
        description={
          metric === "auroc"
            ? "How well retrieval confidence separates answerable from unanswerable questions. 0.5 is chance."
            : "Retrieval quality on questions the site's documentation answers."
        }
        action={
          <div role="tablist" className="flex gap-1 rounded border border-rule-strong bg-paper p-1">
            {metrics.map((m) => (
              <button
                key={m.key}
                role="tab"
                aria-selected={metric === m.key}
                onClick={() => setMetric(m.key)}
                className={clsx(
                  "rounded px-2.5 py-1 text-small transition-colors",
                  metric === m.key ? "bg-paper-raised font-medium text-ink shadow-sm" : "text-ink-soft hover:text-ink",
                )}
              >
                {m.label}
              </button>
            ))}
          </div>
        }
      />
      <div className="h-72">
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={data} margin={{ top: 8, right: 8, bottom: 0, left: -12 }} barCategoryGap="22%">
            <CartesianGrid stroke={palette.rule} strokeDasharray="2 4" vertical={false} />
            <XAxis dataKey="site" tick={axisTick} axisLine={{ stroke: palette.rule }} tickLine={false} />
            <YAxis domain={[0, 1]} ticks={[0, 0.25, 0.5, 0.75, 1]} tick={axisTick} axisLine={false} tickLine={false} />
            <Tooltip
              cursor={{ fill: palette.paperSunk }}
              contentStyle={tooltipStyle}
              formatter={(v: number, name: string) => [v == null ? "–" : v.toFixed(3), label(name)]}
            />
            <Legend formatter={(v: string) => <span className="text-small text-ink-soft">{label(v)}</span>} />
            {chunkers.map((c) => (
              <Bar key={c} dataKey={c} fill={chunkerCopy[c]?.colour ?? palette.ruleStrong} radius={[2, 2, 0, 0]} maxBarSize={36} />
            ))}
          </BarChart>
        </ResponsiveContainer>
      </div>
    </Panel>
  );
}

// ---------------------------------------------------------------------------

interface Column {
  key: string;
  label: string;
  value: (r: ResearchResult) => number | null;
  show: (v: number | null) => string;
  better?: "high" | "low";
}

/** One table per site, with the best value in each column marked. */
export function MetricTable({
  title,
  description,
  results,
  columns,
}: {
  title: string;
  description: string;
  results: ResearchResult[];
  columns: Column[];
}) {
  const sites = [...new Set(results.map((r) => r.site))];
  return (
    <section>
      <SectionHeader title={title} description={description} />
      <Panel className="overflow-x-auto">
        <table className="w-full min-w-[46rem] text-left">
          <thead>
            <tr className="border-b border-rule-strong text-micro text-ink-faint">
              <th className="px-4 py-3 font-medium">Site</th>
              <th className="px-4 py-3 font-medium">Chunker</th>
              {columns.map((c) => (
                <th key={c.key} className="px-4 py-3 text-right font-medium">
                  {c.label}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {sites.map((site) => {
              const rows = results.filter((r) => r.site === site);
              const best = Object.fromEntries(
                columns.map((c) => {
                  const vals = rows.map(c.value).filter((v): v is number => v != null);
                  // No winner to mark when every row has the same value.
                  if (!c.better || !vals.length || new Set(vals).size === 1) return [c.key, null];
                  return [c.key, c.better === "high" ? Math.max(...vals) : Math.min(...vals)];
                }),
              );
              return rows.map((r, n) => (
                <tr
                  key={r.config + r.site}
                  className={clsx("text-small", n === rows.length - 1 ? "border-b border-rule-strong last:border-b-0" : "border-b border-rule")}
                >
                  <td className="px-4 py-2.5 font-medium">{n === 0 ? site : ""}</td>
                  <td className="px-4 py-2.5">
                    <span className="inline-flex items-center gap-2">
                      <span aria-hidden className="h-2.5 w-2.5 rounded-sm" style={{ background: chunkerCopy[r.chunker]?.colour }} />
                      {label(r.chunker)}
                      <span className="text-micro text-ink-faint">{r.size}w</span>
                    </span>
                  </td>
                  {columns.map((c) => {
                    const v = c.value(r);
                    const isBest = v != null && best[c.key] === v && rows.length > 1;
                    return (
                      <td
                        key={c.key}
                        className={clsx("tabular px-4 py-2.5 text-right", isBest ? "font-semibold text-oxblood" : "text-ink")}
                      >
                        {c.show(v)}
                      </td>
                    );
                  })}
                </tr>
              ));
            })}
          </tbody>
        </table>
      </Panel>
    </section>
  );
}

export const retrievalColumns = (k: number): Column[] => [
  { key: "chunks", label: "Chunks", value: (r) => r.chunk_stats.chunks, show: (v) => (v == null ? "–" : v.toLocaleString()) },
  { key: "hit1", label: "Hit@1", value: (r) => r.retrieval.hit1, show: (v) => num(v), better: "high" },
  { key: "hitk", label: `Hit@${k}`, value: (r) => r.retrieval.hitk, show: (v) => num(v), better: "high" },
  { key: "mrr", label: "MRR", value: (r) => r.retrieval.mrr, show: (v) => num(v), better: "high" },
  { key: "recallk", label: `Recall@${k}`, value: (r) => r.retrieval.recallk, show: (v) => num(v), better: "high" },
  { key: "page", label: `Page hit@${k}`, value: (r) => r.retrieval.page_hitk, show: (v) => num(v), better: "high" },
  { key: "ctx", label: "Context words", value: (r) => r.retrieval.context_words, show: (v) => (v == null ? "–" : v.toFixed(0)), better: "low" },
];

export const gapColumns: Column[] = [
  { key: "ca", label: "Conf. answerable", value: (r) => r.retrieval.mean_conf_answerable, show: (v) => num(v) },
  { key: "cu", label: "Conf. unanswerable", value: (r) => r.retrieval.mean_conf_unanswerable, show: (v) => num(v) },
  { key: "auroc", label: "AUROC", value: (r) => r.retrieval.auroc, show: (v) => num(v), better: "high" },
  { key: "fg", label: "False gaps", value: (r) => r.retrieval.false_gap, show: share, better: "low" },
  { key: "mg", label: "Missed gaps", value: (r) => r.retrieval.missed_gap, show: share, better: "low" },
  { key: "tau", label: "Best τ", value: (r) => r.retrieval.best_tau, show: (v) => num(v, 2) },
];

export const qualityColumns: Column[] = [
  { key: "mean", label: "Mean words", value: (r) => r.chunk_stats.words.mean, show: (v) => (v == null ? "–" : v.toFixed(0)) },
  { key: "p10", label: "P10 words", value: (r) => r.chunk_stats.words.p10, show: (v) => (v == null ? "–" : v.toFixed(0)) },
  { key: "p90", label: "P90 words", value: (r) => r.chunk_stats.words.p90, show: (v) => (v == null ? "–" : v.toFixed(0)) },
  { key: "tiny", label: "Tiny (<50 words)", value: (r) => r.chunk_stats.tiny_rate, show: share, better: "low" },
  { key: "cross", label: "Cross-section", value: (r) => r.chunk_stats.cross_section_rate, show: share, better: "low" },
  { key: "code", label: "Code blocks split", value: (r) => r.chunk_stats.code_split_rate, show: share, better: "low" },
];

// ---------------------------------------------------------------------------

export function SignificanceTable({ run }: { run: ResearchSummary }) {
  if (!run.comparisons.length) return null;
  return (
    <section>
      <SectionHeader
        title="Is the difference real?"
        description="Paired bootstrap over the same questions, 2000 resamples. A difference counts when its 95% interval excludes zero."
      />
      <Panel className="overflow-x-auto">
        <table className="w-full min-w-[40rem] text-left">
          <thead>
            <tr className="border-b border-rule-strong text-micro text-ink-faint">
              <th className="px-4 py-3 font-medium">Site</th>
              <th className="px-4 py-3 font-medium">Compared with heading-aware</th>
              <th className="px-4 py-3 font-medium">Metric</th>
              <th className="px-4 py-3 text-right font-medium">Difference</th>
              <th className="px-4 py-3 text-right font-medium">95% interval</th>
              <th className="px-4 py-3 font-medium">Verdict</th>
            </tr>
          </thead>
          <tbody>
            {run.comparisons.map((c, n) => (
              <tr key={n} className="border-b border-rule text-small last:border-b-0">
                <td className="px-4 py-2.5">{c.site}</td>
                <td className="px-4 py-2.5">{label(c.config.split("@")[0])} <span className="text-micro text-ink-faint">{c.config.split("@")[1]}w</span></td>
                <td className="px-4 py-2.5">{c.metric}</td>
                <td className={clsx("tabular px-4 py-2.5 text-right", (c.mean_diff ?? 0) > 0 ? "text-olive" : "text-oxblood")}>
                  {c.mean_diff == null ? "–" : `${c.mean_diff > 0 ? "+" : ""}${c.mean_diff.toFixed(3)}`}
                </td>
                <td className="tabular px-4 py-2.5 text-right text-ink-soft">
                  {num(c.ci_low)} to {num(c.ci_high)}
                </td>
                <td className="px-4 py-2.5">
                  {c.significant ? (
                    <span className="font-medium">{(c.mean_diff ?? 0) > 0 ? "Better" : "Worse"}</span>
                  ) : (
                    <span className="text-ink-faint">No clear difference</span>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </Panel>
    </section>
  );
}

export function TransferTable({ run }: { run: ResearchSummary }) {
  if (!run.transfer.length) return null;
  return (
    <section>
      <SectionHeader
        title="Does one gap threshold work on another site?"
        description="The threshold is tuned on one site and applied unchanged to the other. Close scores mean one setting can serve new organisations."
      />
      <Panel className="overflow-x-auto">
        <table className="w-full min-w-[40rem] text-left">
          <thead>
            <tr className="border-b border-rule-strong text-micro text-ink-faint">
              <th className="px-4 py-3 font-medium">Chunker</th>
              <th className="px-4 py-3 font-medium">Tuned on</th>
              <th className="px-4 py-3 font-medium">Applied to</th>
              <th className="px-4 py-3 text-right font-medium">Threshold</th>
              <th className="px-4 py-3 text-right font-medium">Accuracy, transferred</th>
              <th className="px-4 py-3 text-right font-medium">Accuracy, own best</th>
            </tr>
          </thead>
          <tbody>
            {run.transfer.map((t, n) => (
              <tr key={n} className="border-b border-rule text-small last:border-b-0">
                <td className="px-4 py-2.5">{label(t.config.split("@")[0])} <span className="text-micro text-ink-faint">{t.config.split("@")[1]}w</span></td>
                <td className="px-4 py-2.5">{t.from}</td>
                <td className="px-4 py-2.5">{t.to}</td>
                <td className="tabular px-4 py-2.5 text-right">{t.tau.toFixed(2)}</td>
                <td className="tabular px-4 py-2.5 text-right">{share(t.balanced_transferred)}</td>
                <td className="tabular px-4 py-2.5 text-right text-ink-soft">{share(t.balanced_own)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </Panel>
    </section>
  );
}

export function MethodNote({ run }: { run: ResearchSummary }) {
  return (
    <section className="max-w-measure text-small text-ink-soft">
      <h2 className="mb-2 text-h3 font-semibold text-ink">How these are measured</h2>
      <p>
        Each question was written from one gold passage of 40 to 120 words. A retrieved chunk counts as relevant when it
        holds at least {pct(run.relevance_threshold)} of that passage, or lies at least {pct(run.containment_threshold)}{" "}
        inside it, judged by overlapping three-word sequences. Recall@{run.k} measures how much of the passage the top{" "}
        {run.k} chunks cover together, so it rewards finding an answer a chunker split in two.
      </p>
      <p className="mt-2">
        Unanswerable questions are borrowed from the other sites in the run. A question is flagged as a knowledge gap when
        its retrieval confidence falls below {run.tau}; false gaps are answerable questions flagged anyway, missed gaps are
        unanswerable ones that slipped through.
      </p>
    </section>
  );
}
