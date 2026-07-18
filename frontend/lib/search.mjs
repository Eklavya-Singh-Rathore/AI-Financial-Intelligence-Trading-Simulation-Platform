// Local instrument filter for the command palette (Phase 6). Pure + testable.

/**
 * Filter already-loaded instruments by symbol or display name (case-insensitive
 * substring), symbol-prefix matches ranked first.
 * @param {ReadonlyArray<{symbol: string, display_name: string}>} items
 * @param {string} query
 * @param {number} limit
 */
export function filterInstruments(items, query, limit = 8) {
  const q = query.trim().toLowerCase();
  if (!q) return [];
  const scored = [];
  for (const i of items) {
    const sym = i.symbol.toLowerCase();
    const name = i.display_name.toLowerCase();
    const symIdx = sym.indexOf(q);
    const nameIdx = name.indexOf(q);
    if (symIdx === -1 && nameIdx === -1) continue;
    // Lower score sorts first: exact symbol, symbol-prefix, symbol-substr, name.
    const score = sym === q ? 0 : symIdx === 0 ? 1 : symIdx > 0 ? 2 : 3;
    scored.push({ i, score });
  }
  scored.sort((a, b) => a.score - b.score);
  return scored.slice(0, limit).map((s) => s.i);
}
