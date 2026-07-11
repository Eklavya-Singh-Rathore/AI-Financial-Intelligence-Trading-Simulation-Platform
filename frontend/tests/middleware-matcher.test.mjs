// Regression test (Phase 4.6): the auth middleware must NOT run on the guest
// sign-in route or the backend proxy, otherwise an unauthenticated request to
// establish a guest session is redirected to /login and guest login breaks.
// Uses only Node's built-in test runner + fs (no extra dependencies).
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";
import { test } from "node:test";

const here = dirname(fileURLToPath(import.meta.url));
const src = readFileSync(join(here, "..", "middleware.ts"), "utf8");

// Extract the real matcher pattern string from the source.
const m = src.match(/matcher:\s*\[\s*"([^"]+)"\s*\]/);
assert.ok(m, "could not find the middleware matcher pattern in middleware.ts");
const matcher = new RegExp("^" + m[1] + "$");

// Next.js runs the middleware only when the path MATCHES the matcher regex.
const runsOn = (path) => matcher.test(path);

test("middleware skips the guest sign-in route", () => {
  assert.equal(runsOn("/api/guest"), false);
});

test("middleware skips the backend proxy", () => {
  assert.equal(runsOn("/api/backend/health"), false);
});

test("middleware still guards real app pages", () => {
  for (const p of ["/", "/agents", "/chat", "/instruments/RELIANCE"]) {
    assert.equal(runsOn(p), true, `expected middleware to guard ${p}`);
  }
});
