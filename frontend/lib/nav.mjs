// Pure navigation helpers (Phase 6). Plain ESM so both the TSX shell and the
// node:test runner consume the same logic (allowJs is on in tsconfig).

/**
 * Is `href` the active nav route for the current `pathname`?
 * Root ("/") matches only itself; other entries match the exact path or any
 * sub-path (so /agents is active on /agents/123 but not /agentsfoo).
 * @param {string} pathname
 * @param {string} href
 * @returns {boolean}
 */
export function isActive(pathname, href) {
  if (href === "/") return pathname === "/";
  return pathname === href || pathname.startsWith(href + "/");
}

/**
 * Human page title for the top bar, from the pathname. Longest matching nav
 * prefix wins; empty string when nothing matches (e.g. instrument detail).
 * @param {string} pathname
 * @param {ReadonlyArray<{href: string, label: string}>} routes
 * @returns {string}
 */
export function pageTitle(pathname, routes) {
  let best = null;
  for (const r of routes) {
    if (isActive(pathname, r.href) && (best === null || r.href.length > best.href.length)) {
      best = r;
    }
  }
  return best ? best.label : "";
}
