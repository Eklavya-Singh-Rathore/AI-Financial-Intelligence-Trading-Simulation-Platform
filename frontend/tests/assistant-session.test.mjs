// Phase 6: floating-assistant session resolution + route prefixing (pure).
import assert from "node:assert/strict";
import { test } from "node:test";
import { resolveAssistantSession, withRouteContext } from "../lib/assistantSession.mjs";

const SESSIONS = [{ id: "a" }, { id: "b" }, { id: "c" }];

test("keeps a stored id that still exists on the server", () => {
  assert.equal(resolveAssistantSession("b", SESSIONS), "b");
});

test("drops a stored id that no longer exists (deleted session)", () => {
  assert.equal(resolveAssistantSession("gone", SESSIONS), null);
});

test("returns null when there is no stored id", () => {
  assert.equal(resolveAssistantSession(null, SESSIONS), null);
});

test("returns null when the server has no sessions", () => {
  assert.equal(resolveAssistantSession("b", []), null);
});

test("withRouteContext prefixes the viewed symbol on instrument pages", () => {
  assert.equal(
    withRouteContext("/instruments/RELIANCE", "how does it look?"),
    "[viewing RELIANCE] how does it look?",
  );
});

test("withRouteContext decodes url-encoded symbols and ignores sub-paths", () => {
  assert.equal(
    withRouteContext("/instruments/M%26M/forecast", "buy?"),
    "[viewing M&M] buy?",
  );
});

test("withRouteContext leaves messages untouched off instrument pages", () => {
  assert.equal(withRouteContext("/portfolio", "hi"), "hi");
  assert.equal(withRouteContext("/", "hi"), "hi");
});
