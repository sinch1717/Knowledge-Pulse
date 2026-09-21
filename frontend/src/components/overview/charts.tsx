import {
  Area,
  AreaChart,
  CartesianGrid,
  Line,
  LineChart,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import type { TrendPoint } from "@/lib/types";
import { axisTick, palette, tooltipStyle } from "@/lib/chart";
import { pct, WEAK_CONFIDENCE } from "@/lib/format";
import { Panel, SectionHeader } from "@/components/ui";

export function QuestionVolumeChart({ data }: { data: TrendPoint[] }) {
  return (
    <Panel className="p-5">
      <SectionHeader title="Question volume" description="Questions customers asked in each period." />
      <div className="h-56">
        <ResponsiveContainer width="100%" height="100%">
          <AreaChart data={data} margin={{ top: 8, right: 8, bottom: 0, left: -18 }}>
            <defs>
              <linearGradient id="volume-fill" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor={palette.oxblood} stopOpacity={0.22} />
                <stop offset="100%" stopColor={palette.oxblood} stopOpacity={0.02} />
              </linearGradient>
            </defs>
            <CartesianGrid stroke={palette.rule} strokeDasharray="2 4" vertical={false} />
            <XAxis dataKey="period" tick={axisTick} axisLine={{ stroke: palette.rule }} tickLine={false} />
            <YAxis tick={axisTick} axisLine={false} tickLine={false} allowDecimals={false} />
            <Tooltip cursor={{ stroke: palette.ruleStrong }} contentStyle={tooltipStyle} formatter={(v: number) => [v, "Questions"]} />
            <Area type="monotone" dataKey="queries" stroke={palette.oxblood} strokeWidth={1.75} fill="url(#volume-fill)" />
          </AreaChart>
        </ResponsiveContainer>
      </div>
    </Panel>
  );
}

export function ConfidenceChart({ data }: { data: TrendPoint[] }) {
  return (
    <Panel className="p-5">
      <SectionHeader
        title="Retrieval confidence"
        description={`How well the sources covered what was asked. Below ${pct(WEAK_CONFIDENCE)} counts as answered poorly.`}
      />
      <div className="h-56">
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={data} margin={{ top: 8, right: 8, bottom: 0, left: -12 }}>
            <CartesianGrid stroke={palette.rule} strokeDasharray="2 4" vertical={false} />
            <XAxis dataKey="period" tick={axisTick} axisLine={{ stroke: palette.rule }} tickLine={false} />
            <YAxis
              domain={[0, 1]}
              ticks={[0, 0.25, 0.5, 0.75, 1]}
              tickFormatter={(v: number) => pct(v)}
              tick={axisTick}
              axisLine={false}
              tickLine={false}
            />
            <ReferenceLine y={WEAK_CONFIDENCE} stroke={palette.oxblood} strokeDasharray="4 4" strokeOpacity={0.6} />
            <Tooltip
              cursor={{ stroke: palette.ruleStrong }}
              contentStyle={tooltipStyle}
              formatter={(v: number) => [pct(v), "Mean confidence"]}
            />
            <Line
              type="monotone"
              dataKey="meanConfidence"
              stroke={palette.olive}
              strokeWidth={1.75}
              dot={{ r: 3, fill: palette.olive, strokeWidth: 0 }}
              activeDot={{ r: 4 }}
            />
          </LineChart>
        </ResponsiveContainer>
      </div>
    </Panel>
  );
}
