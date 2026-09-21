import { Link, useNavigate } from "react-router-dom";
import type { Insight } from "@/lib/types";
import { growthLabel, pct, WEAK_CONFIDENCE } from "@/lib/format";
import { Panel, PriorityBadge, PriorityBar, SeverityBadge, TrendIndicator, TrendTag } from "@/components/ui";

const rank = (n: number) => String(n).padStart(2, "0");

function Confidence({ value }: { value: number }) {
  return (
    <span className={value < WEAK_CONFIDENCE ? "text-oxblood" : "text-ink"}>{pct(value)}</span>
  );
}

/** Desktop: every signal in its own column. Rows open the insight. */
export function InsightTable({ insights }: { insights: Insight[] }) {
  const navigate = useNavigate();
  return (
    <Panel className="hidden overflow-x-auto md:block">
      <table className="w-full min-w-[56rem] border-collapse text-left">
        <thead>
          <tr className="border-b border-rule-strong text-micro font-medium text-ink-faint">
            <th scope="col" className="w-12 px-4 py-3">Rank</th>
            <th scope="col" className="px-4 py-3">Topic</th>
            <th scope="col" className="px-4 py-3 text-right">Queries</th>
            <th scope="col" className="px-4 py-3 text-right">Previous</th>
            <th scope="col" className="px-4 py-3 text-right">Growth</th>
            <th scope="col" className="px-4 py-3 text-right">Confidence</th>
            <th scope="col" className="px-4 py-3">Severity</th>
            <th scope="col" className="px-4 py-3">Priority</th>
            <th scope="col" className="px-4 py-3 text-center">Trend</th>
          </tr>
        </thead>
        <tbody>
          {insights.map((i) => (
            <tr
              key={i.id}
              onClick={() => navigate(`/insights/${i.id}`)}
              className="relative cursor-pointer border-b border-rule transition-colors last:border-b-0 hover:bg-paper"
            >
              <td className="tabular px-4 py-3 align-top font-mono text-small text-ink-faint">{rank(i.rank)}</td>
              <td className="relative px-4 py-3 align-top">
                <PriorityBar value={i.priority} />
                <Link
                  to={`/insights/${i.id}`}
                  onClick={(e) => e.stopPropagation()}
                  className="relative text-base font-medium text-ink hover:text-oxblood"
                >
                  {i.name}
                </Link>
                <div className="relative mt-1.5 flex min-w-0 items-center gap-2">
                  <TrendTag state={i.trend} />
                  <span className="truncate font-mono text-micro text-ink-faint">{i.keywords.join(", ")}</span>
                </div>
              </td>
              <td className="tabular px-4 py-3 text-right align-top">{i.queryCount}</td>
              <td className="tabular px-4 py-3 text-right align-top text-ink-faint">{i.previousQueryCount}</td>
              <td className="tabular px-4 py-3 text-right align-top">{growthLabel(i.growth)}</td>
              <td className="tabular px-4 py-3 text-right align-top">
                <Confidence value={i.meanConfidence} />
              </td>
              <td className="px-4 py-3 align-top"><SeverityBadge value={i.severity} /></td>
              <td className="px-4 py-3 align-top"><PriorityBadge value={i.priority} /></td>
              <td className="px-4 py-3 text-center align-top"><TrendIndicator growth={i.growth} /></td>
            </tr>
          ))}
        </tbody>
      </table>
    </Panel>
  );
}

/** Mobile: the same record, stacked. */
export function InsightCard({ insight: i }: { insight: Insight }) {
  return (
    <Link to={`/insights/${i.id}`} className="block">
      <Panel className="relative overflow-hidden p-4 transition-colors hover:bg-paper">
        <PriorityBar value={i.priority} />
        <div className="relative flex items-start justify-between gap-3">
          <div className="min-w-0">
            <span className="tabular font-mono text-micro text-ink-faint">{rank(i.rank)}</span>
            <p className="text-base font-medium">{i.name}</p>
          </div>
          <TrendIndicator growth={i.growth} />
        </div>
        <div className="relative mt-2 flex flex-wrap gap-2">
          <TrendTag state={i.trend} />
          <PriorityBadge value={i.priority} />
          <SeverityBadge value={i.severity} />
        </div>
        <dl className="relative mt-3 grid grid-cols-3 gap-2 text-micro">
          <div>
            <dt className="text-ink-faint">Queries</dt>
            <dd className="tabular text-small">{i.queryCount} <span className="text-ink-faint">from {i.previousQueryCount}</span></dd>
          </div>
          <div>
            <dt className="text-ink-faint">Growth</dt>
            <dd className="tabular text-small">{growthLabel(i.growth)}</dd>
          </div>
          <div>
            <dt className="text-ink-faint">Confidence</dt>
            <dd className="tabular text-small"><Confidence value={i.meanConfidence} /></dd>
          </div>
        </dl>
      </Panel>
    </Link>
  );
}

export function InsightList({ insights }: { insights: Insight[] }) {
  return (
    <>
      <InsightTable insights={insights} />
      <div className="space-y-3 md:hidden">
        {insights.map((i) => (
          <InsightCard key={i.id} insight={i} />
        ))}
      </div>
    </>
  );
}
