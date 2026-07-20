// Phase 6.5: chart interval config (pure).
import assert from "node:assert/strict";
import { test } from "node:test";
import {
  DEFAULT_INTERVAL,
  INTERVALS,
  defaultRangeForInterval,
  isIntradayInterval,
  isValidInterval,
  rangesForInterval,
} from "../lib/chartIntervals.mjs";

test("interval set matches the backend resolver", () => {
  assert.deepEqual(INTERVALS.map((i) => i.id), ["1m", "5m", "15m", "30m", "1H", "1D", "1W", "1M"]);
  assert.equal(DEFAULT_INTERVAL, "1D");
});

test("intraday classification", () => {
  assert.equal(isIntradayInterval("5m"), true);
  assert.equal(isIntradayInterval("1H"), true);
  assert.equal(isIntradayInterval("1D"), false);
  assert.equal(isIntradayInterval("1W"), false);
  assert.equal(isIntradayInterval("nope"), false);
});

test("validity", () => {
  assert.equal(isValidInterval("1H"), true);
  assert.equal(isValidInterval("2H"), false);
});

test("ranges are interval-appropriate", () => {
  assert.deepEqual(rangesForInterval("1m"), ["1D", "5D"]);
  assert.ok(rangesForInterval("1D").includes("MAX"));
  assert.ok(!rangesForInterval("1m").includes("1Y"));
  assert.deepEqual(rangesForInterval("bogus"), rangesForInterval("1D")); // fallback
});

test("default range per interval", () => {
  assert.equal(defaultRangeForInterval("1m"), "5D"); // intraday → recent window
  assert.equal(defaultRangeForInterval("1D"), "6M"); // daily → mid window
});
