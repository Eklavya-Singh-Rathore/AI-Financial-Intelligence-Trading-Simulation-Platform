"use client";

// Financial research (Phase 5): company profile + statements + earnings trend.
import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import clsx from "clsx";
import { api, fmtNum, fmtPct, polarity } from "@/lib/api";

const STATEMENTS = [
  { key: "income", label: "Income" },
  { key: "balance", label: "Balance sheet" },
  { key: "cashflow", label: "Cash flow" },
] as const;

function fmtCompact(v: number | null): string {
  if (v === null || v === undefined) return "–";
  const abs = Math.abs(v);
  if (abs >= 1e12) return `${(v / 1e12).toFixed(2)}T`;
  if (abs >= 1e9) return `${(v / 1e9).toFixed(2)}B`;
  if (abs >= 1e7) return `${(v / 1e7).toFixed(2)}Cr`;
  if (abs >= 1e5) return `${(v / 1e5).toFixed(2)}L`;
  return fmtNum(v);
}

export function ResearchSection({ symbol }: { symbol: string }) {
  const [statement, setStatement] = useState<(typeof STATEMENTS)[number]["key"]>("income");
  const [period, setPeriod] = useState<"annual" | "quarterly">("annual");

  const profile = useQuery({
    queryKey: ["profile", symbol],
    queryFn: () => api.profile(symbol),
    staleTime: 5 * 60_000,
  });
  const financials = useQuery({
    queryKey: ["financials", symbol, period, statement],
    queryFn: () => api.financials(symbol, statement === "income" ? period : "annual", statement),
    staleTime: 5 * 60_000,
  });
  const earnings = useQuery({
    queryKey: ["earnings", symbol],
    queryFn: () => api.earnings(symbol),
    staleTime: 5 * 60_000,
  });

  const p = profile.data?.profile ?? {};
  const summary = typeof p.longBusinessSummary === "string" ? p.longBusinessSummary : null;
  const facts: [string, string][] = [];
  if (p.sector) facts.push(["Sector", String(p.sector)]);
  if (p.industry) facts.push(["Industry", String(p.industry)]);
  if (typeof p.marketCap === "number") facts.push(["Market cap", `₹${fmtCompact(p.marketCap)}`]);
  if (typeof p.trailingPE === "number") facts.push(["P/E (ttm)", p.trailingPE.toFixed(1)]);
  if (typeof p.priceToBook === "number") facts.push(["P/B", p.priceToBook.toFixed(1)]);
  if (typeof p.dividendYield === "number") facts.push(["Div yield", `${p.dividendYield.toFixed(2)}%`]);
  if (typeof p.beta === "number") facts.push(["Beta", p.beta.toFixed(2)]);
  if (typeof p.fullTimeEmployees === "number") facts.push(["Employees", fmtNum(p.fullTimeEmployees, 0)]);

  // Degraded payloads (db-only / provider fallbacks) may lack periods/rows —
  // treat anything missing as empty so bad data renders the empty state, never
  // a crash.
  const stmt = financials.data?.data;
  const periods = stmt?.periods ?? [];
  const rows = stmt?.rows ?? {};
  const quarters = (earnings.data?.quarters ?? []).slice(0, 5);

  return (
    <div className="rounded-lg border border-line p-4">
      <div className="mb-3 flex items-center justify-between">
        <h2 className="font-medium">Research</h2>
        {profile.data && (
          <span className="text-[11px] text-ink-3" title={profile.data.fetched_at ?? undefined}>
            source: {profile.data.source}
          </span>
        )}
      </div>

      {profile.isLoading && <p className="py-6 text-center text-sm text-ink-2">Loading research…</p>}

      {profile.data && (
        <div className="space-y-4">
          <div>
            <div className="mb-1 text-sm font-medium">
              {String(p.longName ?? symbol)}
              {typeof p.website === "string" && (
                <a
                  href={p.website}
                  target="_blank"
                  rel="noreferrer"
                  className="ml-2 text-xs font-normal text-accent hover:underline"
                >
                  {p.website.replace(/^https?:\/\//, "")}
                </a>
              )}
            </div>
            {facts.length > 0 && (
              <div className="mb-2 grid grid-cols-2 gap-x-4 gap-y-1 text-xs text-ink-2 sm:grid-cols-4">
                {facts.map(([k, v]) => (
                  <div key={k}>
                    <span className="text-ink-3">{k}: </span>
                    <span className="tabular">{v}</span>
                  </div>
                ))}
              </div>
            )}
            {summary && <p className="text-xs leading-relaxed text-ink-2">{summary}</p>}
          </div>

          {quarters.length > 0 && (
            <div>
              <div className="mb-1.5 text-xs font-medium text-ink-2">
                Earnings (quarterly, derived from income statement)
              </div>
              <div className="overflow-x-auto">
                <table className="w-full text-xs tabular">
                  <thead>
                    <tr className="text-left text-ink-3">
                      <th className="pb-1">QUARTER</th>
                      <th className="px-2 pb-1 text-right">REVENUE</th>
                      <th className="px-2 pb-1 text-right">REV QoQ</th>
                      <th className="px-2 pb-1 text-right">REV YoY</th>
                      <th className="px-2 pb-1 text-right">NET INCOME</th>
                      <th className="pb-1 text-right">NI YoY</th>
                    </tr>
                  </thead>
                  <tbody>
                    {quarters.map((q) => (
                      <tr key={q.period} className="border-t border-line">
                        <td className="py-1">{q.period}</td>
                        <td className="px-2 text-right">{fmtCompact(q.revenue)}</td>
                        <td className={clsx("px-2 text-right", polarity(q.revenue_qoq_pct))}>
                          {fmtPct(q.revenue_qoq_pct)}
                        </td>
                        <td className={clsx("px-2 text-right", polarity(q.revenue_yoy_pct))}>
                          {fmtPct(q.revenue_yoy_pct)}
                        </td>
                        <td className="px-2 text-right">{fmtCompact(q.net_income)}</td>
                        <td className={clsx("text-right", polarity(q.net_income_yoy_pct))}>
                          {fmtPct(q.net_income_yoy_pct)}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}

          <div>
            <div className="mb-2 flex flex-wrap items-center gap-2 text-xs">
              {STATEMENTS.map((s) => (
                <button
                  key={s.key}
                  onClick={() => setStatement(s.key)}
                  className={clsx(
                    "rounded-md border px-2 py-1",
                    statement === s.key
                      ? "border-accent text-accent"
                      : "border-line text-ink-2 hover:text-ink",
                  )}
                >
                  {s.label}
                </button>
              ))}
              {statement === "income" && (
                <select
                  value={period}
                  onChange={(e) => setPeriod(e.target.value as "annual" | "quarterly")}
                  className="rounded border border-line bg-surface px-2 py-1"
                >
                  <option value="annual">annual</option>
                  <option value="quarterly">quarterly</option>
                </select>
              )}
            </div>
            {financials.isLoading && <p className="text-xs text-ink-3">Loading statement…</p>}
            {stmt && periods.length === 0 && (
              <p className="text-xs text-ink-3">
                Statement data unavailable for this instrument (source: {financials.data?.source}).
              </p>
            )}
            {periods.length > 0 && (
              <div className="overflow-x-auto">
                <table className="w-full text-xs tabular">
                  <thead>
                    <tr className="text-left text-ink-3">
                      <th className="pb-1">LINE ITEM</th>
                      {periods.map((per) => (
                        <th key={per} className="px-2 pb-1 text-right">{per}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {Object.entries(rows).map(([name, values]) => (
                      <tr key={name} className="border-t border-line">
                        <td className="py-1 pr-2">{name}</td>
                        {(Array.isArray(values) ? values : []).map((v, i) => (
                          <td key={i} className="px-2 text-right">{fmtCompact(v)}</td>
                        ))}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
