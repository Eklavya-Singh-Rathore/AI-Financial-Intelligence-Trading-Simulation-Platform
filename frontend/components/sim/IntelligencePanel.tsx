import clsx from "clsx";
import { type SimIntelligence } from "@/lib/api";

/** Risk score, sector exposure, correlation heatmap, suggestions (Phase 6, shared). */
export function IntelligencePanel({ intel }: { intel: SimIntelligence }) {
  const riskTone =
    intel.risk_score >= 60 ? "text-loss" : intel.risk_score >= 30 ? "text-ink" : "text-gain";
  return (
    <div className="space-y-4">
      <div className="flex items-baseline justify-between">
        <span className="text-sm text-ink-2">Risk score</span>
        <span className={clsx("tabular text-2xl font-semibold", riskTone)}>
          {intel.risk_score}
          <span className="text-xs text-ink-3"> / 100</span>
        </span>
      </div>
      <div className="grid grid-cols-2 gap-2 text-xs text-ink-2">
        <div>Volatility: <span className="tabular">{intel.portfolio_volatility_pct}%</span></div>
        <div>Effective positions: <span className="tabular">{intel.diversification.effective_positions}</span></div>
      </div>
      {intel.sector_exposure.length > 0 && (
        <div>
          <div className="mb-1.5 text-xs font-medium text-ink-2">Sector exposure</div>
          <div className="space-y-1.5">
            {intel.sector_exposure.map((s) => (
              <div key={s.sector} className="flex items-center gap-2 text-xs">
                <span className="w-24 truncate text-ink-2">{s.sector}</span>
                <div className="h-2 flex-1 overflow-hidden rounded-full bg-surface-2">
                  <div
                    className={clsx("h-full rounded-full", s.sector === "Cash" ? "bg-ink-3" : "bg-accent")}
                    style={{ width: `${Math.min(s.pct, 100)}%` }}
                  />
                </div>
                <span className="tabular w-12 text-right text-ink-2">{s.pct.toFixed(1)}%</span>
              </div>
            ))}
          </div>
        </div>
      )}
      {intel.correlation.symbols.length >= 2 && (
        <div>
          <div className="mb-1.5 text-xs font-medium text-ink-2">Correlation (180d returns)</div>
          <div className="overflow-x-auto">
            <table className="tabular text-[11px]">
              <thead>
                <tr>
                  <th />
                  {intel.correlation.symbols.map((s) => (
                    <th key={s} className="px-1.5 py-0.5 text-ink-3">{s.slice(0, 6)}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {intel.correlation.symbols.map((row, i) => (
                  <tr key={row}>
                    <td className="pr-1.5 text-ink-3">{row.slice(0, 6)}</td>
                    {intel.correlation.matrix[i].map((v, j) => (
                      <td
                        key={j}
                        className="px-1.5 py-0.5 text-center"
                        style={{
                          backgroundColor:
                            v === null ? undefined : `rgba(37, 99, 235, ${Math.abs(v) * 0.35})`,
                        }}
                      >
                        {v === null ? "–" : v.toFixed(2)}
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
      {intel.suggestions.length > 0 && (
        <div>
          <div className="mb-1.5 text-xs font-medium text-ink-2">Suggestions</div>
          <ul className="list-disc space-y-1 pl-4 text-xs text-ink-2">
            {intel.suggestions.map((s) => (
              <li key={s}>{s}</li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
