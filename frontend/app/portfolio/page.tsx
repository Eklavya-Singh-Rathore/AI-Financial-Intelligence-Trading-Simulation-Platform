"use client";

import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import Link from "next/link";
import { AllocationBars } from "@/components/sim/AllocationBars";
import { EquityChart } from "@/components/sim/EquityChart";
import { HoldingsTable } from "@/components/sim/HoldingsTable";
import { IntelligencePanel } from "@/components/sim/IntelligencePanel";
import { MetricTiles } from "@/components/sim/MetricTiles";
import { FrontierChart } from "@/components/portfolio/FrontierChart";
import { MonteCarloChart } from "@/components/portfolio/MonteCarloChart";
import { Card, CardBody, CardHeader, CardTitle, EmptyState, SkeletonRows, Stat } from "@/components/ui";
import { api, fmtNum, fmtPct } from "@/lib/api";
import { cn } from "@/lib/ui";

const HORIZONS = [
  { label: "1D", value: 1 },
  { label: "10D", value: 10 },
];

export default function PortfolioPage() {
  const [riskHorizon, setRiskHorizon] = useState(1);

  const portfolio = useQuery({ queryKey: ["sim", "portfolio"], queryFn: api.simPortfolio });
  const performance = useQuery({ queryKey: ["sim", "performance"], queryFn: api.simPerformance });
  const intel = useQuery({ queryKey: ["sim", "intelligence"], queryFn: api.simIntelligence });
  const risk = useQuery({
    queryKey: ["sim", "risk", riskHorizon],
    queryFn: () => api.simAnalyticsRisk(riskHorizon),
    staleTime: 60_000,
  });
  const montecarlo = useQuery({
    queryKey: ["sim", "montecarlo"],
    queryFn: () => api.simAnalyticsMonteCarlo(252),
    staleTime: 60_000,
  });
  const opt = useQuery({
    queryKey: ["sim", "optimization"],
    queryFn: () => api.simAnalyticsOptimization(),
    staleTime: 60_000,
  });

  const p = portfolio.data;
  const hasPositions = (p?.positions.length ?? 0) > 0;
  // Narrow the discriminated unions once so nested callbacks keep the type.
  const riskData = risk.data?.available ? risk.data : null;
  const mcData = montecarlo.data?.available ? montecarlo.data : null;
  const optData = opt.data?.available ? opt.data : null;

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div>
          <h1 className="text-xl font-semibold">Portfolio</h1>
          <p className="text-sm text-ink-2">Holdings, performance, and forward-looking risk analytics.</p>
        </div>
        <Link href="/simulation" className="text-sm text-accent hover:underline">
          Trade →
        </Link>
      </div>

      {portfolio.isLoading && <SkeletonRows rows={6} />}
      {p && (
        <>
          <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
            <Stat label="Equity" value={`₹${fmtNum(p.equity)}`} sub={`started ₹${fmtNum(p.starting_cash)}`} />
            <Stat label="Cash" value={`₹${fmtNum(p.cash)}`} sub={`${p.cash_allocation_pct.toFixed(1)}% of equity`} />
            <Stat label="Total P&L" value={`₹${fmtNum(p.total_pnl)}`} deltaPct={p.total_pnl_pct} />
            <Stat label="Realized P&L" value={`₹${fmtNum(p.realized_pnl)}`} />
          </div>

          {!hasPositions && (
            <EmptyState
              title="No holdings yet"
              description="Buy an instrument on the Simulation page to populate the portfolio and unlock risk analytics."
              action={<Link href="/simulation" className="text-sm text-accent hover:underline">Go to Simulation →</Link>}
            />
          )}

          {hasPositions && (
            <div className="grid gap-5 lg:grid-cols-3">
              <div className="space-y-5 lg:col-span-2">
                <Card>
                  <CardHeader><CardTitle>Performance</CardTitle></CardHeader>
                  <CardBody>
                    {performance.data ? (
                      <>
                        <MetricTiles metrics={performance.data.metrics} />
                        <div className="mt-4">
                          <EquityChart series={performance.data.series} />
                        </div>
                      </>
                    ) : (
                      <SkeletonRows rows={3} />
                    )}
                  </CardBody>
                </Card>

                <Card>
                  <CardHeader><CardTitle>Holdings</CardTitle></CardHeader>
                  <CardBody><HoldingsTable positions={p.positions} /></CardBody>
                </Card>

                {/* Monte Carlo projection */}
                <Card>
                  <CardHeader><CardTitle>12-month projection (Monte Carlo)</CardTitle></CardHeader>
                  <CardBody>
                    {mcData ? (
                      <>
                        <MonteCarloChart data={mcData} />
                        <p className="mt-2 text-xs text-ink-3">
                          In 12 months (2,000 GBM paths): median{" "}
                          <span className="tabular text-ink">₹{fmtNum(mcData.terminal.median)}</span>, p5{" "}
                          <span className="tabular">₹{fmtNum(mcData.terminal.p5)}</span> – p95{" "}
                          <span className="tabular">₹{fmtNum(mcData.terminal.p95)}</span>. Probability of loss:{" "}
                          <span className="tabular">{(mcData.prob_loss * 100).toFixed(0)}%</span>.
                        </p>
                      </>
                    ) : (
                      <p className="text-sm text-ink-3">
                        {montecarlo.isLoading ? "Simulating…" : (montecarlo.data && !montecarlo.data.available ? montecarlo.data.reason : "Unavailable.")}
                      </p>
                    )}
                  </CardBody>
                </Card>

                {/* Optimization */}
                <Card>
                  <CardHeader><CardTitle>Allocation optimizer</CardTitle></CardHeader>
                  <CardBody>
                    {optData ? (
                      <div className="grid gap-4 sm:grid-cols-2">
                        <FrontierChart data={optData} />
                        <div>
                          <div className="mb-1 text-xs font-medium text-ink-2">
                            Max-Sharpe weights
                            <span className="tabular ml-2 text-ink-3">
                              {fmtPct(optData.max_sharpe.return_pct)} @ {optData.max_sharpe.risk_pct.toFixed(1)}% vol · Sharpe {optData.max_sharpe.sharpe.toFixed(2)}
                            </span>
                          </div>
                          <table className="w-full text-xs tabular">
                            <tbody>
                              {optData.max_sharpe.weights.map((w) => {
                                const cur = optData.current.find((c) => c.symbol === w.symbol)?.weight ?? 0;
                                const delta = w.weight - cur;
                                return (
                                  <tr key={w.symbol} className="border-t border-line">
                                    <td className="py-1 pr-2 text-ink">{w.symbol}</td>
                                    <td className="px-2 text-right">{(w.weight * 100).toFixed(1)}%</td>
                                    <td className={cn("text-right", delta > 0 ? "text-gain" : delta < 0 ? "text-loss" : "text-ink-3")}>
                                      {delta > 0 ? "+" : ""}{(delta * 100).toFixed(1)}%
                                    </td>
                                  </tr>
                                );
                              })}
                            </tbody>
                          </table>
                          <p className="mt-2 text-[11px] text-ink-3">
                            Long-only mean-variance (Dirichlet frontier sampling). Deltas vs your current weights.
                          </p>
                        </div>
                      </div>
                    ) : (
                      <p className="text-sm text-ink-3">
                        {opt.isLoading ? "Optimizing…" : (opt.data && !opt.data.available ? opt.data.reason : "Needs 2+ holdings with history.")}
                      </p>
                    )}
                  </CardBody>
                </Card>
              </div>

              <div className="space-y-5">
                {/* Value at Risk */}
                <Card>
                  <CardHeader>
                    <CardTitle>Value at Risk</CardTitle>
                    <div className="flex gap-1">
                      {HORIZONS.map((hz) => (
                        <button
                          key={hz.value}
                          onClick={() => setRiskHorizon(hz.value)}
                          className={cn(
                            "rounded px-1.5 py-0.5 text-xs",
                            riskHorizon === hz.value ? "bg-accent/10 text-accent" : "text-ink-3 hover:text-ink",
                          )}
                        >
                          {hz.label}
                        </button>
                      ))}
                    </div>
                  </CardHeader>
                  <CardBody>
                    {riskData ? (
                      <div className="space-y-3">
                        {Object.entries(riskData.confidence).map(([conf, d]) => (
                          <div key={conf} className="rounded-md bg-surface-2 p-2.5">
                            <div className="mb-1 text-[11px] text-ink-3">
                              {(Number(conf) * 100).toFixed(0)}% confidence · {riskData.horizon_days}d
                            </div>
                            <div className="flex items-baseline justify-between">
                              <span className="tabular text-lg font-semibold text-loss">
                                {d.historical.var_pct !== null ? `${d.historical.var_pct.toFixed(2)}%` : "–"}
                              </span>
                              <span className="tabular text-xs text-ink-2">₹{fmtNum(d.var_amount)}</span>
                            </div>
                            <div className="tabular mt-0.5 text-[11px] text-ink-3">
                              CVaR {d.historical.cvar_pct !== null ? `${d.historical.cvar_pct.toFixed(2)}%` : "–"} ·
                              {" "}parametric {d.parametric.var_pct !== null ? `${d.parametric.var_pct.toFixed(2)}%` : "–"}
                            </div>
                          </div>
                        ))}
                        <p className="text-[11px] leading-snug text-ink-3">
                          Max expected loss over {riskData.horizon_days} day(s) at each confidence level (historical
                          + Gaussian). Annual volatility {riskData.annual_vol_pct.toFixed(1)}%.
                        </p>
                      </div>
                    ) : (
                      <p className="text-sm text-ink-3">
                        {risk.isLoading ? "Computing…" : (risk.data && !risk.data.available ? risk.data.reason : "Unavailable.")}
                      </p>
                    )}
                  </CardBody>
                </Card>

                <Card>
                  <CardHeader><CardTitle>Allocation</CardTitle></CardHeader>
                  <CardBody><AllocationBars portfolio={p} /></CardBody>
                </Card>

                <Card>
                  <CardHeader><CardTitle>Intelligence</CardTitle></CardHeader>
                  <CardBody>{intel.data ? <IntelligencePanel intel={intel.data} /> : <SkeletonRows rows={3} />}</CardBody>
                </Card>
              </div>
            </div>
          )}
        </>
      )}
    </div>
  );
}
