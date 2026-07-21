"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Bot, Layers, TrendingUp, Wallet, Zap } from "lucide-react";
import { useState } from "react";
import clsx from "clsx";
import Link from "next/link";
import { OrderRow } from "@/components/sim/OrderRow";
import { OrderTicket } from "@/components/sim/OrderTicket";
import { Badge, Card, CardBody, CardHeader, CardTitle, EmptyState, Stat } from "@/components/ui";
import { api, fmtNum, polarity } from "@/lib/api";

const STATUS_FILTERS = ["all", "open", "filled", "proposed", "cancelled"] as const;

export default function SimulationPage() {
  const qc = useQueryClient();
  const [filter, setFilter] = useState<(typeof STATUS_FILTERS)[number]>("all");
  const refetchAll = () => qc.invalidateQueries({ queryKey: ["sim"] });

  const portfolio = useQuery({ queryKey: ["sim", "portfolio"], queryFn: api.simPortfolio });
  const orders = useQuery({ queryKey: ["sim", "orders"], queryFn: () => api.simOrders() });
  const trades = useQuery({ queryKey: ["sim", "trades"], queryFn: api.simTrades });

  const accept = useMutation({ mutationFn: api.simAcceptOrder, onSuccess: refetchAll });
  const reject = useMutation({ mutationFn: api.simRejectOrder, onSuccess: refetchAll });
  const cancel = useMutation({ mutationFn: api.simCancelOrder, onSuccess: refetchAll });

  const p = portfolio.data;
  const allOrders = orders.data ?? [];
  const proposals = allOrders.filter((o) => o.status === "proposed");
  const filtered = filter === "all" ? allOrders : allOrders.filter((o) => o.status === filter);
  const actionError = accept.error ?? reject.error ?? cancel.error;
  const rowHandlers = {
    onAccept: (id: string) => accept.mutate(id),
    onReject: (id: string) => reject.mutate(id),
    onCancel: (id: string) => cancel.mutate(id),
  };

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div>
          <h1 className="text-xl font-semibold">Simulation</h1>
          <p className="text-sm text-ink-2">Paper trading against stored daily bars — no real orders.</p>
        </div>
        <Link href="/portfolio" className="text-sm text-accent hover:underline">
          Portfolio &amp; analytics →
        </Link>
      </div>

      {portfolio.error && <p className="text-sm text-loss">{String(portfolio.error)}</p>}
      {p && (
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
          <Stat
            label="Equity"
            value={`₹${fmtNum(p.equity)}`}
            deltaPct={p.total_pnl_pct}
            icon={<Wallet size={14} />}
            tone="accent"
          />
          <Stat
            label="Buying power"
            value={`₹${fmtNum(p.buying_power)}`}
            icon={<Zap size={14} />}
            tone="accent"
            sub={p.equity ? `${((p.buying_power / p.equity) * 100).toFixed(0)}% of equity` : undefined}
          />
          <Stat
            label="Total P&L"
            value={`₹${fmtNum(p.total_pnl)}`}
            deltaPct={p.total_pnl_pct}
            icon={<TrendingUp size={14} />}
            tone={p.total_pnl >= 0 ? "gain" : "loss"}
          />
          <Stat
            label="Positions"
            value={String(p.positions.length)}
            icon={<Layers size={14} />}
            tone="accent"
            sub="Active positions"
          />
        </div>
      )}
      {actionError != null && <p className="text-sm text-loss">{String(actionError)}</p>}

      <div className="grid gap-5 lg:grid-cols-3">
        {/* Left: order entry + AI proposals */}
        <div className="space-y-5">
          <Card>
            <CardHeader><CardTitle>Place order</CardTitle></CardHeader>
            <CardBody>
              <OrderTicket buyingPower={p?.buying_power} onDone={refetchAll} />
            </CardBody>
          </Card>

          {proposals.length > 0 && (
            <Card className="border-accent/40 bg-accent/5">
              <CardHeader className="border-accent/30">
                <CardTitle className="flex items-center gap-1.5">
                  <Bot size={15} className="text-accent" /> AI proposals
                </CardTitle>
                <Badge tone="accent">{proposals.length}</Badge>
              </CardHeader>
              <CardBody>
                <table className="w-full"><tbody>
                  {proposals.map((o) => <OrderRow key={o.id} o={o} {...rowHandlers} />)}
                </tbody></table>
                <p className="mt-2 text-[11px] text-ink-3">
                  From completed agent runs — accept to execute as a market order, or reject.
                </p>
              </CardBody>
            </Card>
          )}
        </div>

        {/* Right: orders + trade blotter */}
        <div className="space-y-5 lg:col-span-2">
          <Card>
            <CardHeader>
              <CardTitle>Orders</CardTitle>
              <div className="flex flex-wrap gap-1">
                {STATUS_FILTERS.map((f) => (
                  <button
                    key={f}
                    onClick={() => setFilter(f)}
                    className={clsx(
                      "rounded-md px-2 py-0.5 text-xs",
                      filter === f ? "bg-accent/10 text-accent" : "text-ink-3 hover:text-ink",
                    )}
                  >
                    {f}
                  </button>
                ))}
              </div>
            </CardHeader>
            <CardBody>
              {filtered.length === 0 ? (
                <EmptyState title={filter === "all" ? "No orders yet" : `No ${filter} orders`} description="Placed and AI-proposed orders appear here." />
              ) : (
                <div className="overflow-x-auto">
                  <table className="w-full"><tbody>
                    {filtered.map((o) => <OrderRow key={o.id} o={o} {...rowHandlers} />)}
                  </tbody></table>
                </div>
              )}
            </CardBody>
          </Card>

          <Card>
            <CardHeader><CardTitle>Trade history</CardTitle></CardHeader>
            <CardBody>
              {(trades.data ?? []).length === 0 ? (
                <EmptyState title="No trades yet" description="Filled orders are recorded here with realized P&L." />
              ) : (
                <div className="overflow-x-auto">
                  <table className="w-full text-sm">
                    <thead>
                      <tr className="text-left text-[11px] uppercase tracking-wide text-ink-3">
                        <th className="pb-1.5">Trade</th>
                        <th className="px-2 pb-1.5 text-right">Price</th>
                        <th className="px-2 pb-1.5 text-right">Value</th>
                        <th className="px-2 pb-1.5 text-right">Realized P&L</th>
                        <th className="pb-1.5 text-right">Date</th>
                      </tr>
                    </thead>
                    <tbody>
                      {(trades.data ?? []).map((t) => (
                        <tr key={t.id} className="border-t border-line">
                          <td className="py-1.5">
                            <span className={clsx("font-medium", t.side === "buy" ? "text-gain" : "text-loss")}>{t.side}</span>{" "}
                            {t.qty} {t.symbol}
                          </td>
                          <td className="tabular px-2 text-right">{fmtNum(t.price)}</td>
                          <td className="tabular px-2 text-right">{fmtNum(t.value)}</td>
                          <td className={clsx("tabular px-2 text-right", polarity(t.realized_pnl))}>
                            {t.realized_pnl === null ? "–" : fmtNum(t.realized_pnl)}
                          </td>
                          <td className="text-right text-xs text-ink-3">{new Date(t.created_at).toLocaleDateString()}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </CardBody>
          </Card>
        </div>
      </div>
    </div>
  );
}
