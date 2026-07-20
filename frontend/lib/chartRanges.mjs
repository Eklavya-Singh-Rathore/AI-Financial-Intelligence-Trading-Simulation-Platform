// Chart visible-range presets (Phase 6 → 6.5). Pure: computed from the bar time
// list so it's node-testable; the component maps the returned strings to chart
// times via toTime(). Times may be dates ("2026-07-17") or intraday datetimes
// ("2026-07-20T09:15:00").

const DAYS = { "1D": 1, "5D": 5 };
const MONTHS = { "1M": 1, "3M": 3, "6M": 6, "1Y": 12, "3Y": 36, "5Y": 60 };

/** @type {ReadonlyArray<string>} full ordered preset set (component filters per interval) */
export const RANGE_PRESETS = ["1D", "5D", "1M", "3M", "6M", "YTD", "1Y", "3Y", "5Y", "MAX"];

/** Normalize a bar time string to a Date-parseable ISO (matches toTime). */
function toIso(s) {
  if (s.length <= 10) return `${s}T00:00:00Z`;
  return /[zZ]|[+-]\d\d:?\d\d$/.test(s) ? s : `${s}Z`;
}

/**
 * Compute the {from, to} window for a preset, given ascending bar times.
 * Returns null for "MAX" (or empty input) — caller should fitContent() then.
 * @param {ReadonlyArray<string>} times ascending ISO date/datetime strings
 * @param {string} preset one of RANGE_PRESETS
 * @returns {{from: string, to: string} | null}
 */
export function visibleRangeFor(times, preset) {
  if (!times || times.length === 0) return null;
  if (preset === "MAX") return null;
  const to = times[times.length - 1];
  const d = new Date(toIso(to));
  if (Number.isNaN(d.getTime())) return null;

  if (preset === "YTD") {
    return { from: `${d.getUTCFullYear()}-01-01`, to };
  }
  if (DAYS[preset] != null) {
    d.setUTCDate(d.getUTCDate() - DAYS[preset]);
    return { from: d.toISOString(), to };
  }
  const months = MONTHS[preset];
  if (months == null) return null;
  d.setUTCMonth(d.getUTCMonth() - months);
  return { from: d.toISOString(), to };
}
