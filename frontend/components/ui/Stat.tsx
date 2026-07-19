import { type ReactNode } from "react";
import { fmtPct, polarity } from "@/lib/api";
import { cn } from "@/lib/ui";

type Props = {
  label: string;
  value: ReactNode;
  /** Signed % delta rendered with gain/loss color, if provided. */
  deltaPct?: number | null;
  /** Free-form sub-line under the value. */
  sub?: ReactNode;
  className?: string;
};

/** Labelled metric tile. Value uses the tabular (mono) numeric face. */
export function Stat({ label, value, deltaPct, sub, className }: Props) {
  return (
    <div className={cn("rounded-lg border border-line bg-surface p-4 shadow-xs", className)}>
      <div className="text-xs text-ink-3">{label}</div>
      <div className="tabular mt-1 text-xl font-semibold text-ink">{value}</div>
      {deltaPct !== undefined && deltaPct !== null && (
        <div className={cn("tabular mt-0.5 text-xs", polarity(deltaPct))}>{fmtPct(deltaPct)}</div>
      )}
      {sub !== undefined && sub !== null && (
        <div className="mt-0.5 text-[11px] text-ink-3">{sub}</div>
      )}
    </div>
  );
}
