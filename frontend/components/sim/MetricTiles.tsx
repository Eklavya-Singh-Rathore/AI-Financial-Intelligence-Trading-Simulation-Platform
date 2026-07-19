import clsx from "clsx";
import { fmtNum, fmtPct, polarity } from "@/lib/api";

const METRIC_LABELS: Record<string, string> = {
  total_return_pct: "Total return",
  cagr_pct: "CAGR",
  sharpe_ratio: "Sharpe",
  sortino_ratio: "Sortino",
  max_drawdown_pct: "Max drawdown",
  volatility_pct: "Volatility",
  win_rate: "Win rate",
  closed_trades: "Closed trades",
};

/** Performance metric grid (Sharpe/Sortino/CAGR/… ) — Phase 6, shared. */
export function MetricTiles({ metrics }: { metrics: Record<string, number | null> }) {
  return (
    <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
      {Object.entries(METRIC_LABELS).map(([key, label]) => {
        const v = metrics[key];
        const pct = key.endsWith("_pct");
        return (
          <div key={key} className="rounded-md bg-surface-2 p-2.5">
            <div className="text-[11px] text-ink-3">{label}</div>
            <div className={clsx("tabular text-sm font-semibold", pct ? polarity(v) : "")}>
              {v === null || v === undefined
                ? "–"
                : key === "win_rate"
                  ? fmtPct(v * 100)
                  : pct
                    ? fmtPct(v)
                    : fmtNum(v)}
            </div>
          </div>
        );
      })}
    </div>
  );
}
