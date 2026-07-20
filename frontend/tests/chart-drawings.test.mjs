// Phase 6.5: drawing geometry + volume-profile math (pure).
import assert from "node:assert/strict";
import { test } from "node:test";
import {
  distToSegment,
  fibPrices,
  measureStats,
  volumeProfile,
} from "../lib/chartDrawings.mjs";

test("fib retracement spans p0..p1 with standard levels", () => {
  const f = fibPrices(100, 200);
  assert.equal(f[0].price, 100); // 0.0
  assert.equal(f[f.length - 1].price, 200); // 1.0
  const half = f.find((x) => x.level === 0.5);
  assert.equal(half.price, 150);
  const g = f.find((x) => x.level === 0.618);
  assert.ok(Math.abs(g.price - 161.8) < 1e-9);
});

test("measure stats: delta price, percent, bars", () => {
  const m = measureStats(100, 110, 3, 8);
  assert.equal(m.dPrice, 10);
  assert.ok(Math.abs(m.dPct - 10) < 1e-9);
  assert.equal(m.dBars, 5);
});

test("distToSegment: point on the line is ~0, off the line is the gap", () => {
  assert.ok(distToSegment(5, 0, 0, 0, 10, 0) < 1e-9); // on horizontal segment
  assert.equal(distToSegment(5, 3, 0, 0, 10, 0), 3); // 3px above
  // beyond the endpoint clamps to the endpoint distance
  assert.equal(distToSegment(-4, 0, 0, 0, 10, 0), 4);
});

test("volumeProfile buckets volume by typical price and normalizes", () => {
  const bars = [
    { high: 11, low: 9, close: 10, volume: 100 }, // tp=10
    { high: 21, low: 19, close: 20, volume: 300 }, // tp=20
    { high: 11, low: 9, close: 10, volume: 50 }, // tp=10
  ];
  const bk = volumeProfile(bars, 10);
  const total = bk.reduce((s, b) => s + b.volume, 0);
  assert.equal(total, 450);
  // the 20-price bucket holds the biggest single volume (300) → frac 1
  const top = bk.reduce((a, b) => (b.volume > a.volume ? b : a));
  assert.equal(top.volume, 300);
  assert.equal(top.frac, 1);
  assert.ok(top.mid > 15); // it's the high-price bucket
});

test("volumeProfile handles empty / flat input", () => {
  assert.deepEqual(volumeProfile([], 10), []);
  assert.deepEqual(volumeProfile([{ high: 5, low: 5, close: 5, volume: 9 }], 10), []); // no range
});
