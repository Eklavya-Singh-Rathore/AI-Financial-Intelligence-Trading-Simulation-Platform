// Phase 6: dashboard table sorting (pure).
import assert from "node:assert/strict";
import { test } from "node:test";
import { nextSort, sortRows } from "../lib/tableSort.mjs";

const ROWS = [
  { symbol: "TCS", change: 2.5 },
  { symbol: "gold", change: null },
  { symbol: "INFY", change: -1.2 },
  { symbol: "RELIANCE", change: 0.4 },
];

test("nextSort cycles asc -> desc -> off, switches columns to asc", () => {
  let s = nextSort(null, "change");
  assert.deepEqual(s, { key: "change", dir: "asc" });
  s = nextSort(s, "change");
  assert.deepEqual(s, { key: "change", dir: "desc" });
  s = nextSort(s, "change");
  assert.equal(s, null);
  assert.deepEqual(nextSort({ key: "change", dir: "desc" }, "symbol"), { key: "symbol", dir: "asc" });
});

test("numeric sort with nulls always last", () => {
  const asc = sortRows(ROWS, { key: "change", dir: "asc" }).map((r) => r.symbol);
  assert.deepEqual(asc, ["INFY", "RELIANCE", "TCS", "gold"]);
  const desc = sortRows(ROWS, { key: "change", dir: "desc" }).map((r) => r.symbol);
  assert.deepEqual(desc, ["TCS", "RELIANCE", "INFY", "gold"]);
});

test("string sort is case-insensitive", () => {
  const asc = sortRows(ROWS, { key: "symbol", dir: "asc" }).map((r) => r.symbol);
  assert.deepEqual(asc, ["gold", "INFY", "RELIANCE", "TCS"]);
});

test("null state returns a copy in original order", () => {
  const out = sortRows(ROWS, null);
  assert.deepEqual(out, ROWS);
  assert.notEqual(out, ROWS);
});
