// Client-side table sorting (Phase 6). Pure + node-testable.

/**
 * @typedef {{key: string, dir: "asc" | "desc"} | null} SortState
 */

/**
 * Cycle sort state for a clicked column: asc -> desc -> off; new column -> asc.
 * @param {SortState} current
 * @param {string} key
 * @returns {SortState}
 */
export function nextSort(current, key) {
  if (!current || current.key !== key) return { key, dir: "asc" };
  if (current.dir === "asc") return { key, dir: "desc" };
  return null;
}

/**
 * Stable sort by `state.key`; nulls/undefined always sink to the bottom
 * regardless of direction. Strings compare case-insensitively.
 * @template T
 * @param {ReadonlyArray<T>} rows
 * @param {SortState} state
 * @returns {T[]}
 */
export function sortRows(rows, state) {
  if (!state) return [...rows];
  const { key, dir } = state;
  const mul = dir === "desc" ? -1 : 1;
  return [...rows].sort((a, b) => {
    const va = a[key];
    const vb = b[key];
    const aNull = va === null || va === undefined;
    const bNull = vb === null || vb === undefined;
    if (aNull && bNull) return 0;
    if (aNull) return 1; // nulls last, independent of dir
    if (bNull) return -1;
    if (typeof va === "string" || typeof vb === "string") {
      return String(va).localeCompare(String(vb), undefined, { sensitivity: "base" }) * mul;
    }
    return (va < vb ? -1 : va > vb ? 1 : 0) * mul;
  });
}
