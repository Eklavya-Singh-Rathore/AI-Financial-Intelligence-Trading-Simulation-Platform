// Shared lightweight-charts helpers (Phase 6). Used by TradingChart and the
// portfolio charts so theming + time mapping stay consistent.
import type { UTCTimestamp } from "lightweight-charts";

/** Read a CSS custom property off <body> (chart colors follow the theme). */
export function cssVar(name: string, fallback = ""): string {
  if (typeof document === "undefined") return fallback;
  const v = getComputedStyle(document.body).getPropertyValue(name).trim();
  return v || fallback;
}

export type ChartColors = ReturnType<typeof chartColors>;

export function chartColors() {
  return {
    gain: cssVar("--gain", "#059669"),
    loss: cssVar("--loss", "#dc2626"),
    accent: cssVar("--accent", "#2563eb"),
    ink3: cssVar("--ink-3", "#94a3b8"),
    border: cssVar("--border", "#e2e8f0"),
    surface: cssVar("--surface", "#ffffff"),
  };
}

/** Daily-bar date string ("2026-07-17") → chart UTCTimestamp (seconds). */
export function toTime(date: string): UTCTimestamp {
  return (new Date(date + "T00:00:00Z").getTime() / 1000) as UTCTimestamp;
}

/** 8-digit hex from a 6-digit hex + 0–255 alpha (chart series need rgba-ish). */
export function withAlpha(hex: string, alpha: number): string {
  const a = Math.max(0, Math.min(255, Math.round(alpha)))
    .toString(16)
    .padStart(2, "0");
  return `${hex}${a}`;
}
