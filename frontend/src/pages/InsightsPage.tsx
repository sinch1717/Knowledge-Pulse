import { useEffect, useState } from "react";
import clsx from "clsx";
import { api } from "@/lib/api";
import { trendCopy, useAsync } from "@/lib/format";
import type { TrendState } from "@/lib/types";
import { EmptyState, ErrorState, PageContainer, PageHeader, RefreshButton, RowSkeletons, inputClass } from "@/components/ui";
import { InsightList } from "@/components/insights/InsightList";

type Filter = "all" | TrendState;

const filters: { key: Filter; label: string }[] = [
  { key: "all", label: "All" },
  { key: "emerging", label: "Emerging" },
  { key: "recurring", label: "Recurring" },
  { key: "stable", label: "Stable" },
];

export function InsightsPage() {
  const periods = useAsync(() => api.getPeriods(), []);
  const [period, setPeriod] = useState<string>("");
  const [filter, setFilter] = useState<Filter>("all");
  const insights = useAsync(() => api.getInsights(period || undefined), [period]);

  // Default to the most recent period once the list arrives.
  useEffect(() => {
    if (!period && periods.data?.length) setPeriod(periods.data[0]);
  }, [period, periods.data]);

  const shown = insights.data?.filter((i) => filter === "all" || i.trend === filter) ?? [];

  return (
    <PageContainer>
      <PageHeader
        title="Insights"
        description="What customers are asking, what is changing, and where the knowledge base appears weakest."
        actions={
          <>
            {periods.data && periods.data.length > 0 && (
              <label className="flex items-center gap-2 text-small text-ink-soft">
                <span className="sr-only">Period</span>
                <select
                  value={period}
                  onChange={(e) => setPeriod(e.target.value)}
                  className={clsx(inputClass, "w-auto py-2 pr-8 text-small")}
                >
                  {periods.data.map((p) => (
                    <option key={p} value={p}>
                      {p}
                    </option>
                  ))}
                </select>
              </label>
            )}
            <RefreshButton onClick={insights.reload} loading={insights.loading} />
          </>
        }
      />

      <div className="mb-6 flex flex-wrap items-center gap-2">
        {filters.map((f) => (
          <button
            key={f.key}
            onClick={() => setFilter(f.key)}
            aria-pressed={filter === f.key}
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
        {filter !== "all" && <span className="pl-1 text-micro text-ink-faint">{trendCopy[filter].note}</span>}
      </div>

      {insights.error && <ErrorState message={insights.error} onRetry={insights.reload} />}
      {!insights.data && !insights.error && <RowSkeletons rows={6} />}

      {insights.data && insights.data.length === 0 && (
        <EmptyState
          title="No topics for this period"
          description="Topics appear after the analytics batch has clustered the period's questions. Run analytics from This period, then refresh."
        />
      )}

      {insights.data && insights.data.length > 0 && shown.length === 0 && (
        <EmptyState title={`No ${filter} topics this period`} description="Try another filter or period." />
      )}

      {shown.length > 0 && <InsightList insights={shown} />}

      <p className="mt-8 max-w-measure text-small text-ink-faint">
        Priority combines four signals: how many people asked, how fast that number is moving, how far retrieval
        confidence fell short, and how badly the topic blocks the customer. Default weights are 0.30, 0.30, 0.25 and
        0.15.
      </p>
    </PageContainer>
  );
}
