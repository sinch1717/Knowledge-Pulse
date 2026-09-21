import { useParams } from "react-router-dom";
import { api } from "@/lib/api";
import { growthLabel, pct, useAsync, WEAK_CONFIDENCE } from "@/lib/format";
import {
  ChartSkeleton,
  ErrorState,
  MetricCard,
  MetricGrid,
  MetricSkeletons,
  PageContainer,
  PageHeader,
  PriorityBadge,
  RowSkeletons,
  SeverityBadge,
  Skeleton,
  TrendIndicator,
  TrendTag,
} from "@/components/ui";
import {
  BackNavigation,
  CustomerQuestions,
  InsightHistoryChart,
  WeakKnowledgeMatches,
} from "@/components/insights/detail";

export function InsightDetailPage() {
  const { id = "" } = useParams();
  const { data, error, loading, reload } = useAsync(() => api.getInsight(id), [id]);

  if (loading && !data) {
    return (
      <PageContainer>
        <BackNavigation to="/insights" label="All insights" />
        <Skeleton className="mb-10 h-10 w-2/3" />
        <div className="space-y-6">
          <MetricSkeletons count={4} columns={4} />
          <ChartSkeleton />
          <RowSkeletons rows={4} />
        </div>
      </PageContainer>
    );
  }

  if (error || !data) {
    return (
      <PageContainer>
        <BackNavigation to="/insights" label="All insights" />
        <ErrorState message={error ?? "This insight does not exist."} onRetry={reload} />
      </PageContainer>
    );
  }

  const weak = data.meanConfidence < WEAK_CONFIDENCE;

  return (
    <PageContainer>
      <BackNavigation to="/insights" label="All insights" />
      <PageHeader
        title={data.name}
        description={`Ranked ${data.rank} this period. ${data.queryCount} questions from customers.`}
        meta={
          <div className="flex flex-wrap items-center gap-2">
            <TrendTag state={data.trend} />
            <PriorityBadge value={data.priority} />
            <SeverityBadge value={data.severity} />
            <TrendIndicator growth={data.growth} showLabel />
          </div>
        }
      />

      <div className="space-y-10">
        <MetricGrid columns={4}>
          <MetricCard label="Questions" value={String(data.queryCount)} note="This period" />
          <MetricCard label="Previous period" value={String(data.previousQueryCount)} note="Questions last period" />
          <MetricCard
            label="Growth"
            value={growthLabel(data.growth)}
            note="Period over period"
            tone={data.growth > 0.5 ? "ochre" : "ink"}
          />
          <MetricCard
            label="Mean confidence"
            value={pct(data.meanConfidence)}
            note={weak ? "Sources are not covering this" : "Sources are holding up"}
            tone={weak ? "oxblood" : "olive"}
          />
        </MetricGrid>

        {data.history.length > 0 && <InsightHistoryChart history={data.history} />}

        {data.memberQueries.length > 0 && <CustomerQuestions questions={data.memberQueries} />}

        {data.weakestChunks.length > 0 && <WeakKnowledgeMatches chunks={data.weakestChunks} />}

        {data.keywords.length > 0 && (
          <section>
            <h2 className="mb-3 text-h3 font-semibold">Keywords</h2>
            <div className="flex flex-wrap gap-2">
              {data.keywords.map((k) => (
                <span key={k} className="rounded border border-rule-strong bg-paper-raised px-2 py-1 font-mono text-micro text-ink-soft">
                  {k}
                </span>
              ))}
            </div>
          </section>
        )}
      </div>
    </PageContainer>
  );
}
