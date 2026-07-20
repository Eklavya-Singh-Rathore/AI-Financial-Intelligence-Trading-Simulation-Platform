// Phase 6.5: indicator preset sanitization (pure).
import assert from "node:assert/strict";
import { test } from "node:test";
import { sanitizeEnabled } from "../lib/chartPresets.mjs";

const VALID = ["sma", "ema", "rsi", "macd", "vwap"];
const FALLBACK = ["sma", "rsi"];

test("non-array stored → fallback (never set / corrupt)", () => {
  assert.deepEqual(sanitizeEnabled(null, VALID, FALLBACK), ["sma", "rsi"]);
  assert.deepEqual(sanitizeEnabled("nope", VALID, FALLBACK), ["sma", "rsi"]);
  assert.deepEqual(sanitizeEnabled(undefined, VALID, FALLBACK), ["sma", "rsi"]);
});

test("valid array is filtered to known ids, order preserved", () => {
  assert.deepEqual(sanitizeEnabled(["rsi", "bogus", "vwap"], VALID, FALLBACK), ["rsi", "vwap"]);
});

test("empty array is respected (user turned everything off)", () => {
  assert.deepEqual(sanitizeEnabled([], VALID, FALLBACK), []);
});

test("all-invalid array collapses to empty, not fallback", () => {
  assert.deepEqual(sanitizeEnabled(["x", "y"], VALID, FALLBACK), []);
});

test("does not mutate the fallback", () => {
  const fb = ["sma"];
  const out = sanitizeEnabled(null, VALID, fb);
  out.push("ema");
  assert.deepEqual(fb, ["sma"]);
});
