// Chart indicator presets (Phase 6.5) — persisted enabled-indicator set.
// Pure `sanitizeEnabled` is node-testable; the load/save wrappers touch
// localStorage and degrade to the fallback on any error.

const KEY = "chart_indicators_v1";

/**
 * Keep only currently-valid indicator ids from a stored value. A non-array
 * stored value (never set / corrupt) yields the fallback; a valid array is
 * respected as-is (an empty array means the user turned everything off).
 * @param {unknown} stored
 * @param {readonly string[]} validIds
 * @param {readonly string[]} fallback
 * @returns {string[]}
 */
export function sanitizeEnabled(stored, validIds, fallback) {
  if (!Array.isArray(stored)) return [...fallback];
  const valid = new Set(validIds);
  return stored.filter((id) => valid.has(id));
}

/** @param {readonly string[]} validIds @param {readonly string[]} fallback */
export function loadEnabledIndicators(validIds, fallback) {
  try {
    const raw = localStorage.getItem(KEY);
    if (raw == null) return [...fallback];
    return sanitizeEnabled(JSON.parse(raw), validIds, fallback);
  } catch {
    return [...fallback];
  }
}

/** @param {readonly string[]} ids */
export function saveEnabledIndicators(ids) {
  try {
    localStorage.setItem(KEY, JSON.stringify(ids));
  } catch {
    /* storage unavailable — presets just won't persist */
  }
}
