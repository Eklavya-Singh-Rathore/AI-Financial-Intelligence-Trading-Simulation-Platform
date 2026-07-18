// Trade-to-chart-marker mapping (Phase 6). Pure + node-testable; the hook feeds
// theme colors in. Buy = up-arrow below the bar (gain), sell = down-arrow above
// (loss). Markers must be time-ascending for lightweight-charts.

/** @param {string} date @returns {number} UTCTimestamp seconds */
function toT(date) {
  return Math.floor(Date.parse(date + "T00:00:00Z") / 1000);
}

/**
 * @param {ReadonlyArray<{date: string, side: string, qty: number, price: number}>} trades
 * @param {{gain: string, loss: string}} colors
 * @returns {Array<{time:number, position:string, color:string, shape:string, text:string}>}
 */
export function tradesToMarkers(trades, colors) {
  return trades
    .map((t) => ({ t, time: toT(t.date) }))
    .sort((a, b) => a.time - b.time)
    .map(({ t, time }) => {
      const buy = t.side === "buy";
      return {
        time,
        position: buy ? "belowBar" : "aboveBar",
        color: buy ? colors.gain : colors.loss,
        shape: buy ? "arrowUp" : "arrowDown",
        text: `${buy ? "B" : "S"} ${t.qty}`,
      };
    });
}
