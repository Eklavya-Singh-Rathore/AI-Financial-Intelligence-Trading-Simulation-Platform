// Floating-assistant session resolution (Phase 6). Pure + testable.

/**
 * Return the stored assistant chat-session id if it still exists on the
 * server, else null (caller then lazily creates a fresh session).
 * @param {string | null} storedId
 * @param {ReadonlyArray<{id: string}>} existingSessions
 * @returns {string | null}
 */
export function resolveAssistantSession(storedId, existingSessions) {
  if (storedId && existingSessions.some((s) => s.id === storedId)) return storedId;
  return null;
}

/**
 * Prefix a user message with the symbol currently being viewed so the chat
 * backend's symbol detection grounds the answer (no backend change needed).
 * @param {string} pathname
 * @param {string} message
 * @returns {string}
 */
export function withRouteContext(pathname, message) {
  const m = pathname.match(/^\/instruments\/([^/]+)/);
  if (m) return `[viewing ${decodeURIComponent(m[1])}] ${message}`;
  return message;
}
