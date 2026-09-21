import { Link } from "react-router-dom";
import clsx from "clsx";
import type { ReactNode } from "react";
import type { Insight, Overview } from "@/lib/types";
import { pct, WEAK_CONFIDENCE } from "@/lib/format";
import { Panel } from "@/components/ui";

function GlanceColumn({
  title,
  accent,
  children,
}: {
  title: string;
  accent: "ochre" | "oxblood" | "ink";
  children: ReactNode;
}) {
  return (
    <Panel
      className={clsx(
        "border-l-2 p-5",
        accent === "ochre" && "border-l-ochre",
        accent === "oxblood" && "border-l-oxblood",
        accent === "ink" && "border-l-ink",
      )}
    >
      <h3 className="text-lead font-semibold">{title}</h3>
      <div className="mt-3 text-small text-ink-soft">{children}</div>
    </Panel>
  );
}

function TopicLinks({ items, detail }: { items: Insight[]; detail: (i: Insight) => string }) {
  return (
    <ul className="space-y-2">
      {items.map((i) => (
        <li key={i.id} className="flex items-baseline justify-between gap-3">
          <Link to={`/insights/${i.id}`} className="min-w-0 truncate text-ink underline-offset-4 hover:text-oxblood hover:underline">
            {i.name}
          </Link>
          <span className="tabular shrink-0 font-mono text-micro text-ink-faint">{detail(i)}</span>
        </li>
      ))}
    </ul>
  );
}

export function AtAGlance({ overview, insights }: { overview: Overview; insights: Insight[] }) {
  const emerging = insights.filter((i) => i.trend === "emerging").slice(0, 3);
  const gaps = [...insights]
    .filter((i) => i.meanConfidence < WEAK_CONFIDENCE)
    .sort((a, b) => a.meanConfidence - b.meanConfidence)
    .slice(0, 3);
  const poorlyAnswered = Math.round(overview.queryCount * overview.unansweredRate);

  return (
    <section>
      <h2 className="mb-4 text-h3 font-semibold">At a glance</h2>
      <div className="grid gap-4 lg:grid-cols-3">
        <GlanceColumn title="Emerging topics" accent="ochre">
          {emerging.length === 0 ? (
            <p>Nothing new is rising sharply this period.</p>
          ) : (
            <>
              <p className="mb-3">Small today, growing fast. A volume ranking would bury these.</p>
              <TopicLinks items={emerging} detail={(i) => `${i.previousQueryCount} to ${i.queryCount}`} />
            </>
          )}
        </GlanceColumn>

        <GlanceColumn title="Unanswered questions" accent="oxblood">
          <p>
            <span className="tabular font-display text-h2 font-semibold text-oxblood">{poorlyAnswered.toLocaleString()}</span>
            <span className="ml-2">of {overview.queryCount.toLocaleString()} questions</span>
          </p>
          <p className="mt-2">
            {pct(overview.unansweredRate)} were answered with confidence below {pct(WEAK_CONFIDENCE)}, which usually
            means the sources do not cover the question.
          </p>
          <Link to="/insights" className="mt-3 inline-block text-oxblood underline underline-offset-4">
            See which topics
          </Link>
        </GlanceColumn>

        <GlanceColumn title="Knowledge gaps" accent="ink">
          {gaps.length === 0 ? (
            <p>Every topic this period was answered with reasonable confidence.</p>
          ) : (
            <>
              <p className="mb-3">Topics where the sources had the least to offer.</p>
              <TopicLinks items={gaps} detail={(i) => pct(i.meanConfidence)} />
            </>
          )}
        </GlanceColumn>
      </div>
    </section>
  );
}
