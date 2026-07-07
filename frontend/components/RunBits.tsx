"use client";

import clsx from "clsx";
import type { AgentRun } from "@/lib/api";

export function StatusChip({ status }: { status: string }) {
  const style =
    status === "completed"
      ? "bg-gain/10 text-gain"
      : status === "failed"
        ? "bg-loss/10 text-loss"
        : "bg-accent/10 text-accent";
  return (
    <span className={clsx("rounded-full px-2 py-0.5 text-xs font-medium", style)}>{status}</span>
  );
}

export function DecisionBadge({ run }: { run: AgentRun }) {
  const fd = run.final_decision as { action?: string; size_pct?: number } | null;
  if (!fd?.action) return <span className="text-xs text-ink-3">–</span>;
  const color =
    fd.action === "BUY" ? "text-gain" : fd.action === "SELL" ? "text-loss" : "text-ink-2";
  return (
    <span className={clsx("text-sm font-semibold", color)}>
      {fd.action}
      {fd.action !== "HOLD" && fd.size_pct ? ` ${fd.size_pct}%` : ""}
    </span>
  );
}
