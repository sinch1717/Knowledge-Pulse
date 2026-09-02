import { Link } from "react-router-dom";
import { Area, AreaChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { api } from "@/lib/api";
import { growthLabel, pct, useAsync } from "@/lib/format";
import { ErrorNote, Loading, Page, PriorityBar, Stat, TrendTag } from "@/components/ui";

export function OverviewPage() {
  const overview = useAsync(() => api.getOverview(), []);
  const insights = useAsync(() => api.getInsights(), []);

  if (overview.error) return <Page title="This period"><ErrorNote message={overview.error} /></Page>;
  if (!overview.data || !insights.data) return <Page title="This period"><Loading /></Page>;

  const o = overview.data;
  const top = insights.data.slice(0, 4);
  const emerging = insights.data.filter((i) => i.trend === "emerging");

  return (
    <Page
      title={o.period}
      standfirst="Everything below comes from questions customers asked the assistant. Nothing was solicited."
    >
      {/* Lede: the single sentence that says what happened this month. */}
      <p className="mb-12 max-w-[26ch] font-display text-display font-semibold leading-[1.02] tracking-tight md:max-w-[22ch]">
        {o.queryCount.toLocaleString()} questions,{" "}
        <span className="text-ink-faint">{o.topicCount} topics,</span>{" "}
        <span className="text-oxblood">{o.emergingCount} of them new.</span>
      </p>

      <div className="grid gap-8 md:grid-cols-4">
        <Stat label="Conversations" value={o.conversationCount.toLocaleString()} note="Distinct sessions" />
        <Stat
          label="Answered poorly"
          value={pct(o.unansweredRate)}
          note="Retrieval confidence below 0.4"
          tone="oxblood"
        />
        <Stat label="Mean confidence" value={o.meanConfidence.toFixed(2)} note="Across every answered turn" />
        <Stat label="Emerging concerns" value={String(o.emergingCount)} note="Rising from a low base" tone="ochre" />
      </div>

      <section className="mt-14">
        <h2 className="text-h3 font-semibold">Question volume</h2>
        <div className="mt-4 h-52 border-t border-rule pt-4">
          <ResponsiveContainer width="100%" height="100%">
            <AreaChart data={o.volumeByPeriod} margin={{ top: 4, right: 8, bottom: 0, left: -20 }}>
              <defs>
                <linearGradient id="vol" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor="#7A2E2E" stopOpacity={0.22} />
                  <stop offset="100%" stopColor="#7A2E2E" stopOpacity={0.02} />
                </linearGradient>
              </defs>
              <XAxis
                dataKey="period"
                tick={{ fill: "#8B8171", fontSize: 12 }}
                axisLine={{ stroke: "#DDD5C6" }}
                tickLine={false}
              />
              <YAxis tick={{ fill: "#8B8171", fontSize: 12 }} axisLine={false} tickLine={false} />
              <Tooltip
                cursor={{ stroke: "#C7BCA6" }}
                contentStyle={{
                  background: "#FBF8F1",
                  border: "1px solid #DDD5C6",
                  borderRadius: 3,
                  fontSize: 13,
                }}
              />
              <Area
                type="monotone"
                dataKey="queries"
                stroke="#7A2E2E"
                strokeWidth={1.5}
                fill="url(#vol)"
              />
            </AreaChart>
          </ResponsiveContainer>
        </div>
      </section>

      <section className="mt-14">
        <div className="flex items-baseline justify-between border-b border-rule-strong pb-2">
          <h2 className="text-h3 font-semibold">What matters most</h2>
          <Link to="/insights" className="text-small text-oxblood underline underline-offset-4">
            All {insights.data.length} insights
          </Link>
        </div>
        <ol>
          {top.map((i) => (
            <li key={i.id}>
              <Link to={`/insights/${i.id}`} className="ledger-row block">
                <PriorityBar value={i.priority} />
                <div className="relative flex flex-wrap items-baseline gap-x-3 gap-y-1">
                  <span className="tabular font-mono text-small text-ink-faint">
                    {String(i.rank).padStart(2, "0")}
                  </span>
                  <span className="text-lead">{i.name}</span>
                  <TrendTag state={i.trend} />
                </div>
                <div className="relative mt-1 flex gap-5 pl-8 text-micro text-ink-faint">
                  <span className="tabular">{i.queryCount} questions</span>
                  <span className="tabular">{growthLabel(i.growth)}</span>
                  <span className="tabular">confidence {i.meanConfidence.toFixed(2)}</span>
                </div>
              </Link>
            </li>
          ))}
        </ol>
      </section>

      {emerging.length > 0 && (
        <section className="mt-14 max-w-measure border-l-2 border-ochre pl-5">
          <h2 className="text-h3 font-semibold">Worth catching early</h2>
          <p className="mt-2 text-ink-soft">
            These topics are small enough that a volume-ranked view would bury them, but each one grew
            sharply against the previous period.
          </p>
          <ul className="mt-4 space-y-2">
            {emerging.map((i) => (
              <li key={i.id} className="text-small">
                <Link to={`/insights/${i.id}`} className="underline underline-offset-4 hover:text-oxblood">
                  {i.name}
                </Link>
                <span className="tabular ml-2 text-ink-faint">
                  {i.previousQueryCount} → {i.queryCount}
                </span>
              </li>
            ))}
          </ul>
        </section>
      )}
    </Page>
  );
}
