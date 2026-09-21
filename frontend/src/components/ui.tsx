import clsx from "clsx";
import { useEffect, useRef, type ReactNode } from "react";
import { AlertCircle, ArrowDownRight, ArrowRight, ArrowUpRight, Loader2, RefreshCw, X } from "lucide-react";
import type { TrendState } from "@/lib/types";
import { directionOf, trendCopy, type Direction } from "@/lib/format";

// ---------------------------------------------------------------------------
// Page scaffolding
// ---------------------------------------------------------------------------

export function PageContainer({ children, narrow = false }: { children: ReactNode; narrow?: boolean }) {
  return (
    <div className={clsx("mx-auto w-full px-5 py-10 md:px-10 md:py-12", narrow ? "max-w-3xl" : "max-w-6xl")}>
      {children}
    </div>
  );
}

export function PageHeader({
  title,
  description,
  actions,
  meta,
  centered = false,
}: {
  title: ReactNode;
  description?: ReactNode;
  actions?: ReactNode;
  meta?: ReactNode;
  centered?: boolean;
}) {
  if (centered) {
    return (
      <header className="mb-10 text-center">
        <h1 className="font-display text-h1 font-semibold tracking-tight">{title}</h1>
        {description && <p className="mx-auto mt-2 max-w-measure text-lead text-ink-soft">{description}</p>}
        {meta && <div className="mt-3 flex justify-center">{meta}</div>}
        {actions && <div className="mt-5 flex flex-wrap justify-center gap-2">{actions}</div>}
      </header>
    );
  }
  return (
    <header className="mb-10 flex flex-wrap items-end justify-between gap-6 border-b border-rule pb-6">
      <div className="min-w-0">
        <h1 className="font-display text-h1 font-semibold tracking-tight">{title}</h1>
        {description && <p className="mt-2 max-w-measure text-lead text-ink-soft">{description}</p>}
        {meta && <div className="mt-3">{meta}</div>}
      </div>
      {actions && <div className="flex flex-wrap items-center gap-2">{actions}</div>}
    </header>
  );
}

export function SectionHeader({
  title,
  description,
  action,
}: {
  title: string;
  description?: string;
  action?: ReactNode;
}) {
  return (
    <div className="mb-4 flex flex-wrap items-end justify-between gap-3">
      <div>
        <h2 className="text-h3 font-semibold">{title}</h2>
        {description && <p className="mt-1 text-small text-ink-faint">{description}</p>}
      </div>
      {action}
    </div>
  );
}

/** The raised surface every card and panel sits on. */
export function Panel({ children, className }: { children: ReactNode; className?: string }) {
  return <div className={clsx("rounded-md border border-rule bg-paper-raised", className)}>{children}</div>;
}

// ---------------------------------------------------------------------------
// Numbers
// ---------------------------------------------------------------------------

export type Tone = "ink" | "oxblood" | "olive" | "ochre";

const toneText: Record<Tone, string> = {
  ink: "text-ink",
  oxblood: "text-oxblood",
  olive: "text-olive",
  ochre: "text-ochre",
};

export function MetricCard({
  label,
  value,
  note,
  tone = "ink",
}: {
  label: string;
  value: string;
  note?: string;
  tone?: Tone;
}) {
  return (
    <Panel className="px-5 py-4">
      <div className="text-small text-ink-soft">{label}</div>
      <div className={clsx("tabular mt-2 font-display text-h1 font-semibold", toneText[tone])}>{value}</div>
      {note && <div className="mt-1 text-micro text-ink-faint">{note}</div>}
    </Panel>
  );
}

