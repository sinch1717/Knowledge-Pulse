import { useEffect, useState } from "react";
import type { ActionCategory, TrendState } from "@/lib/types";

export const pct = (n: number, digits = 0) => `${(n * 100).toFixed(digits)}%`;

export const growthLabel = (g: number) => {
  if (Math.abs(g) < 0.02) return "level";
  const sign = g > 0 ? "+" : "";
  return g >= 1 ? `${sign}${g.toFixed(1)}×` : `${sign}${Math.round(g * 100)}%`;
};

export const dateLabel = (iso: string | null) => {
  if (!iso) return "never";
  return new Date(iso).toLocaleDateString("en-GB", {
    day: "numeric",
    month: "short",
    year: "numeric",
  });
};

export const trendCopy: Record<TrendState, { label: string; note: string }> = {
  emerging: { label: "Emerging", note: "New or rising sharply from a low base" },
  recurring: { label: "Recurring", note: "Present across periods without resolution" },
  stable: { label: "Stable", note: "Present and unchanged" },
};

export const categoryCopy: Record<ActionCategory, { label: string; note: string }> = {
  product: { label: "Change the product", note: "The difficulty is in the product, not the explanation" },
  documentation: { label: "Fix the documentation", note: "Named page or section to add or correct" },
  faq: { label: "Add to the FAQ", note: "Draft answer in the customers' own phrasing" },
  customer_issue: { label: "Reply directly", note: "Individual conversations left unresolved" },
};

/** Minimal async hook. No cache, no retries — the app only reads a handful of endpoints. */
export function useAsync<T>(fn: () => Promise<T>, deps: unknown[] = []) {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let live = true;
    setLoading(true);
    setError(null);
    fn()
      .then((d) => live && setData(d))
      .catch((e: Error) => live && setError(e.message))
      .finally(() => live && setLoading(false));
    return () => {
      live = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps);

  return { data, error, loading };
}
