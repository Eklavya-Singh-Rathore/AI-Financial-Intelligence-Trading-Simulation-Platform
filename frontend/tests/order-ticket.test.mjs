// Phase 6: order-ticket estimate + validation (pure).
import assert from "node:assert/strict";
import { test } from "node:test";
import { estimatedCost, validateOrder } from "../lib/orderTicket.mjs";

test("estimatedCost uses limit price for limit orders, last price otherwise", () => {
  assert.equal(estimatedCost("market", 10, 100, undefined), 1000);
  assert.equal(estimatedCost("limit", 10, 100, 90), 900);
  assert.equal(estimatedCost("market", 0, 100, undefined), null);
});

test("valid market buy within buying power", () => {
  const r = validateOrder({ side: "buy", orderType: "market", qty: 5, buyingPower: 10000, lastPrice: 100 });
  assert.equal(r.ok, true);
  assert.equal(r.cost, 500);
});

test("buy exceeding buying power is rejected", () => {
  const r = validateOrder({ side: "buy", orderType: "market", qty: 200, buyingPower: 1000, lastPrice: 100 });
  assert.equal(r.ok, false);
  assert.match(r.reason, /buying power/);
});

test("limit order requires a limit price; stop requires a stop price", () => {
  assert.equal(validateOrder({ side: "buy", orderType: "limit", qty: 1, lastPrice: 10 }).ok, false);
  assert.equal(validateOrder({ side: "sell", orderType: "stop", qty: 1, lastPrice: 10 }).ok, false);
  assert.equal(
    validateOrder({ side: "buy", orderType: "limit", qty: 1, limitPrice: 9, buyingPower: 100, lastPrice: 10 }).ok,
    true,
  );
});

test("qty below 1 is rejected", () => {
  assert.equal(validateOrder({ side: "buy", orderType: "market", qty: 0, lastPrice: 10 }).ok, false);
});

test("sell is not blocked by buying power", () => {
  const r = validateOrder({ side: "sell", orderType: "market", qty: 999, buyingPower: 0, lastPrice: 100 });
  assert.equal(r.ok, true);
});