export function MetricGrid({ children, columns = 3 }: { children: ReactNode; columns?: 3 | 4 }) {
  return (
    <div
      className={clsx(
        "grid grid-cols-1 gap-4 sm:grid-cols-2",
        columns === 3 ? "lg:grid-cols-3" : "lg:grid-cols-4",
      )}
    >
      {children}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Loading, empty and error
// ---------------------------------------------------------------------------

export function Skeleton({ className }: { className?: string }) {
  return <div aria-hidden className={clsx("animate-pulse rounded bg-paper-sunk", className)} />;
}

export function MetricSkeletons({ count = 6, columns = 3 }: { count?: number; columns?: 3 | 4 }) {
  return (
    <MetricGrid columns={columns}>
      {Array.from({ length: count }).map((_, n) => (
        <Panel key={n} className="px-5 py-4">
          <Skeleton className="h-4 w-24" />
          <Skeleton className="mt-3 h-9 w-20" />
          <Skeleton className="mt-2 h-3 w-32" />
        </Panel>
      ))}
    </MetricGrid>
  );
}

export function ChartSkeleton({ height = "h-56" }: { height?: string }) {
  return (
    <Panel className="p-5">
      <Skeleton className="h-4 w-36" />
      <Skeleton className={clsx("mt-4 w-full", height)} />
    </Panel>
  );
}

export function RowSkeletons({ rows = 5 }: { rows?: number }) {
  return (
    <div role="status" aria-label="Loading" className="space-y-3">
      {Array.from({ length: rows }).map((_, n) => (
        <Skeleton key={n} className="h-14 w-full" />
      ))}
    </div>
  );
}

export function EmptyState({
  title,
  description,
  action,
}: {
  title: string;
  description?: string;
  action?: ReactNode;
}) {
  return (
    <div className="rounded-md border border-dashed border-rule-strong px-6 py-14 text-center">
      <p className="text-lead text-ink">{title}</p>
      {description && <p className="mx-auto mt-2 max-w-measure text-small text-ink-soft">{description}</p>}
      {action && <div className="mt-5 flex justify-center">{action}</div>}
    </div>
  );
}

export function ErrorState({ message, onRetry }: { message: string; onRetry?: () => void }) {
  return (
    <div
      role="alert"
      className="flex flex-wrap items-start gap-3 rounded-md border-l-2 border-oxblood bg-oxblood-wash px-4 py-3 text-small text-oxblood-deep"
    >
      <AlertCircle size={16} className="mt-0.5 shrink-0" aria-hidden />
      <p className="min-w-0 flex-1">Could not load this. {message}</p>
      {onRetry && (
        <button onClick={onRetry} className="font-medium underline underline-offset-4 hover:text-oxblood">
          Try again
        </button>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Controls
// ---------------------------------------------------------------------------

export function Button({
  children,
  variant = "primary",
  busy = false,
  className,
  ...rest
}: React.ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: "primary" | "quiet" | "danger";
  busy?: boolean;
}) {
  return (
    <button
      {...rest}
      disabled={rest.disabled || busy}
      className={clsx(
        "inline-flex items-center justify-center gap-2 rounded px-4 py-2 text-small font-medium transition-colors disabled:cursor-not-allowed disabled:opacity-45",
        variant === "primary" && "bg-oxblood text-paper-raised hover:bg-oxblood-deep",
        variant === "quiet" && "border border-rule-strong bg-paper-raised text-ink-soft hover:bg-paper-sunk hover:text-ink",
        variant === "danger" && "border border-oxblood text-oxblood hover:bg-oxblood-wash",
        className,
      )}
    >
      {busy && <Loader2 size={14} className="animate-spin" aria-hidden />}
      {children}
    </button>
  );
}

export function RefreshButton({ onClick, loading }: { onClick: () => void; loading: boolean }) {
  return (
    <Button variant="quiet" onClick={onClick} disabled={loading} aria-label="Refresh">
      <RefreshCw size={14} className={clsx(loading && "animate-spin")} aria-hidden />
      Refresh
    </Button>
  );
}

// ---------------------------------------------------------------------------
// Badges
// ---------------------------------------------------------------------------

const badgeTone: Record<Tone, string> = {
  ink: "border-rule-strong bg-paper-sunk text-ink-soft",
  oxblood: "border-oxblood bg-oxblood-wash text-oxblood-deep",
  olive: "border-olive bg-olive-wash text-[#414A22]",
  ochre: "border-ochre bg-ochre-wash text-[#7A5A17]",
};

export function StatusBadge({ tone, children, title }: { tone: Tone; children: ReactNode; title?: string }) {
  return (
    <span
      title={title}
      className={clsx("inline-flex items-center gap-1.5 whitespace-nowrap border-l-2 px-2 py-0.5 text-micro font-medium", badgeTone[tone])}
    >
      {children}
    </span>
  );
}

export function TrendTag({ state }: { state: TrendState }) {
  const tone: Tone = state === "emerging" ? "ochre" : state === "recurring" ? "oxblood" : "olive";
  return (
    <StatusBadge tone={tone} title={trendCopy[state].note}>
      {trendCopy[state].label}
    </StatusBadge>
  );
}

const directionCopy: Record<Direction, { label: string; icon: typeof ArrowRight; tone: string }> = {
  growing: { label: "Growing", icon: ArrowUpRight, tone: "text-oxblood" },
  stable: { label: "Stable", icon: ArrowRight, tone: "text-ink-faint" },
  declining: { label: "Declining", icon: ArrowDownRight, tone: "text-olive" },
};

/** Direction of volume, separate from the recurring/emerging classification. */
export function TrendIndicator({ growth, showLabel = false }: { growth: number; showLabel?: boolean }) {
  const d = directionCopy[directionOf(growth)];
  const Icon = d.icon;
  return (
    <span className={clsx("inline-flex items-center gap-1 text-small", d.tone)} title={d.label}>
      <Icon size={16} aria-hidden />
      <span className={clsx(!showLabel && "sr-only")}>{d.label}</span>
    </span>
  );
}

export function PriorityBadge({ value }: { value: number }) {
  const [label, tone]: [string, Tone] =
    value >= 0.7 ? ["High", "oxblood"] : value >= 0.4 ? ["Medium", "ochre"] : ["Low", "olive"];
  return (
    <StatusBadge tone={tone} title={`Priority score ${value.toFixed(2)}`}>
      {label}
      <span className="tabular opacity-70">{value.toFixed(2)}</span>
    </StatusBadge>
  );
}

export function SeverityBadge({ value }: { value: number }) {
  const [label, tone]: [string, Tone] =
    value >= 0.7 ? ["Blocking", "oxblood"] : value >= 0.4 ? ["Annoying", "ochre"] : ["Minor", "ink"];
  return (
    <StatusBadge tone={tone} title={`Inferred severity ${value.toFixed(2)}`}>
      {label}
    </StatusBadge>
  );
}

/** Thin bar bleeding behind a row, so ranking is legible before reading. */
export function PriorityBar({ value }: { value: number }) {
  return (
    <span
      aria-hidden
      className="pointer-events-none absolute inset-y-0 left-0 bg-oxblood/[0.055]"
      style={{ width: `${Math.max(4, value * 100)}%` }}
    />
  );
}

// ---------------------------------------------------------------------------
// Dialogs
// ---------------------------------------------------------------------------

export function Dialog({
  open,
  onClose,
  title,
  description,
  children,
}: {
  open: boolean;
  onClose: () => void;
  title: string;
  description?: string;
  children: ReactNode;
}) {
  const panel = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const previous = document.activeElement as HTMLElement | null;
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    document.addEventListener("keydown", onKey);
    document.body.style.overflow = "hidden";
    // Focus the first field or button inside the dialog.
    requestAnimationFrame(() => {
      const el =
        panel.current?.querySelector<HTMLElement>("input:not([tabindex='-1']), textarea, select") ??
        panel.current?.querySelector<HTMLElement>("button:not([data-close])");
      el?.focus();
    });
    return () => {
      document.removeEventListener("keydown", onKey);
      document.body.style.overflow = "";
      previous?.focus();
    };
  }, [open, onClose]);

  if (!open) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-end justify-center p-4 sm:items-center">
      <div className="absolute inset-0 bg-ink/40" onClick={onClose} aria-hidden />
      <div
        ref={panel}
        role="dialog"
        aria-modal="true"
        aria-labelledby="dialog-title"
        className="relative w-full max-w-lg rounded-md border border-rule-strong bg-paper-raised p-6 shadow-[0_18px_48px_-24px_rgba(22,19,15,0.45)]"
      >
        <div className="flex items-start justify-between gap-4">
          <div>
            <h2 id="dialog-title" className="text-h3 font-semibold">
              {title}
            </h2>
            {description && <p className="mt-1 text-small text-ink-soft">{description}</p>}
          </div>
          <button
            data-close
            onClick={onClose}
            aria-label="Close"
            className="rounded p-1 text-ink-faint hover:bg-paper-sunk hover:text-ink"
          >
            <X size={18} />
          </button>
        </div>
        <div className="mt-5">{children}</div>
      </div>
    </div>
  );
}

export function ConfirmDialog({
  open,
  title,
  description,
  confirmLabel,
  busy,
  onConfirm,
  onClose,
}: {
  open: boolean;
  title: string;
  description: string;
  confirmLabel: string;
  busy?: boolean;
  onConfirm: () => void;
  onClose: () => void;
}) {
  return (
    <Dialog open={open} onClose={onClose} title={title} description={description}>
      <div className="flex justify-end gap-2">
        <Button variant="quiet" onClick={onClose} disabled={busy}>
          Cancel
        </Button>
        <Button onClick={onConfirm} busy={busy}>
          {confirmLabel}
        </Button>
      </div>
    </Dialog>
  );
}

export const inputClass =
  "w-full min-w-0 rounded border border-rule-strong bg-paper-raised px-3 py-2.5 text-base placeholder:text-ink-faint focus:border-oxblood focus:outline-none";
