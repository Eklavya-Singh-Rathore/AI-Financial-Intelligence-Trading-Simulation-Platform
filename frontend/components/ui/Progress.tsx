import { cn } from "@/lib/ui";

type Tone = "accent" | "gain" | "loss" | "warn";

type Props = {
  /** Current value; percentage is value / max. */
  value: number;
  max?: number;
  tone?: Tone;
  className?: string;
  "aria-label"?: string;
};

const TONE_BAR: Record<Tone, string> = {
  accent: "bg-accent",
  gain: "bg-gain",
  loss: "bg-loss",
  warn: "bg-warn",
};

/** Thin token-driven meter (allocations, exposure, scores). */
export function Progress({ value, max = 1, tone = "accent", className, ...rest }: Props) {
  const pct = Math.max(0, Math.min(100, (value / (max || 1)) * 100));
  return (
    <div
      role="progressbar"
      aria-valuenow={Math.round(pct)}
      aria-valuemin={0}
      aria-valuemax={100}
      className={cn("h-1.5 w-full overflow-hidden rounded-full bg-surface-2", className)}
      {...rest}
    >
      <div
        className={cn("h-full rounded-full transition-[width] duration-300 motion-reduce:transition-none", TONE_BAR[tone])}
        style={{ width: `${pct}%` }}
      />
    </div>
  );
}
