// Phase 6: nav active-route + page-title logic (pure).
import assert from "node:assert/strict";
import { test } from "node:test";
import { isActive, pageTitle } from "../lib/nav.mjs";

const ROUTES = [
  { href: "/", label: "Dashboard" },
  { href: "/simulation", label: "Simulation" },
  { href: "/agents", label: "Agents" },
  { href: "/insights", label: "Insights" },
];

test("root matches only itself", () => {
  assert.equal(isActive("/", "/"), true);
  assert.equal(isActive("/agents", "/"), false);
});

test("section matches exact path and sub-paths, not sibling prefixes", () => {
  assert.equal(isActive("/agents", "/agents"), true);
  assert.equal(isActive("/agents/123", "/agents"), true);
  assert.equal(isActive("/agentsfoo", "/agents"), false);
  assert.equal(isActive("/simulation", "/agents"), false);
});

test("pageTitle picks the matching nav label", () => {
  assert.equal(pageTitle("/", ROUTES), "Dashboard");
  assert.equal(pageTitle("/agents/abc", ROUTES), "Agents");
  assert.equal(pageTitle("/simulation", ROUTES), "Simulation");
});

test("pageTitle is empty for routes not in the nav (e.g. instrument detail)", () => {
  assert.equal(pageTitle("/instruments/RELIANCE", ROUTES), "");
});
