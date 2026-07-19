"use client";

import { useMutation, useQuery } from "@tanstack/react-query";
import { ArrowRight, Send } from "lucide-react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useState } from "react";
import clsx from "clsx";
import { StatusChip } from "@/components/RunBits";
import { Badge, Button, Card, CardBody, CardHeader, CardTitle, Skeleton } from "@/components/ui";
import { api, fmtNum, type SimOrder } from "@/lib/api";
import { type Tone } from "@/lib/ui";

const AGENT_LABELS: Record<string, string> = {
  technical_analyst: "Technical Analyst",
  news_analyst: "News Analyst",
  bull_researcher: "Bull Researcher",
  bear_researcher: "Bear Researcher",
  trader: "Trader",
  risk_manager: "Risk Manager",
  portfolio_manager: "Portfolio Manager",
};

function StanceChip({ label, stance }: { label: string; stance?: string }) {
  if (!stance) return null;
  const tone: Tone = stance === "bullish" ? "gain" : stance === "bearish" ? "loss" : "neutral";
  return (
    <Badge tone={tone}>
      {label}: {stance}
    </Badge>
  );
}

function ExplanationPanel({ runId }: { runId: string }) {
  const q = useQuery({
    queryKey: ["explanation", runId],
    queryFn: () => api.runExplanation(runId),
    staleTime: 60_000,
  });
  const ex = q.data;
  if (q.isLoading) return <Skeleton className="h-40" />;
  if (!ex) return null;

  const indicators = Object.entries(ex.indicators).filter(([, v]) => v !== null).slice(0, 8);
  const forecastCloses = ex.forecast.predicted_closes ?? [];
  const forecastDelta =
    forecastCloses.length > 0 && ex.price_summary.last_close
      ? ((forecastCloses[forecastCloses.length - 1] / Number(ex.price_summary.last_close)) - 1) * 100
      : null;
  const btMetrics = ex.backtest.metrics ?? {};

  return (
    <Card>
      <CardHeader>
        <CardTitle>Why this recommendation</CardTitle>
        {ex.as_of && <span className="text-[11px] text-ink-3">inputs as of {ex.as_of}</span>}
      </CardHeader>
      <CardBody>
        {ex.why.length > 0 && (
          <ul className="mb-3 list-disc space-y-1 pl-4 text-sm leading-relaxed text-ink-2">
            {ex.why.map((w, i) => (
              <li key={i}>{w}</li>
            ))}
          </ul>
        )}

        <div className="mb-3 flex flex-wrap items-center gap-1.5">
          <StanceChip label="technical" stance={ex.technical.stance} />
          <StanceChip label="news" stance={ex.news.stance} />
          {typeof ex.news.sentiment_score === "number" && (
            <Badge tone="neutral" className="tabular">
              sentiment {ex.news.sentiment_score.toFixed(2)}
            </Badge>
          )}
          {ex.risk.verdict && <Badge tone="neutral">risk: {ex.risk.verdict}</Badge>}
        </div>

        <div className="grid gap-3 text-xs sm:grid-cols-2">
          {indicators.length > 0 && (
            <div>
              <div className="mb-1 font-medium text-ink-2">Indicators at decision time</div>
              <div className="flex flex-wrap gap-1.5">
                {indicators.map(([k, v]) => (
                  <span key={k} className="rounded bg-surface-2 px-1.5 py-0.5 tabular text-ink-2">
                    {k} {fmtNum(v)}
                  </span>
                ))}
              </div>
            </div>
          )}
          {forecastCloses.length > 0 && (
            <div>
              <div className="mb-1 font-medium text-ink-2">
                Forecast ({ex.forecast.model}, {ex.forecast.horizon_days}d)
              </div>
              <span className={clsx("tabular", forecastDelta !== null && forecastDelta >= 0 ? "text-gain" : "text-loss")}>
                {forecastDelta !== null ? `${forecastDelta >= 0 ? "+" : ""}${forecastDelta.toFixed(2)}% vs last close` : "–"}
              </span>
              <span className="ml-2 text-ink-3">→ {forecastCloses.map((c) => fmtNum(c)).join(", ")}</span>
            </div>
          )}
          {Object.keys(btMetrics).length > 0 && (
            <div>
              <div className="mb-1 font-medium text-ink-2">Backtest ({ex.backtest.engine})</div>
              <div className="flex flex-wrap gap-x-3 gap-y-0.5 tabular text-ink-2">
                {Object.entries(btMetrics).slice(0, 4).map(([k, v]) => (
                  <span key={k}>{k}: {fmtNum(v)}</span>
                ))}
              </div>
            </div>
          )}
          {ex.risk.concerns.length > 0 && (
            <div>
              <div className="mb-1 font-medium text-ink-2">Risk concerns</div>
              <ul className="list-disc space-y-0.5 pl-4 text-ink-2">
                {ex.risk.concerns.map((c, i) => (
                  <li key={i}>{c}</li>
                ))}
              </ul>
            </div>
          )}
        </div>

        {ex.news.headlines.length > 0 && (
          <div className="mt-3 text-xs">
            <div className="mb-1 font-medium text-ink-2">Headlines considered</div>
            <ul className="space-y-0.5 text-ink-3">
              {ex.news.headlines.slice(0, 5).map((h, i) => (
                <li key={i} className="truncate">{h}</li>
              ))}
            </ul>
          </div>
        )}

        {!ex.has_snapshot && (
          <p className="mt-3 text-[11px] text-ink-3">
            This run predates input snapshots — indicators/forecast/backtest at decision time are unavailable.
          </p>
        )}
      </CardBody>
    </Card>
  );
}

