import { Link, useParams } from "react-router-dom";
import { Bar, BarChart, Cell, ResponsiveContainer, Tooltip, XAxis } from "recharts";
import { api } from "@/lib/api";
import { dateLabel, growthLabel, useAsync } from "@/lib/format";
import { ErrorNote, Loading, Page, Stat, TrendTag } from "@/components/ui";

export function InsightDetailPage() {
  const { id = "" } = useParams();
  const { data, error, loading } = useAsync(() => api.getInsight(id), [id]);

  if (loading) return <Page title="Insight"><Loading /></Page>;
  if (error || !data) return <Page title="Insight"><ErrorNote message={error ?? "Not found"} /></Page>;

  return (
    <Page
      title={data.name}
      standfirst={`Ranked ${data.rank} this period. ${data.queryCount} customers asked about this.`}
      aside={<TrendTag state={data.trend} />}
    >
      <Link to="/insights" className="mb-8 inline-block text-small text-oxblood underline underline-offset-4">
        Back to all insights
      </Link>

      <div className="grid gap-8 md:grid-cols-4">
        <Stat label="Questions" value={String(data.queryCount)} note={`${data.previousQueryCount} last period`} />
        <Stat label="Growth" value={growthLabel(data.growth)} tone={data.growth > 0.5 ? "ochre" : "ink"} />
        <Stat
          label="Mean confidence"
          value={data.meanConfidence.toFixed(2)}
          note={data.meanConfidence < 0.4 ? "Retrieval is failing here" : "Retrieval is holding up"}
          tone={data.meanConfidence < 0.4 ? "oxblood" : "olive"}
        />
        <Stat label="Priority" value={data.priority.toFixed(2)} note="Weighted composite" />
      </div>

      <section className="mt-14">
        <h2 className="text-h3 font-semibold">Across periods</h2>
        <div className="mt-4 h-44 border-t border-rule pt-4">
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={data.history} margin={{ top: 4, right: 8, bottom: 0, left: 0 }}>
              <XAxis
                dataKey="period"
                tick={{ fill: "#8B8171", fontSize: 12 }}
                axisLine={{ stroke: "#DDD5C6" }}
                tickLine={false}
              />
              <Tooltip
                cursor={{ fill: "#EAE3D5" }}
                contentStyle={{
                  background: "#FBF8F1",
                  border: "1px solid #DDD5C6",
                  borderRadius: 3,
                  fontSize: 13,
                }}
              />
              <Bar dataKey="queries" radius={[2, 2, 0, 0]}>
                {data.history.map((_, n) => (
                  <Cell key={n} fill={n === data.history.length - 1 ? "#7A2E2E" : "#C7BCA6"} />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </div>
      </section>

      <section className="mt-14">
        <h2 className="text-h3 font-semibold">What people actually asked</h2>
        <p className="mt-1 text-small text-ink-faint">
          Verbatim, with the retrieval confidence the assistant managed on each.
        </p>
        <div className="mt-4 border-t border-rule-strong">
          {data.memberQueries.map((q) => (
            <div key={q.id} className="flex items-baseline gap-4 border-b border-rule px-1 py-3">
              <span
                className="tabular w-10 shrink-0 font-mono text-small"
                style={{ color: q.confidence < 0.4 ? "#7A2E2E" : "#5A6337" }}
              >
                {q.confidence.toFixed(2)}
              </span>
              <span className="min-w-0 flex-1 text-base">{q.text}</span>
              <span className="hidden shrink-0 text-micro text-ink-faint sm:block">
                {dateLabel(q.askedAt)}
              </span>
            </div>
          ))}
        </div>
      </section>

      {data.weakestChunks.length > 0 && (
        <section className="mt-14 max-w-measure">
          <h2 className="text-h3 font-semibold">Closest thing the sources had</h2>
          <p className="mt-1 text-small text-ink-faint">
            These are the passages retrieval kept returning. If they look unrelated to the questions above,
            the corpus is missing the answer rather than phrasing it badly.
          </p>
          <div className="mt-4 space-y-4">
            {data.weakestChunks.map((c) => (
              <figure key={c.chunkId} className="border-l-2 border-rule-strong pl-4">
                <blockquote className="text-base text-ink-soft">{c.excerpt}</blockquote>
                <figcaption className="mt-2 font-mono text-micro text-ink-faint">
                  {c.sourceLabel} · {c.headingPath} · similarity {c.similarity.toFixed(2)} · {c.chunkId}
                </figcaption>
              </figure>
            ))}
          </div>
        </section>
      )}

      <section className="mt-14">
        <h2 className="text-h3 font-semibold">Cluster keywords</h2>
        <div className="mt-3 flex flex-wrap gap-2">
          {data.keywords.map((k) => (
            <span key={k} className="border border-rule-strong px-2 py-1 font-mono text-micro text-ink-soft">
              {k}
            </span>
          ))}
        </div>
      </section>
    </Page>
  );
}
