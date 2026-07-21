import { type ReactNode } from "react";
import { fmtPct, polarity } from "@/lib/api";
import { cn } from "@/lib/ui";

type Tone = "accent" | "gain" | "loss" | "warn";

type Props = {
  label: string;
  value: ReactNode;
  /** Signed % delta rendered with gain/loss color, if provided. */
  deltaPct?: number | null;
  /** Free-form sub-line under the value. */
  sub?: ReactNode;
  /** Optional leading icon, shown in a soft tinted chip. */
  icon?: ReactNode;
  /** Tint for the icon chip. */
  tone?: Tone;
  /** Optional visual (e.g. a <Sparkline/>) shown under the value. */
  chart?: ReactNode;
  className?: string;
};

const CHIP_TONES: Record<Tone, string> = {
  accent: "bg-accent/10 text-accent",
  gain: "bg-gain/10 text-gain",
  loss: "bg-loss/10 text-loss",
  warn: "bg-warn/10 text-warn",
};

/** Labelled metric tile. Value uses the tabular (mono) numeric face. */
export function Stat({ label, value, deltaPct, sub, icon, tone = "accent", chart, className }: Props) {
  const hasDelta = deltaPct !== undefined && deltaPct !== null;
  return (
    <div className={cn("rounded-xl border border-line bg-surface p-4 shadow-xs", className)}>
      <div className="flex items-start justify-between gap-2">
        <div className="flex min-w-0 items-center gap-2 text-xs text-ink-3">
          {icon && (
            <span className={cn("grid size-6 shrink-0 place-items-center rounded-md", CHIP_TONES[tone])}>
              {icon}
            </span>
          )}
          <span className="truncate">{label}</span>
        </div>
        {hasDelta && (
          <span className={cn("tabular shrink-0 text-xs font-medium", polarity(deltaPct))}>
            {fmtPct(deltaPct)}
          </span>
        )}
      </div>
      <div className="tabular mt-2 text-xl font-semibold text-ink">{value}</div>
      {sub !== undefined && sub !== null && <div className="mt-0.5 text-[11px] text-ink-3">{sub}</div>}
      {chart && <div className="mt-2">{chart}</div>}
    </div>
  );
}
