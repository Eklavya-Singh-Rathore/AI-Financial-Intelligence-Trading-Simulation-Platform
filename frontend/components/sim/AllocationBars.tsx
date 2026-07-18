import clsx from "clsx";
import { type SimPortfolio } from "@/lib/api";

/** Position + cash allocation as horizontal % bars (Phase 6, shared). */
export function AllocationBars({ portfolio }: { portfolio: SimPortfolio }) {
  const rows = [
    ...portfolio.positions.map((p) => ({ label: p.symbol, pct: p.allocation_pct })),
    { label: "Cash", pct: portfolio.cash_allocation_pct },
  ];
  return (
    <div className="space-y-1.5">
      {rows.map((r) => (
        <div key={r.label} className="flex items-center gap-2 text-xs">
          <span className="w-20 truncate text-ink-2">{r.label}</span>
          <div className="h-2 flex-1 overflow-hidden rounded-full bg-surface-2">
            <div
              className={clsx("h-full rounded-full", r.label === "Cash" ? "bg-ink-3" : "bg-accent")}
              style={{ width: `${Math.min(Math.max(r.pct, 0), 100)}%` }}
            />
          </div>
          <span className="tabular w-12 text-right text-ink-2">{r.pct.toFixed(1)}%</span>
        </div>
      ))}
    </div>
  );
}
