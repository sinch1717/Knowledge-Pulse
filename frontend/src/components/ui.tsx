import clsx from "clsx";
import type { ReactNode } from "react";
import type { TrendState } from "@/lib/types";
import { trendCopy } from "@/lib/format";

export function Page({
  title,
  standfirst,
  aside,
  children,
}: {
  title: string;
  standfirst?: string;
  aside?: ReactNode;
  children: ReactNode;
}) {
  return (
    <div className="px-6 py-10 md:px-12 md:py-14">
      <header className="mb-10 flex flex-wrap items-end justify-between gap-6 border-b border-rule pb-6">
        <div>
          <h1 className="font-display text-h1 font-semibold tracking-tight">{title}</h1>
          {standfirst && (
            <p className="mt-2 max-w-measure text-lead text-ink-soft">{standfirst}</p>
          )}
        </div>
        {aside}
      </header>
      {children}
    </div>
  );
}

export function Loading({ label = "Loading" }: { label?: string }) {
  return (
    <p className="py-16 text-small text-ink-faint" role="status">
      {label}…
    </p>
  );
}

export function ErrorNote({ message }: { message: string }) {
  return (
    <div className="border-l-2 border-oxblood bg-oxblood-wash px-4 py-3 text-small text-oxblood-deep">
      Could not load this. {message}
    </div>
  );
}

export function EmptyState({ title, action }: { title: string; action?: ReactNode }) {
  return (
    <div className="border border-dashed border-rule-strong px-6 py-14 text-center">
      <p className="text-lead text-ink-soft">{title}</p>
      {action && <div className="mt-4">{action}</div>}
    </div>
  );
}

export function TrendTag({ state }: { state: TrendState }) {
  const tone =
    state === "emerging"
      ? "bg-ochre-wash text-[#7A5A17] border-ochre"
      : state === "recurring"
        ? "bg-oxblood-wash text-oxblood-deep border-oxblood"
        : "bg-olive-wash text-[#414A22] border-olive";
  return (
    <span
      title={trendCopy[state].note}
      className={clsx("border-l-2 px-2 py-0.5 text-micro font-medium", tone)}
    >
      {trendCopy[state].label}
    </span>
  );
}

/** Thin bar bleeding behind a ledger row, so ranking is legible before reading. */
export function PriorityBar({ value }: { value: number }) {
  return (
    <span
      aria-hidden
      className="pointer-events-none absolute inset-y-0 left-0 bg-oxblood/[0.055]"
      style={{ width: `${Math.max(4, value * 100)}%` }}
    />
  );
}

export function Stat({
  label,
  value,
  note,
  tone = "ink",
}: {
  label: string;
  value: string;
  note?: string;
  tone?: "ink" | "oxblood" | "olive" | "ochre";
}) {
  const colour = {
    ink: "text-ink",
    oxblood: "text-oxblood",
    olive: "text-olive",
    ochre: "text-ochre",
  }[tone];
  return (
    <div className="border-t border-rule-strong pt-3">
      <div className={clsx("tabular font-display text-h2 font-semibold", colour)}>{value}</div>
      <div className="mt-1 text-small text-ink">{label}</div>
      {note && <div className="mt-0.5 text-micro text-ink-faint">{note}</div>}
    </div>
  );
}

export function Button({
  children,
  variant = "primary",
  ...rest
}: React.ButtonHTMLAttributes<HTMLButtonElement> & { variant?: "primary" | "quiet" }) {
  return (
    <button
      {...rest}
      className={clsx(
        "rounded px-4 py-2 text-small font-medium transition-colors disabled:cursor-not-allowed disabled:opacity-45",
        variant === "primary"
          ? "bg-oxblood text-paper-raised hover:bg-oxblood-deep"
          : "border border-rule-strong text-ink-soft hover:bg-paper-sunk hover:text-ink",
        rest.className,
      )}
    >
      {children}
    </button>
  );
}
