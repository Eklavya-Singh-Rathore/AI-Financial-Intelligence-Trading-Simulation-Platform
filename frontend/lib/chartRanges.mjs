// Chart visible-range presets (Phase 6). Pure: computed from the bar date list
// so it's node-testable; the component maps the returned dates to chart times.

const MONTHS = { "1M": 1, "3M": 3, "6M": 6, "1Y": 12, "3Y": 36 };

/** @type {ReadonlyArray<string>} */
export const RANGE_PRESETS = ["1M", "3M", "6M", "1Y", "3Y", "All"];

/**
 * Compute the {from, to} date window for a preset, given ascending bar dates.
 * Returns null for "All" (or empty input) — caller should fitContent() then.
 * @param {ReadonlyArray<string>} dates ascending ISO date strings
 * @param {string} preset one of RANGE_PRESETS
 * @returns {{from: string, to: string} | null}
 */
export function visibleRangeFor(dates, preset) {
  if (!dates || dates.length === 0) return null;
  if (preset === "All") return null;
  const months = MONTHS[preset];
  if (!months) return null;
  const to = dates[dates.length - 1];
  const d = new Date(to + "T00:00:00Z");
  d.setUTCMonth(d.getUTCMonth() - months);
  const from = d.toISOString().slice(0, 10);
  return { from, to };
}
