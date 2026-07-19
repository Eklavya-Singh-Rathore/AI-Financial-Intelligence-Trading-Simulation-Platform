"use client";

import clsx from "clsx";
import { Badge } from "@/components/ui";
import { type Tone } from "@/lib/ui";
import type { AgentRun } from "@/lib/api";

const STATUS_TONE: Record<string, Tone> = {
  completed: "gain",
  failed: "loss",
  running: "accent",
  pending: "accent",
};

export function StatusChip({ status }: { status: string }) {
  return <Badge tone={STATUS_TONE[status] ?? "neutral"}>{status}</Badge>;
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
