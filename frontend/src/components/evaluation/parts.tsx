import clsx from "clsx";
import type { EvaluationRun } from "@/lib/types";
import { dateLabel, pct } from "@/lib/format";
import { Panel, SectionHeader } from "@/components/ui";

export const metrics = [
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

export function MetricProgress({ score, target }: { score: number; target: number }) {
  const met = score >= target;
  return (
    <div>
      <div className="relative h-2 rounded-full bg-paper-sunk">
        <div
          className={clsx("h-full rounded-full", met ? "bg-olive" : "bg-oxblood")}
          style={{ width: `${Math.min(100, score * 100)}%` }}
        />
        <div
          className="absolute -top-1 h-4 w-0.5 bg-ink"
          style={{ left: `${target * 100}%` }}
          title={`Target ${pct(target)}`}
          aria-hidden
        />
      </div>
      <p className="mt-1.5 text-micro text-ink-faint">Target {pct(target)}</p>
    </div>
  );
}

export function EvaluationMetricCard({
  label,
  plain,
  score,
  target,
}: {
  label: string;
  plain: string;
  score: number;
  target: number;
}) {
  const met = score >= target;
  return (
    <Panel className="flex flex-col p-5">
      <div className="flex items-baseline justify-between gap-3">
        <h2 className="text-lead font-semibold">{label}</h2>
        <span className={clsx("text-micro font-medium", met ? "text-olive" : "text-oxblood")}>
          {met ? "Meets target" : "Below target"}
        </span>
      </div>
      <p className={clsx("tabular mt-3 font-display text-h1 font-semibold", met ? "text-olive" : "text-oxblood")}>
        {score.toFixed(2)}
      </p>
      <p className="mt-1 flex-1 text-small text-ink-soft">{plain}</p>
      <div className="mt-4">
        <MetricProgress score={score} target={target} />
      </div>
    </Panel>
  );
}

export function EvaluationMetricGrid({ run }: { run: EvaluationRun }) {
  return (
    <div className="grid gap-4 md:grid-cols-3">
      {metrics.map((m) => (
        <EvaluationMetricCard key={m.key} label={m.label} plain={m.plain} score={run[m.key]} target={m.target} />
      ))}
    </div>
  );
}

export function EvaluationMetadata({ run }: { run: EvaluationRun }) {
  return (
    <div className="flex flex-wrap gap-x-6 gap-y-1 text-small text-ink-soft">
      <span>
        <span className="tabular font-medium text-ink">{run.questionCount}</span> questions evaluated
      </span>
      <span>Run on {dateLabel(run.ranAt)}</span>
    </div>
  );
}

const metricName: Record<string, string> = {
  faithfulness: "Faithfulness",
  answer_relevance: "Answer relevance",
  context_relevance: "Context relevance",
};

export function FailureCard({ failure }: { failure: EvaluationRun["failures"][number] }) {
  return (
    <li className="flex items-baseline gap-4 border-b border-rule px-4 py-3 last:border-b-0">
      <span className="tabular w-10 shrink-0 font-mono text-small text-oxblood">{failure.score.toFixed(2)}</span>
      <span className="min-w-0 flex-1 text-base">{failure.question}</span>
      <span className="hidden shrink-0 text-micro text-ink-faint sm:block">
        {metricName[failure.metric] ?? failure.metric.replace(/_/g, " ")}
      </span>
    </li>
  );
}

export function EvaluationFailures({ failures }: { failures: EvaluationRun["failures"] }) {
  return (
    <section>
      <SectionHeader
        title="Where it fell down"
        description="The lowest-scoring questions in this run. They usually line up with the topics Insights already flags."
      />
      <Panel>
        <ul>
          {failures.map((f, n) => (
            <FailureCard key={n} failure={f} />
          ))}
        </ul>
      </Panel>
    </section>
  );
}
