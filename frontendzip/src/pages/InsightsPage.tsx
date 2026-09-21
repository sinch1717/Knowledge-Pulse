import { useState } from "react";
import { Link } from "react-router-dom";
import clsx from "clsx";
import { api } from "@/lib/api";
import { growthLabel, trendCopy, useAsync } from "@/lib/format";
import type { TrendState } from "@/lib/types";
import { ErrorNote, Loading, Page, PriorityBar, TrendTag } from "@/components/ui";

type Filter = "all" | TrendState;

const filters: { key: Filter; label: string }[] = [
  { key: "all", label: "All" },
  { key: "emerging", label: "Emerging" },
  { key: "recurring", label: "Recurring" },
  { key: "stable", label: "Stable" },
];

export function InsightsPage() {
  const [filter, setFilter] = useState<Filter>("all");
  const { data, error, loading } = useAsync(() => api.getInsights(), []);

  const shown = data?.filter((i) => filter === "all" || i.trend === filter) ?? [];

  return (
    <Page
      title="Insights"
      standfirst="Every topic the assistant saw this period, ranked by volume, growth, how badly retrieval performed and how blocking the topic is."
    >
      <div className="mb-6 flex flex-wrap gap-2">
        {filters.map((f) => (
          <button
            key={f.key}
            onClick={() => setFilter(f.key)}
            className={clsx(
              "rounded border px-3 py-1.5 text-small transition-colors",
              filter === f.key
                ? "border-oxblood bg-oxblood-wash text-oxblood-deep"
                : "border-rule-strong text-ink-soft hover:bg-paper-sunk",
            )}
          >
            {f.label}
          </button>
        ))}
        {filter !== "all" && (
          <span className="self-center pl-1 text-micro text-ink-faint">{trendCopy[filter].note}</span>
        )}
      </div>

      {error && <ErrorNote message={error} />}
      {loading && <Loading label="Reading the archive" />}

      {data && (
        <div className="border-t border-rule-strong">
          {shown.map((i) => (
            <Link key={i.id} to={`/insights/${i.id}`} className="ledger-row block">
              <PriorityBar value={i.priority} />
              <div className="relative flex flex-wrap items-baseline gap-x-3 gap-y-1">
                <span className="tabular font-mono text-small text-ink-faint">
                  {String(i.rank).padStart(2, "0")}
                </span>
                <span className="text-lead">{i.name}</span>
                <TrendTag state={i.trend} />
              </div>
              <p className="relative mt-1 max-w-measure pl-8 text-small text-ink-soft">
                {i.sampleQueries[0]}
              </p>
              <div className="relative mt-2 flex flex-wrap gap-x-6 gap-y-1 pl-8 font-mono text-micro text-ink-faint">
                <span className="tabular">{i.queryCount} questions</span>
                <span className="tabular">{growthLabel(i.growth)} vs last period</span>
                <span className="tabular">confidence {i.meanConfidence.toFixed(2)}</span>
                <span className="tabular">priority {i.priority.toFixed(2)}</span>
              </div>
            </Link>
          ))}
        </div>
      )}

      <p className="mt-8 max-w-measure text-small text-ink-faint">
        Priority combines four signals: how many people asked, how fast that number is moving, how far
        retrieval confidence fell short, and an inferred sense of how badly the topic blocks the customer.
        Weights are 0.30, 0.30, 0.25 and 0.15 by default and can be changed in the backend config.
      </p>
    </Page>
  );
}
