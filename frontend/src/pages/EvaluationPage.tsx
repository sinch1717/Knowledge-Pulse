import { api } from "@/lib/api";
import { dateLabel, useAsync } from "@/lib/format";
import { ErrorNote, Loading, Page } from "@/components/ui";

const metricCopy = [
  {
    key: "faithfulness" as const,
    label: "Faithfulness",
    plain: "Does the answer stay inside what the retrieved passages actually said?",
    target: 0.8,
  },
  {
    key: "answerRelevance" as const,
    label: "Answer relevance",
    plain: "Does the answer address the question that was asked?",
    target: 0.75,
  },
  {
    key: "contextRelevance" as const,
    label: "Context relevance",
    plain: "Were the retrieved passages the right ones to pull?",
    target: 0.7,
  },
];

export function EvaluationPage() {
  const { data, error, loading } = useAsync(() => api.getEvaluation(), []);

  if (loading) return <Page title="Evaluation"><Loading /></Page>;
  if (error || !data) return <Page title="Evaluation"><ErrorNote message={error ?? "No runs yet"} /></Page>;

  return (
    <Page
      title="Evaluation"
      standfirst="Scored against a held-out question set with no human-written answers, so it can be re-run after any change to the corpus or the retriever."
      aside={
        <div className="text-right font-mono text-micro text-ink-faint">
          <div>run {dateLabel(data.ranAt)}</div>
          <div className="tabular">{data.questionCount} questions</div>
        </div>
      }
    >
      <div className="max-w-measure space-y-8">
        {metricCopy.map((m) => {
          const score = data[m.key];
          const met = score >= m.target;
          return (
            <div key={m.key} className="border-t border-rule-strong pt-4">
              <div className="flex items-baseline justify-between gap-4">
                <h2 className="text-h3 font-semibold">{m.label}</h2>
                <span
                  className="tabular font-display text-h2 font-semibold"
                  style={{ color: met ? "#5A6337" : "#7A2E2E" }}
                >
                  {score.toFixed(2)}
                </span>
              </div>
              <p className="mt-1 text-small text-ink-soft">{m.plain}</p>
              <div className="relative mt-3 h-1.5 bg-paper-sunk">
                <div
                  className="h-full"
                  style={{ width: `${score * 100}%`, background: met ? "#5A6337" : "#7A2E2E" }}
                />
                <div
                  className="absolute top-[-3px] h-3 w-px bg-ink"
                  style={{ left: `${m.target * 100}%` }}
                  title={`Target ${m.target}`}
                />
              </div>
              <p className="tabular mt-1 font-mono text-micro text-ink-faint">
                target {m.target.toFixed(2)}
              </p>
            </div>
          );
        })}
      </div>

      {data.failures.length > 0 && (
        <section className="mt-14 max-w-measure">
          <h2 className="text-h3 font-semibold">Where it fell down</h2>
          <p className="mt-1 text-small text-ink-faint">
            The lowest-scoring questions in this run. Most of them are the same topics the insight ledger
            already flagged, which is a useful cross-check.
          </p>
          <div className="mt-4 border-t border-rule-strong">
            {data.failures.map((f, n) => (
              <div key={n} className="flex items-baseline gap-4 border-b border-rule py-3">
                <span className="tabular w-10 shrink-0 font-mono text-small text-oxblood">
                  {f.score.toFixed(2)}
                </span>
                <span className="min-w-0 flex-1 text-base">{f.question}</span>
                <span className="hidden shrink-0 font-mono text-micro text-ink-faint sm:block">
                  {f.metric.replace("_", " ")}
                </span>
              </div>
            ))}
          </div>
        </section>
      )}
    </Page>
  );
}
