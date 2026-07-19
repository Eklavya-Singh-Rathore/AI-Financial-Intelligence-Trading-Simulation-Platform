// Phase 6: chart range-preset math (pure).
import assert from "node:assert/strict";
import { test } from "node:test";
import { RANGE_PRESETS, visibleRangeFor } from "../lib/chartRanges.mjs";

const DATES = ["2023-01-02", "2024-06-14", "2026-06-17", "2026-07-17"];

test("1M window ends at the last bar, one month back", () => {
  assert.deepEqual(visibleRangeFor(DATES, "1M"), { from: "2026-06-17", to: "2026-07-17" });
});

test("1Y and 3Y subtract the right span", () => {
  assert.deepEqual(visibleRangeFor(DATES, "1Y"), { from: "2025-07-17", to: "2026-07-17" });
  assert.deepEqual(visibleRangeFor(DATES, "3Y"), { from: "2023-07-17", to: "2026-07-17" });
});

test("All and empty input return null (caller uses fitContent)", () => {
  assert.equal(visibleRangeFor(DATES, "All"), null);
  assert.equal(visibleRangeFor([], "1M"), null);
});

test("month underflow rolls the year correctly", () => {
  // Jan 15 minus 3 months -> Oct 15 previous year.
  assert.deepEqual(visibleRangeFor(["2026-01-15"], "3M"), {
    from: "2025-10-15",
    to: "2026-01-15",
  });
});

test("presets list is stable", () => {
  assert.deepEqual([...RANGE_PRESETS], ["1M", "3M", "6M", "1Y", "3Y", "All"]);
});
