// Phase 6 → 6.5: chart range-preset math (pure).
import assert from "node:assert/strict";
import { test } from "node:test";
import { RANGE_PRESETS, visibleRangeFor } from "../lib/chartRanges.mjs";

const DATES = ["2023-01-02", "2024-06-14", "2026-06-17", "2026-07-17"];

test("month presets end at the last bar, N months back", () => {
  assert.deepEqual(visibleRangeFor(DATES, "1M"), { from: "2026-06-17T00:00:00.000Z", to: "2026-07-17" });
  assert.deepEqual(visibleRangeFor(DATES, "1Y"), { from: "2025-07-17T00:00:00.000Z", to: "2026-07-17" });
  assert.deepEqual(visibleRangeFor(DATES, "3Y"), { from: "2023-07-17T00:00:00.000Z", to: "2026-07-17" });
});

test("day presets subtract days (used by intraday intervals)", () => {
  assert.deepEqual(visibleRangeFor(DATES, "5D"), { from: "2026-07-12T00:00:00.000Z", to: "2026-07-17" });
});

test("YTD starts at Jan 1 of the last bar's year", () => {
  assert.deepEqual(visibleRangeFor(DATES, "YTD"), { from: "2026-01-01", to: "2026-07-17" });
});

test("MAX and empty input return null (caller uses fitContent)", () => {
  assert.equal(visibleRangeFor(DATES, "MAX"), null);
  assert.equal(visibleRangeFor([], "1M"), null);
});

test("works with intraday datetime strings", () => {
  const times = ["2026-07-20T09:15:00", "2026-07-20T09:20:00", "2026-07-20T14:30:00"];
  const r = visibleRangeFor(times, "1D");
  assert.equal(r.to, "2026-07-20T14:30:00");
  assert.equal(r.from, "2026-07-19T14:30:00.000Z"); // last minus 1 day
});

test("month underflow rolls the year", () => {
  assert.deepEqual(visibleRangeFor(["2026-01-15"], "3M"), {
    from: "2025-10-15T00:00:00.000Z",
    to: "2026-01-15",
  });
});

test("presets list is the expanded set", () => {
  assert.deepEqual([...RANGE_PRESETS], ["1D", "5D", "1M", "3M", "6M", "YTD", "1Y", "3Y", "5Y", "MAX"]);
});
