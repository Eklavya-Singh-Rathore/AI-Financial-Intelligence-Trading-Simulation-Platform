import { Progress } from "@/components/ui";
import { type SimPortfolio } from "@/lib/api";

/** Position + cash allocation as horizontal % meters (Phase 6, shared). */
export function AllocationBars({ portfolio }: { portfolio: SimPortfolio }) {
  const rows = [
    ...portfolio.positions.map((p) => ({ label: p.symbol, pct: p.allocation_pct, cash: false })),
    { label: "Cash", pct: portfolio.cash_allocation_pct, cash: true },
  ];
  return (
    <div className="space-y-2">
      {rows.map((r) => (
        <div key={r.label} className="flex items-center gap-2 text-xs">
          <span className="w-20 truncate text-ink-2">{r.label}</span>
          <Progress
            value={r.pct}
            max={100}
            tone={r.cash ? "neutral" : "accent"}
            className="flex-1"
            aria-label={`${r.label} allocation`}
          />
          <span className="tabular w-12 text-right text-ink-2">{r.pct.toFixed(1)}%</span>
        </div>
      ))}
    </div>
  );
}
