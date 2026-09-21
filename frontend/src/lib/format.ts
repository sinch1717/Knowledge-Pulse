import { useCallback, useEffect, useState } from "react";
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

/**
 * Minimal async hook. No cache, no retries — the app only reads a handful of
 * endpoints. `reload` re-runs the request and keeps the previous data on screen
 * while it does, so a refresh never flashes an empty page.
 */
export function useAsync<T>(fn: () => Promise<T>, deps: unknown[] = []) {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [tick, setTick] = useState(0);

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
  }, [...deps, tick]);

  const reload = useCallback(() => setTick((t) => t + 1), []);

  return { data, error, loading, reload };
}

/** "2 hours ago", "3 days ago". Falls back to a date past a month. */
export const relativeTime = (iso: string | null) => {
  if (!iso) return "never";
  const seconds = Math.round((Date.now() - new Date(iso).getTime()) / 1000);
  if (seconds < 60) return "just now";
  const units: [number, string][] = [
    [60 * 60 * 24 * 30, ""],
    [60 * 60 * 24, "day"],
    [60 * 60, "hour"],
    [60, "minute"],
  ];
  for (const [size, name] of units) {
    if (seconds >= size) {
      if (!name) return dateLabel(iso);
      const n = Math.floor(seconds / size);
      return `${n} ${name}${n === 1 ? "" : "s"} ago`;
    }
  }
  return "just now";
};

export type Direction = "growing" | "stable" | "declining";

/** Growth within ±5% reads as stable. */
export const directionOf = (growth: number): Direction =>
  growth > 0.05 ? "growing" : growth < -0.05 ? "declining" : "stable";

/** Confidence below this is treated as "answered poorly" everywhere in the app. */
export const WEAK_CONFIDENCE = 0.4;
