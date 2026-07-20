// Support/resistance detection (Phase 6.5). Pure + node-testable. Finds swing
// pivots (local extrema over a window) and returns the nearest levels above
// (resistance) and below (support) the latest close.

/**
 * @param {ReadonlyArray<{high:number,low:number,close:number}>} bars ascending
 * @param {{window?:number, max?:number}} [opts]
 * @returns {Array<{price:number, kind:"support"|"resistance"}>}
 */
export function supportResistance(bars, opts = {}) {
  const window = opts.window ?? 5;
  const max = opts.max ?? 3;
  if (!bars || bars.length < window * 2 + 1) return [];
  const highs = [];
  const lows = [];
  for (let i = window; i < bars.length - window; i++) {
    const h = bars[i].high;
    const l = bars[i].low;
    let isHigh = true;
    let isLow = true;
    for (let j = i - window; j <= i + window; j++) {
      if (bars[j].high > h) isHigh = false;
      if (bars[j].low < l) isLow = false;
    }
    if (isHigh) highs.push(h);
    if (isLow) lows.push(l);
  }
  const last = bars[bars.length - 1].close;
  const res = [...new Set(highs)]
    .filter((p) => p > last)
    .sort((a, b) => a - b)
    .slice(0, max)
    .map((price) => ({ price, kind: "resistance" }));
  const sup = [...new Set(lows)]
    .filter((p) => p < last)
    .sort((a, b) => b - a)
    .slice(0, max)
    .map((price) => ({ price, kind: "support" }));
  return [...res, ...sup];
}