function SendToSimulation({ runId }: { runId: string }) {
  const [order, setOrder] = useState<SimOrder | null>(null);
  const propose = useMutation({
    mutationFn: () => api.simPropose(runId),
    onSuccess: setOrder,
  });
  if (order) {
    return (
      <span className="inline-flex items-center gap-1.5 text-sm text-gain">
        Proposal created: {order.side.toUpperCase()} {order.qty} {order.symbol}
        <Link href="/simulation" className="inline-flex items-center gap-0.5 text-accent hover:underline">
          review in Simulation <ArrowRight size={13} />
        </Link>
      </span>
    );
  }
  return (
    <span className="inline-flex items-center gap-2">
      <Button size="sm" onClick={() => propose.mutate()} disabled={propose.isPending}>
        <Send size={14} /> {propose.isPending ? "Sending…" : "Send to Simulation"}
      </Button>
      {propose.error && <span className="text-xs text-loss">{propose.error.message}</span>}
    </span>
  );
}

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
  const proposable =
    run.data?.status === "completed" &&
    (fd?.action === "BUY" || fd?.action === "SELL") &&
    fd?.risk_verdict !== "veto" &&
    (fd?.size_pct ?? 0) > 0;

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
        <Card>
          <CardHeader>
            <CardTitle>Final decision</CardTitle>
          </CardHeader>
          <CardBody>
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
              {fd.risk_verdict && <Badge tone="neutral">risk: {fd.risk_verdict}</Badge>}
              {(fd.limited_by ?? []).map((l) => (
                <Badge key={l} tone="loss">{l}</Badge>
              ))}
            </div>
            {fd.summary && <p className="mt-2 text-sm leading-relaxed text-ink-2">{fd.summary}</p>}
            {proposable && (
              <div className="mt-3">
                <SendToSimulation runId={runId} />
              </div>
            )}
            {run.data?.token_usage && (
              <p className="tabular mt-2 text-xs text-ink-3">
                {run.data.token_usage.calls} LLM calls · {run.data.token_usage.input_tokens} in / {run.data.token_usage.output_tokens} out · {run.data.llm_provider}
              </p>
            )}
          </CardBody>
        </Card>
      )}

      {run.data?.status === "completed" && <ExplanationPanel runId={runId} />}

      <div className="space-y-3">
        {messages.data?.map((m) => (
          <Card key={m.seq}>
            <CardHeader>
              <CardTitle>{AGENT_LABELS[m.agent_name] ?? m.agent_name}</CardTitle>
              <span className="tabular text-xs text-ink-3">
                #{m.seq}{m.latency_ms ? ` · ${(m.latency_ms / 1000).toFixed(1)}s` : ""}
              </span>
            </CardHeader>
            <CardBody>
              <p className="whitespace-pre-wrap text-sm leading-relaxed text-ink-2">{m.content}</p>
            </CardBody>
          </Card>
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
