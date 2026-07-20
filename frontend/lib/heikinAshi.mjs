// Heikin-Ashi candle transform (Phase 6.5). Pure + node-testable.
// HA smooths OHLC to emphasize trend; each bar depends on the previous HA bar.

/**
 * @template {{open:number,high:number,low:number,close:number}} T
 * @param {ReadonlyArray<T>} bars ascending
 * @returns {T[]} same length, HA-transformed (other fields preserved)
 */
export function heikinAshi(bars) {
  const out = [];
  let prevOpen;
  let prevClose;
  for (const b of bars) {
    const close = (b.open + b.high + b.low + b.close) / 4;
    const open = prevOpen === undefined ? (b.open + b.close) / 2 : (prevOpen + prevClose) / 2;
    const high = Math.max(b.high, open, close);
    const low = Math.min(b.low, open, close);
    out.push({ ...b, open, high, low, close });
    prevOpen = open;
    prevClose = close;
  }
  return out;
}
