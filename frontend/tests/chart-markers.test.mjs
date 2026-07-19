// Phase 6: trade -> chart marker mapping (pure).
import assert from "node:assert/strict";
import { test } from "node:test";
import { tradesToMarkers } from "../lib/chartMarkers.mjs";

const COLORS = { gain: "#0a0", loss: "#a00" };

test("buy and sell map to the right shape/position/color/text", () => {
  const m = tradesToMarkers(
    [
      { date: "2026-07-10", side: "buy", qty: 5, price: 100 },
      { date: "2026-07-12", side: "sell", qty: 3, price: 110 },
    ],
    COLORS,
  );
  assert.equal(m.length, 2);
  assert.deepEqual(
    { position: m[0].position, shape: m[0].shape, color: m[0].color, text: m[0].text },
    { position: "belowBar", shape: "arrowUp", color: "#0a0", text: "B 5" },
  );
  assert.deepEqual(
    { position: m[1].position, shape: m[1].shape, color: m[1].color, text: m[1].text },
    { position: "aboveBar", shape: "arrowDown", color: "#a00", text: "S 3" },
  );
});

test("markers come out time-ascending regardless of input order", () => {
  const m = tradesToMarkers(
    [
      { date: "2026-07-12", side: "sell", qty: 1, price: 1 },
      { date: "2026-07-01", side: "buy", qty: 1, price: 1 },
    ],
    COLORS,
  );
  assert.ok(m[0].time < m[1].time);
});

test("empty trades -> empty markers", () => {
  assert.deepEqual(tradesToMarkers([], COLORS), []);
});
