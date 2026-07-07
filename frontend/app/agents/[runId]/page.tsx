"use client";

import { useQuery } from "@tanstack/react-query";
import { useParams } from "next/navigation";
import clsx from "clsx";
import { StatusChip } from "@/components/RunBits";
import { api, fmtNum } from "@/lib/api";

const AGENT_LABELS: Record<string, string> = {
  technical_analyst: "Technical Analyst",
  news_analyst: "News Analyst",
  bull_researcher: "Bull Researcher",
  bear_researcher: "Bear Researcher",
  trader: "Trader",
  risk_manager: "Risk Manager",
  portfolio_manager: "Portfolio Manager",
};

export default function RunPage() {
  const { runId } = useParams<{ runId: string }>();
  const live = (s?: string) => s === "pending" || s === "running";

  const run = useQuery({
    queryKey: ["run", runId],
    queryFn: () => api.run(runId),
    refetchInterval: (q) => (live(q.state.data?.status) ? 2500 : false),
  });
  const messages = useQuery({
    queryKey: ["runMessages", runId],
    queryFn: () => api.runMessages(runId),
    refetchInterval: () => (live(run.data?.status) ? 2500 : false),
  });

  const fd = run.data?.final_decision as
    | { action?: string; size_pct?: number; confidence?: number; summary?: string; risk_verdict?: string; limited_by?: string[] }
    | null;

  return (
    <div className="space-y-5">
      <div className="flex items-center gap-3">
        <h1 className="text-xl font-semibold">{run.data?.symbol ?? "Run"}</h1>
        {run.data && <StatusChip status={run.data.status} />}
        {live(run.data?.status) && <span className="text-xs text-ink-3">updating…</span>}
      </div>
      {run.data?.error && (
        <div className="rounded-md border border-loss/40 bg-loss/5 p-3 text-sm text-loss">{run.data.error}</div>
      )}

      {fd?.action && (
        <div className="rounded-lg border border-line p-4">
          <div className="mb-1 text-xs uppercase tracking-wide text-ink-3">Final decision</div>
          <div className="flex flex-wrap items-center gap-3">
            <span
              className={clsx(
                "text-2xl font-bold",
                fd.action === "BUY" ? "text-gain" : fd.action === "SELL" ? "text-loss" : "",
              )}
            >
              {fd.action}
            </span>
            {fd.action !== "HOLD" && <span className="tabular text-lg">{fd.size_pct}% of capital</span>}
            <span className="tabular text-sm text-ink-2">confidence {fmtNum((fd.confidence ?? 0) * 100, 0)}%</span>
            {fd.risk_verdict && (
              <span className="rounded-full bg-surface-2 px-2 py-0.5 text-xs text-ink-2">
                risk: {fd.risk_verdict}
              </span>
            )}
            {(fd.limited_by ?? []).map((l) => (
              <span key={l} className="rounded-full bg-loss/10 px-2 py-0.5 text-xs text-loss">{l}</span>
            ))}
          </div>
          {fd.summary && <p className="mt-2 text-sm leading-relaxed text-ink-2">{fd.summary}</p>}
          {run.data?.token_usage && (
            <p className="tabular mt-2 text-xs text-ink-3">
              {run.data.token_usage.calls} LLM calls · {run.data.token_usage.input_tokens} in / {run.data.token_usage.output_tokens} out · {run.data.llm_provider}
            </p>
          )}
        </div>
      )}

      <div className="space-y-3">
        {messages.data?.map((m) => (
          <div key={m.seq} className="rounded-lg border border-line p-4">
            <div className="mb-1.5 flex items-center justify-between">
              <span className="text-sm font-semibold">{AGENT_LABELS[m.agent_name] ?? m.agent_name}</span>
              <span className="tabular text-xs text-ink-3">
                #{m.seq}{m.latency_ms ? ` · ${(m.latency_ms / 1000).toFixed(1)}s` : ""}
              </span>
            </div>
            <p className="whitespace-pre-wrap text-sm leading-relaxed text-ink-2">{m.content}</p>
          </div>
        ))}
        {live(run.data?.status) && (
          <div className="rounded-lg border border-dashed border-line p-4 text-center text-sm text-ink-3">
            pipeline running — next agent thinking…
          </div>
        )}
      </div>
    </div>
  );
}
