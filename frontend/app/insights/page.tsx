"use client";

// AI Insights (Phase 5): evaluation metrics + portfolio-intelligence digest.
import { useQuery } from "@tanstack/react-query";
import { ArrowRight, BarChart3, Brain, Target, Trophy } from "lucide-react";
import Link from "next/link";
import {
  Card,
  CardBody,
  CardHeader,
  CardTitle,
  Progress,
  Skeleton,
  Stat,
  Table,
  Tbody,
  Td,
  Th,
  Thead,
  Tr,
} from "@/components/ui";
import { api, fmtNum, fmtPct, polarity } from "@/lib/api";

export default function InsightsPage() {
  const evaluation = useQuery({
    queryKey: ["evaluation"],
    queryFn: api.evaluationSummary,
    staleTime: 60_000,
  });
  const intelligence = useQuery({
    queryKey: ["simIntelligence"],
    queryFn: api.simIntelligence,
    staleTime: 60_000,
  });

  const ev = evaluation.data;
  const iq = intelligence.data;
  const statuses = ev?.agents.runs_by_status ?? {};
  const completed = statuses["completed"] ?? 0;
  const failed = statuses["failed"] ?? 0;

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-xl font-semibold">AI Insights</h1>
        <p className="text-sm text-ink-2">
          How the AI is performing: forecast accuracy, agent behaviour, recommendation
          outcomes, and cost.
        </p>
      </div>

      {evaluation.isLoading && (
        <div className="space-y-6">
          <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
            {Array.from({ length: 4 }).map((_, i) => (
              <Skeleton key={i} className="h-[86px]" />
            ))}
          </div>
          <div className="grid gap-4 lg:grid-cols-2">
            <Skeleton className="h-40" />
            <Skeleton className="h-40" />
          </div>
        </div>
      )}
      {evaluation.error && (
        <p className="text-sm text-loss">Failed to load evaluation: {evaluation.error.message}</p>
      )}

      {ev && (
        <>
          <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
            <Stat
              label="Agent runs (window)"
              value={`${completed} ok`}
              icon={<BarChart3 size={14} />}
              tone="accent"
              sub={failed ? `${failed} failed` : "no failures"}
            />
            <Stat
              label="Avg decision confidence"
              value={ev.agents.avg_confidence !== null ? `${(ev.agents.avg_confidence * 100).toFixed(0)}%` : "–"}
              icon={<Target size={14} />}
              tone="accent"
              sub={Object.entries(ev.agents.action_mix).map(([a, n]) => `${a} ${n}`).join(" · ") || undefined}
            />
            <Stat
              label="Analyst agreement"
              value={ev.agents.stance_agreement_pct !== null ? `${ev.agents.stance_agreement_pct}%` : "–"}
              icon={<Brain size={14} />}
              tone="accent"
              sub={`technical vs news · ${ev.agents.stance_pairs_evaluated} runs`}
            />
            <Stat
              label="Recommendation success"
              value={
                ev.recommendation_success.success_rate !== null
                  ? `${(ev.recommendation_success.success_rate * 100).toFixed(0)}%`
                  : "–"
              }
              icon={<Trophy size={14} />}
              tone="gain"
              sub={
                ev.recommendation_success.evaluated
                  ? `${ev.recommendation_success.evaluated} BUY/SELL evaluated · avg ${fmtPct(ev.recommendation_success.avg_return_pct)}`
                  : "no evaluable recommendations yet"
              }
            />
          </div>

          <div className="grid gap-4 lg:grid-cols-2">
            <Card>
              <CardHeader>
                <CardTitle>Forecast accuracy (matured points)</CardTitle>
              </CardHeader>
              <CardBody>
                {ev.forecast_accuracy.evaluated_points === 0 ? (
                  <p className="text-xs text-ink-3">
                    No persisted forecasts have matured yet — accuracy appears once forecast
                    target dates pass and actual closes exist.
                  </p>
                ) : (
                  <Table>
                    <Thead>
                      <tr>
                        <Th>Model</Th>
                        <Th numeric>Points</Th>
                        <Th numeric>MAPE</Th>
                        <Th numeric>Bias</Th>
                      </tr>
                    </Thead>
                    <Tbody>
                      {Object.entries(ev.forecast_accuracy.models).map(([model, m]) => (
                        <Tr key={model}>
                          <Td className="text-ink">{model}</Td>
                          <Td numeric>{m.evaluated_points}</Td>
                          <Td numeric>{m.mape_pct.toFixed(2)}%</Td>
                          <Td numeric className={polarity(m.bias_pct)}>
                            {fmtPct(m.bias_pct)}
                          </Td>
                        </Tr>
                      ))}
                    </Tbody>
                  </Table>
                )}
              </CardBody>
            </Card>

            <Card>
              <CardHeader>
                <CardTitle>Usage &amp; cost (recent runs)</CardTitle>
              </CardHeader>
              <CardBody>
                <div className="grid grid-cols-2 gap-x-4 gap-y-1.5 text-xs">
                  <div><span className="text-ink-3">LLM calls: </span><span className="tabular">{fmtNum(ev.usage.llm_calls, 0)}</span></div>
                  <div><span className="text-ink-3">Est. cost: </span><span className="tabular">${ev.usage.est_cost_usd.toFixed(4)}</span></div>
                  <div><span className="text-ink-3">Input tokens: </span><span className="tabular">{fmtNum(ev.usage.input_tokens, 0)}</span></div>
                  <div><span className="text-ink-3">Output tokens: </span><span className="tabular">{fmtNum(ev.usage.output_tokens, 0)}</span></div>
                  <div><span className="text-ink-3">Avg run time: </span><span className="tabular">{ev.usage.avg_run_seconds !== null ? `${ev.usage.avg_run_seconds}s` : "–"}</span></div>
                  <div><span className="text-ink-3">Avg step latency: </span><span className="tabular">{ev.usage.avg_message_latency_ms !== null ? `${(ev.usage.avg_message_latency_ms / 1000).toFixed(1)}s` : "–"}</span></div>
                </div>
                {ev.recommendation_success.evaluated > 0 && (
                  <div className="mt-3 border-t border-line pt-2 text-xs">
                    <div className="mb-1 text-ink-3">Directional return by action</div>
                    <div className="flex gap-4">
                      {Object.entries(ev.recommendation_success.by_action).map(([action, b]) => (
                        <span key={action} className="tabular">
                          {action}: <span className={polarity(b.avg_return_pct)}>{fmtPct(b.avg_return_pct)}</span>{" "}
                          <span className="text-ink-3">({b.n})</span>
                        </span>
                      ))}
                    </div>
                  </div>
                )}
              </CardBody>
            </Card>
          </div>
        </>
      )}

      <Card>
        <CardHeader>
          <CardTitle>Portfolio intelligence</CardTitle>
          <Link href="/simulation" className="inline-flex items-center gap-1 text-xs text-accent hover:underline">
            full view in Simulation <ArrowRight size={12} />
          </Link>
        </CardHeader>
        <CardBody>
          {intelligence.isLoading && <Skeleton className="h-16" />}
          {intelligence.error && (
            <p className="text-xs text-ink-3">
              Portfolio intelligence unavailable ({intelligence.error.message}).
            </p>
          )}
          {iq && (
            <div className="space-y-2 text-xs">
              <div className="flex flex-wrap items-center gap-4">
                <span>
                  <span className="text-ink-3">Risk score: </span>
                  <span className="tabular font-semibold">{iq.risk_score}/100</span>
                </span>
                <span>
                  <span className="text-ink-3">Volatility: </span>
                  <span className="tabular">{fmtPct(iq.portfolio_volatility_pct)}</span>
                </span>
                <span>
                  <span className="text-ink-3">Positions: </span>
                  <span className="tabular">{iq.diversification.positions}</span>
                </span>
                <span>
                  <span className="text-ink-3">Effective positions: </span>
                  <span className="tabular">{iq.diversification.effective_positions}</span>
                </span>
              </div>
              <Progress
                value={iq.risk_score}
                max={100}
                tone={iq.risk_score >= 66 ? "loss" : iq.risk_score >= 33 ? "warn" : "gain"}
                aria-label="Portfolio risk score"
                className="max-w-sm"
              />
              {iq.suggestions.length > 0 && (
                <ul className="list-disc space-y-0.5 pl-4 text-ink-2">
                  {iq.suggestions.map((s, i) => (
                    <li key={i}>{s}</li>
                  ))}
                </ul>
              )}
            </div>
          )}
        </CardBody>
      </Card>
    </div>
  );
}
