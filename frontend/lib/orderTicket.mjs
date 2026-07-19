// Order-ticket estimate + validation (Phase 6). Pure, mirrors the backend
// rules in schemas/simulation.py so the UI can pre-validate before submit.

/**
 * Estimated order cost (₹). Uses the limit price for limit orders, else the
 * latest close. Null when the driving price/qty is unknown.
 */
export function estimatedCost(orderType, qty, lastPrice, limitPrice) {
  const price = orderType === "limit" ? limitPrice : lastPrice;
  if (!price || !qty || qty < 1) return null;
  return price * qty;
}

/**
 * @returns {{ ok: boolean, reason?: string, cost: number | null }}
 */
export function validateOrder({
  side,
  orderType,
  qty,
  limitPrice,
  stopPrice,
  buyingPower,
  lastPrice,
}) {
  const cost = estimatedCost(orderType, qty, lastPrice, limitPrice);
  if (!qty || qty < 1) return { ok: false, reason: "quantity must be at least 1", cost };
  if (orderType === "limit" && !(limitPrice > 0))
    return { ok: false, reason: "limit price required", cost };
  if (orderType === "stop" && !(stopPrice > 0))
    return { ok: false, reason: "stop price required", cost };
  if (side === "buy" && cost != null && buyingPower != null && cost > buyingPower)
    return { ok: false, reason: "estimated cost exceeds buying power", cost };
  return { ok: true, cost };
}
