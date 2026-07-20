// Drawing-tool geometry, serialization, and volume-profile math (Phase 6.5).
// Pure + node-testable. Anchors are stored in data space ({ time, price });
// the DrawingCanvas maps them to pixels via the chart's coordinate converters.

/** Tools that need two anchor points (click-drag). */
export const TWO_POINT_TOOLS = ["trendline", "ray", "rectangle", "fib", "measure", "long", "short"];
/** Tools that need one anchor point (single click). */
export const ONE_POINT_TOOLS = ["horizontal", "vertical", "text", "callout"];
export const ALL_TOOLS = [...TWO_POINT_TOOLS, ...ONE_POINT_TOOLS];

export const FIB_LEVELS = [0, 0.236, 0.382, 0.5, 0.618, 0.786, 1];

/** Fibonacci retracement prices from p0 (0.0) to p1 (1.0). */
export function fibPrices(price0, price1) {
  return FIB_LEVELS.map((level) => ({ level, price: price0 + (price1 - price0) * level }));
}

/** Measure-tool stats between two anchors (+ bar-index distance). */
export function measureStats(price0, price1, barIdx0, barIdx1) {
  const dPrice = price1 - price0;
  const dPct = price0 ? (dPrice / price0) * 100 : 0;
  const dBars = Math.abs((barIdx1 ?? 0) - (barIdx0 ?? 0));
  return { dPrice, dPct, dBars };
}

/** Long/short position risk-reward: entry=p0.price, target/stop=p1.price by side. */
export function positionStats(entry, other, side) {
  // long: target above / stop below is drawn by the user dragging; we report the
  // reward (|other-entry|) vs a symmetric risk marker. Kept simple: R:R from the
  // drawn leg vs an equal opposite leg.
  const reward = other - entry;
  const rr = entry ? (Math.abs(reward) / Math.abs(entry * 0.01) || 0) : 0;
  const pct = entry ? (reward / entry) * 100 : 0;
  return { side, reward, pct, rr };
}

/** Perpendicular distance from point (px,py) to segment (x1,y1)-(x2,y2). */
export function distToSegment(px, py, x1, y1, x2, y2) {
  const dx = x2 - x1;
  const dy = y2 - y1;
  const len2 = dx * dx + dy * dy;
  if (len2 === 0) return Math.hypot(px - x1, py - y1);
  let t = ((px - x1) * dx + (py - y1) * dy) / len2;
  t = Math.max(0, Math.min(1, t));
  return Math.hypot(px - (x1 + t * dx), py - (y1 + t * dy));
}

/** localStorage key for a symbol's drawings. */
export function drawingsKey(symbol) {
  return `chart_drawings_${symbol}`;
}

export function loadDrawings(symbol) {
  try {
    const raw = localStorage.getItem(drawingsKey(symbol));
    const parsed = raw ? JSON.parse(raw) : [];
    return Array.isArray(parsed) ? parsed : [];
  } catch {
    return [];
  }
}

export function saveDrawings(symbol, drawings) {
  try {
    localStorage.setItem(drawingsKey(symbol), JSON.stringify(drawings));
  } catch {
    /* storage unavailable */
  }
}

/**
 * Volume-by-price histogram (pure). Buckets the [min low, max high] range and
 * adds each bar's volume to the bucket of its typical price. Returns buckets
 * oldest→highest price with a `volume` and normalized `frac` (0..1 of max).
 * @param {ReadonlyArray<{high:number,low:number,close:number,volume:number}>} bars
 * @param {number} nBuckets
 */
export function volumeProfile(bars, nBuckets = 24) {
  if (!bars || bars.length === 0) return [];
  let min = Infinity;
  let max = -Infinity;
  for (const b of bars) {
    if (b.low < min) min = b.low;
    if (b.high > max) max = b.high;
  }
  if (!(max > min)) return [];
  const step = (max - min) / nBuckets;
  const buckets = Array.from({ length: nBuckets }, (_, i) => ({
    lo: min + i * step,
    hi: min + (i + 1) * step,
    mid: min + (i + 0.5) * step,
    volume: 0,
    frac: 0,
  }));
  for (const b of bars) {
    const tp = (b.high + b.low + b.close) / 3;
    let idx = Math.floor((tp - min) / step);
    if (idx < 0) idx = 0;
    if (idx >= nBuckets) idx = nBuckets - 1;
    buckets[idx].volume += b.volume;
  }
  const maxVol = buckets.reduce((m, x) => Math.max(m, x.volume), 0) || 1;
  for (const x of buckets) x.frac = x.volume / maxVol;
  return buckets;
}
