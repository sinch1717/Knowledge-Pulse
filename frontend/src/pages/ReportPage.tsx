import { api } from "@/lib/api";
import { useAsync } from "@/lib/format";
import {
  EmptyState,
  ErrorState,
  MetricSkeletons,
  PageContainer,
  PageHeader,
  RefreshButton,
  RowSkeletons,
  Skeleton,
} from "@/components/ui";
import {
  LatestReportCard,
  RecommendationsSection,
  ReportHistory,
  ReportMetricGrid,
} from "@/components/report/parts";

export function ReportPage() {
  const report = useAsync(() => api.getReport(), []);
  const history = useAsync(() => api.getReports(), []);

  const refresh = () => {
    report.reload();
    history.reload();
  };

  return (
    <PageContainer>
      <PageHeader
        title="Report"
        description="The client report for the latest period. Each recommendation names one action and shows the customer questions behind it."
        actions={<RefreshButton onClick={refresh} loading={report.loading || history.loading} />}
      />

      {!report.data && report.loading && (
        <div className="space-y-6">
          <Skeleton className="h-36 w-full" />
          <MetricSkeletons count={3} />
          <RowSkeletons rows={3} />
        </div>
      )}

      {report.error && !report.data && (
        <EmptyState
          title="No report yet"
          description={`${report.error} Reports are written by the analytics batch at the end of each period.`}
        />
      )}

      {report.data && (
        <div className="space-y-10">
          <LatestReportCard report={report.data} />
          <ReportMetricGrid report={report.data} />
          {report.data.recommendations.length > 0 ? (
            <RecommendationsSection recommendations={report.data.recommendations} />
          ) : (
            <EmptyState
              title="No recommendations this period"
              description="Nothing stood out strongly enough to act on. That usually means the sources covered what customers asked."
            />
          )}
        </div>
      )}

      <div className="mt-14">
        {history.data && history.data.length > 0 && (
          <ReportHistory reports={history.data} currentId={report.data?.id} />
        )}
        {history.error && report.data && <ErrorState message={`Report history is unavailable. ${history.error}`} onRetry={history.reload} />}
      </div>
    </PageContainer>
  );
}
