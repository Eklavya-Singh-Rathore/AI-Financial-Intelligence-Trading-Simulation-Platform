// Chart interval definitions (Phase 6.5). Pure + node-testable. Must stay in
// sync with the backend `app/services/ohlcv.py` INTERVALS. Intraday grains come
// from yfinance (bounded history); daily/weekly/monthly from stored bars.

/** @typedef {{ id: string, label: string, intraday: boolean }} Interval */

/** @type {ReadonlyArray<Interval>} */
export const INTERVALS = [
  { id: "1m", label: "1m", intraday: true },
  { id: "5m", label: "5m", intraday: true },
  { id: "15m", label: "15m", intraday: true },
  { id: "30m", label: "30m", intraday: true },
  { id: "1H", label: "1H", intraday: true },
  { id: "1D", label: "1D", intraday: false },
  { id: "1W", label: "1W", intraday: false },
  { id: "1M", label: "1M", intraday: false },
];

export const DEFAULT_INTERVAL = "1D";

const BY_ID = Object.fromEntries(INTERVALS.map((i) => [i.id, i]));

/** @param {string} id */
export function isIntradayInterval(id) {
  return BY_ID[id]?.intraday ?? false;
}

/** @param {string} id */
export function isValidInterval(id) {
  return id in BY_ID;
}

// Range presets that make sense per interval — bounded by how much history each
// grain has (yfinance: 1m ≈ 7d, 5m/15m/30m ≈ 60d, 60m ≈ 2y). The component
// clamps further to the data actually returned.
const RANGES = {
  "1m": ["1D", "5D"],
  "5m": ["1D", "5D", "1M"],
  "15m": ["1D", "5D", "1M"],
  "30m": ["1D", "5D", "1M"],
  "1H": ["5D", "1M", "3M", "6M", "1Y"],
  "1D": ["1M", "3M", "6M", "YTD", "1Y", "3Y", "5Y", "MAX"],
  "1W": ["6M", "YTD", "1Y", "3Y", "5Y", "MAX"],
  "1M": ["1Y", "3Y", "5Y", "MAX"],
};

/** Range presets applicable to an interval; falls back to daily's set.
 *  @param {string} id
 *  @returns {string[]} */
export function rangesForInterval(id) {
  return RANGES[id] ?? RANGES["1D"];
}

/** Default range preset to select when switching to an interval.
 *  @param {string} id
 *  @returns {string} */
export function defaultRangeForInterval(id) {
  const r = rangesForInterval(id);
  // intraday → a recent window (2nd preset); daily family → a mid window (3rd).
  const idx = isIntradayInterval(id) ? 1 : 2;
  return r[Math.min(idx, r.length - 1)];
}
