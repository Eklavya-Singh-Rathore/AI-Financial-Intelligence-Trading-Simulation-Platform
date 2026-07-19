// Phase 6: command-palette local filter (pure).
import assert from "node:assert/strict";
import { test } from "node:test";
import { filterInstruments } from "../lib/search.mjs";

const ITEMS = [
  { symbol: "RELIANCE", display_name: "Reliance Industries Ltd" },
  { symbol: "INFY", display_name: "Infosys Ltd" },
  { symbol: "TCS", display_name: "Tata Consultancy Services" },
  { symbol: "TATAMOTORS", display_name: "Tata Motors" },
];

test("empty query returns nothing", () => {
  assert.deepEqual(filterInstruments(ITEMS, "  "), []);
});

test("matches symbol and name substrings", () => {
  const tata = filterInstruments(ITEMS, "tata").map((i) => i.symbol);
  assert.ok(tata.includes("TCS")); // name "Tata Consultancy"
  assert.ok(tata.includes("TATAMOTORS"));
});

test("symbol-prefix ranks before name-only match", () => {
  const res = filterInstruments(ITEMS, "tata").map((i) => i.symbol);
  // TATAMOTORS (symbol prefix) should rank above TCS (name-only).
  assert.ok(res.indexOf("TATAMOTORS") < res.indexOf("TCS"));
});

test("respects the limit", () => {
  assert.equal(filterInstruments(ITEMS, "l", 2).length, 2);
});
