// Phase 6.5: Heikin-Ashi transform (pure).
import assert from "node:assert/strict";
import { test } from "node:test";
import { heikinAshi } from "../lib/heikinAshi.mjs";

test("first bar seeds open from (open+close)/2", () => {
  const ha = heikinAshi([{ open: 10, high: 14, low: 9, close: 12 }]);
  assert.equal(ha[0].close, (10 + 14 + 9 + 12) / 4); // 11.25
  assert.equal(ha[0].open, (10 + 12) / 2); // 11
  assert.equal(ha[0].high, Math.max(14, 11, 11.25)); // 14
  assert.equal(ha[0].low, Math.min(9, 11, 11.25)); // 9
});

test("second bar open is the mean of the previous HA open/close", () => {
  const ha = heikinAshi([
    { open: 10, high: 14, low: 9, close: 12 },
    { open: 12, high: 16, low: 11, close: 15 },
  ]);
  assert.equal(ha[1].open, (ha[0].open + ha[0].close) / 2); // (11 + 11.25)/2
  assert.equal(ha[1].close, (12 + 16 + 11 + 15) / 4); // 13.5
});

test("preserves extra fields (date/volume) and length", () => {
  const bars = [{ date: "2026-07-17", volume: 100, open: 10, high: 14, low: 9, close: 12 }];
  const ha = heikinAshi(bars);
  assert.equal(ha.length, 1);
  assert.equal(ha[0].date, "2026-07-17");
  assert.equal(ha[0].volume, 100);
});

test("empty input yields empty output", () => {
  assert.deepEqual(heikinAshi([]), []);
});
