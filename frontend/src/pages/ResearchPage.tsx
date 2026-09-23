import { useState } from "react";
import clsx from "clsx";
import { api } from "@/lib/api";
import { useAsync } from "@/lib/format";
import {
  ChartSkeleton,
  EmptyState,
  PageContainer,
  PageHeader,
  RefreshButton,
  RowSkeletons,
  inputClass,
} from "@/components/ui";
import {
  ComparisonChart,
  MethodNote,
  MetricTable,
  RunMeta,
  SignificanceTable,
  SitesTable,
  TransferTable,
  gapColumns,
  qualityColumns,
  retrievalColumns,
} from "@/components/research/parts";

const commands = [
  "python -m research.snapshot --site plausible",
  "python -m research.questions --site plausible --count 100",
  "python -m research.run --sites plausible,fastapi",
];

export function ResearchPage() {
  const { data, error, loading, reload } = useAsync(() => api.getResearch(), []);
  const [size, setSize] = useState<number | null>(null);

  const sizes = data?.sizes ?? [];
  const activeSize = size ?? sizes[0] ?? null;
  const results = data?.results.filter((r) => activeSize == null || r.size === activeSize) ?? [];
  const comparisons = data?.comparisons.filter((c) => activeSize == null || c.config.endsWith(`@${activeSize}`)) ?? [];
  const transfer = data?.transfer.filter((t) => activeSize == null || t.config.endsWith(`@${activeSize}`)) ?? [];

  return (
    <PageContainer>
      <PageHeader
        title="Research"
        description="How the way documentation is chunked changes what the assistant retrieves, and how reliably it spots gaps in the docs."
        meta={data && <RunMeta run={data} />}
        actions={
          <>
            {sizes.length > 1 && (
              <label className="flex items-center gap-2 text-small text-ink-soft">
                Chunk size
                <select
                  value={activeSize ?? ""}
                  onChange={(e) => setSize(Number(e.target.value))}
                  className={clsx(inputClass, "w-auto py-2 pr-8 text-small")}
                >
                  {sizes.map((s) => (
                    <option key={s} value={s}>
                      {s} words
                    </option>
                  ))}
                </select>
              </label>
            )}
            <RefreshButton onClick={reload} loading={loading} />
          </>
        }
      />

      {loading && !data && (
        <div className="space-y-6">
          <RowSkeletons rows={3} />
          <ChartSkeleton height="h-72" />
        </div>
      )}

      {error && !data && (
        <EmptyState
          title="No experiment results yet"
          description="Run these from the backend folder, in order. The last one writes the results this page reads."
          action={
            <pre className="overflow-x-auto rounded border border-rule-strong bg-paper-raised px-4 py-3 text-left font-mono text-small text-ink">
              {commands.join("\n")}
            </pre>
          }
        />
      )}

      {data?.run_id === "placeholder" && (
        <p className="mb-8 rounded-md border-l-4 border-ochre bg-ochre-wash px-4 py-3 text-small text-[#7A5A17]">
          These numbers are invented placeholders so the layout can be reviewed. Do not cite them. Connect the backend and
          run the experiment for real results.
        </p>
      )}

      {data && (
        <div className="space-y-12">
          <SitesTable run={data} />
          <ComparisonChart results={results} k={data.k} />
          <MetricTable
            title="Retrieval"
            description="On questions each site's own documentation answers. The best value per site is marked."
            results={results}
            columns={retrievalColumns(data.k)}
          />
          <MetricTable
            title="Knowledge-gap signal"
            description="Retrieval confidence on answerable versus unanswerable questions. This is the signal the insights layer ranks topics by."
            results={results}
            columns={gapColumns}
          />
          <MetricTable
            title="Chunk quality"
            description="Properties of the chunks themselves, measured without any questions."
            results={results}
            columns={qualityColumns}
          />
          <SignificanceTable run={{ ...data, comparisons }} />
          <TransferTable run={{ ...data, transfer }} />
          <MethodNote run={data} />
        </div>
      )}
    </PageContainer>
  );
}
