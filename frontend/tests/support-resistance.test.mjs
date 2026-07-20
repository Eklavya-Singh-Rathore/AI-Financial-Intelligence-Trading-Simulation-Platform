// Phase 6.5: support/resistance pivot detection (pure).
import assert from "node:assert/strict";
import { test } from "node:test";
import { supportResistance } from "../lib/supportResistance.mjs";

// helper: bar with high/low around a close
const bar = (c, spread = 0.5) => ({ high: c + spread, low: c - spread, close: c });

test("empty / too-short input returns nothing", () => {
  assert.deepEqual(supportResistance([], { window: 2 }), []);
  assert.deepEqual(supportResistance([bar(10), bar(11)], { window: 2 }), []);
});

test("finds a resistance pivot above the last close and support below", () => {
  // a clear peak at index 4 (high ~120) and trough at index 10 (low ~90),
  // ending below the peak and above the trough.
  const closes = [100, 105, 110, 115, 120, 115, 110, 105, 100, 95, 90, 95, 100, 105, 108];
  const bars = closes.map((c) => bar(c));
  const sr = supportResistance(bars, { window: 3, max: 3 });
  const res = sr.filter((x) => x.kind === "resistance");
  const sup = sr.filter((x) => x.kind === "support");
  assert.ok(res.length >= 1, "has resistance");
  assert.ok(sup.length >= 1, "has support");
  // resistance is above the last close (108); support below
  assert.ok(res.every((r) => r.price > 108));
  assert.ok(sup.every((s) => s.price < 108));
});

test("levels are ordered nearest-first from the last close", () => {
  const closes = [50, 60, 70, 80, 90, 80, 70, 60, 55, 50, 45, 50, 55, 58, 60];
  const sr = supportResistance(closes.map((c) => bar(c)), { window: 3, max: 3 });
  const res = sr.filter((x) => x.kind === "resistance").map((r) => r.price);
  // ascending (nearest resistance above close first)
  assert.deepEqual([...res].sort((a, b) => a - b), res);
});
