import { Link } from "react-router-dom";
import { api } from "@/lib/api";
import { categoryCopy, dateLabel, growthLabel, pct, useAsync } from "@/lib/format";
import type { ActionCategory, Recommendation } from "@/lib/types";
import { ErrorNote, Loading, Page } from "@/components/ui";

const order: ActionCategory[] = ["product", "documentation", "faq", "customer_issue"];

export function ReportPage() {
  const { data, error, loading } = useAsync(() => api.getReport(), []);

  if (loading) return <Page title="Report"><Loading label="Assembling the report" /></Page>;
  if (error || !data) return <Page title="Report"><ErrorNote message={error ?? "Not found"} /></Page>;

  const grouped = order
    .map((c) => ({ category: c, items: data.recommendations.filter((r) => r.category === c) }))
    .filter((g) => g.items.length > 0);

  return (
    <Page
      title={`Report · ${data.period}`}
      standfirst={data.summary}
      aside={
        <div className="text-right font-mono text-micro text-ink-faint">
          <div>generated {dateLabel(data.generatedAt)}</div>
          <div className="tabular">
            {data.conversationCount} conversations · {data.queryCount} questions ·{" "}
            {pct(data.unansweredRate)} poorly answered
          </div>
        </div>
      }
    >
      {grouped.map((group) => (
        <section key={group.category} className="mb-16">
          <div className="mb-6 flex flex-wrap items-baseline gap-x-4 gap-y-1 border-b-2 border-ink pb-2">
            <h2 className="font-display text-h2 font-semibold tracking-tight">
              {categoryCopy[group.category].label}
            </h2>
            <span className="text-small text-ink-faint">{categoryCopy[group.category].note}</span>
          </div>
          <div className="space-y-10">
            {group.items.map((r) => (
              <RecommendationBlock key={r.id} rec={r} />
            ))}
          </div>
        </section>
      ))}
    </Page>
  );
}

function RecommendationBlock({ rec }: { rec: Recommendation }) {
  return (
    <article className="max-w-measure">
      <h3 className="text-h3 font-semibold">{rec.headline}</h3>
      <p className="mt-2 text-ink-soft">{rec.body}</p>

      {rec.faqAnswer && (
        <div className="mt-4 border-l-2 border-olive bg-olive-wash/50 px-4 py-3">
          <p className="text-micro text-ink-faint">Draft answer, ready to publish</p>
          <p className="mt-1 text-base">{rec.faqAnswer}</p>
        </div>
      )}

      <details className="group mt-4">
        <summary className="cursor-pointer list-none text-small text-oxblood underline underline-offset-4">
          <span className="group-open:hidden">Show the {rec.supportingQueries.length} questions behind this</span>
          <span className="hidden group-open:inline">Hide the questions</span>
        </summary>
        <ul className="mt-3 space-y-1.5 border-l border-rule-strong pl-4">
          {rec.supportingQueries.map((q, n) => (
            <li key={n} className="text-small text-ink-soft">
              {q}
            </li>
          ))}
        </ul>
      </details>

      <div className="mt-4 flex flex-wrap gap-x-6 gap-y-1 border-t border-rule pt-3 font-mono text-micro text-ink-faint">
        <span className="tabular">{rec.volume} questions</span>
        <span className="tabular">{growthLabel(rec.growth)}</span>
        <Link to={`/insights/${rec.insightId}`} className="underline underline-offset-2 hover:text-oxblood">
          {rec.insightName}
        </Link>
      </div>
      <p className="mt-2 text-small text-ink-soft">
        <span className="text-ink-faint">If you do this: </span>
        {rec.expectedEffect}
      </p>
    </article>
  );
}
