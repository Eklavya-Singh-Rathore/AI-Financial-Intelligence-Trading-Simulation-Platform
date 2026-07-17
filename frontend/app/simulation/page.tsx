"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Bot, Check, X } from "lucide-react";
import { useState } from "react";
import clsx from "clsx";
import { EquityChart } from "@/components/sim/EquityChart";
import {
  api,
  fmtNum,
  fmtPct,
  polarity,
  type OrderCreate,
  type SimIntelligence,
  type SimOrder,
  type SimPortfolio,
} from "@/lib/api";

const METRIC_LABELS: Record<string, string> = {
  total_return_pct: "Total return",
  cagr_pct: "CAGR",
  sharpe_ratio: "Sharpe",
  sortino_ratio: "Sortino",
  max_drawdown_pct: "Max drawdown",
  volatility_pct: "Volatility",
  win_rate: "Win rate",
  closed_trades: "Closed trades",
};

function Card({ label, value, sub, tone }: {
  label: string; value: string; sub?: string; tone?: string;
}) {
  return (
    <div className="rounded-lg border border-line p-4">
      <div className="text-xs text-ink-3">{label}</div>
      <div className={clsx("tabular text-xl font-semibold", tone)}>{value}</div>
      {sub && <div className="mt-0.5 text-xs text-ink-3">{sub}</div>}
    </div>
  );
}

function OrderTicket({ onDone }: { onDone: () => void }) {
  const [form, setForm] = useState<OrderCreate>({
    symbol: "", side: "buy", order_type: "market", qty: 1,
  });
  const place = useMutation({
    mutationFn: () => api.simPlaceOrder({
      ...form,
      symbol: form.symbol.trim().toUpperCase(),
      limit_price: form.order_type === "limit" ? form.limit_price : undefined,
      stop_price: form.order_type === "stop" ? form.stop_price : undefined,
    }),
    onSuccess: onDone,
  });
  const set = (patch: Partial<OrderCreate>) => setForm({ ...form, ...patch });
  const input = "w-full rounded-md border border-line bg-surface px-2 py-1.5 text-sm";
  return (
    <div className="rounded-lg border border-line p-4">
      <h2 className="mb-3 font-medium">Place order</h2>
      <div className="space-y-2 text-sm">
        <input
          value={form.symbol}
          onChange={(e) => set({ symbol: e.target.value })}
          placeholder="symbol e.g. RELIANCE"
          className={input}
        />
        <div className="grid grid-cols-2 gap-2">
          <select value={form.side} onChange={(e) => set({ side: e.target.value as "buy" | "sell" })} className={input}>
            <option value="buy">buy</option>
            <option value="sell">sell</option>
          </select>
          <select
            value={form.order_type}
            onChange={(e) => set({ order_type: e.target.value as OrderCreate["order_type"] })}
            className={input}
          >
            <option value="market">market</option>
            <option value="limit">limit</option>
            <option value="stop">stop</option>
          </select>
        </div>
        <label className="flex flex-col gap-1 text-xs text-ink-2">
          quantity
          <input
            type="number" min={1} value={form.qty}
            onChange={(e) => set({ qty: Number(e.target.value) })}
            className={clsx(input, "tabular")}
          />
        </label>
        {form.order_type === "limit" && (
          <label className="flex flex-col gap-1 text-xs text-ink-2">
            limit price
            <input
              type="number" min={0.05} step={0.05} value={form.limit_price ?? ""}
              onChange={(e) => set({ limit_price: Number(e.target.value) })}
              className={clsx(input, "tabular")}
            />
          </label>
        )}
        {form.order_type === "stop" && (
          <label className="flex flex-col gap-1 text-xs text-ink-2">
            stop price
            <input
              type="number" min={0.05} step={0.05} value={form.stop_price ?? ""}
              onChange={(e) => set({ stop_price: Number(e.target.value) })}
              className={clsx(input, "tabular")}
            />
          </label>
        )}
        {place.error && <p className="text-xs text-loss">{String(place.error)}</p>}
        <button
          onClick={() => place.mutate()}
          disabled={place.isPending || !form.symbol.trim() || form.qty < 1}
          className={clsx(
            "w-full rounded-md px-3 py-2 text-sm font-medium text-white disabled:opacity-50",
            form.side === "buy" ? "bg-gain" : "bg-loss",
          )}
        >
          {place.isPending ? "…" : `${form.side} ${form.symbol.trim().toUpperCase() || "…"}`}
        </button>
        <p className="text-[11px] leading-snug text-ink-3">
          Market fills at the latest stored close; limit/stop orders rest and trigger on
          daily bars. Paper simulation only.
        </p>
      </div>
    </div>
  );
}

function AllocationBars({ portfolio }: { portfolio: SimPortfolio }) {
  const rows = [
    ...portfolio.positions.map((p) => ({ label: p.symbol, pct: p.allocation_pct })),
    { label: "Cash", pct: portfolio.cash_allocation_pct },
  ];
  return (
    <div className="space-y-1.5">
      {rows.map((r) => (
        <div key={r.label} className="flex items-center gap-2 text-xs">
          <span className="w-20 truncate text-ink-2">{r.label}</span>
          <div className="h-2 flex-1 overflow-hidden rounded-full bg-surface-2">
            <div
              className={clsx("h-full rounded-full", r.label === "Cash" ? "bg-ink-3" : "bg-accent")}
              style={{ width: `${Math.min(Math.max(r.pct, 0), 100)}%` }}
            />
          </div>
          <span className="w-12 text-right tabular text-ink-2">{r.pct.toFixed(1)}%</span>
        </div>
      ))}
    </div>
  );
}

function IntelligencePanel({ intel }: { intel: SimIntelligence }) {
  const riskTone =
    intel.risk_score >= 60 ? "text-loss" : intel.risk_score >= 30 ? "text-ink" : "text-gain";
  return (
    <div className="space-y-4">
      <div className="flex items-baseline justify-between">
        <span className="text-sm text-ink-2">Risk score</span>
        <span className={clsx("tabular text-2xl font-semibold", riskTone)}>
          {intel.risk_score}
          <span className="text-xs text-ink-3"> / 100</span>
        </span>
      </div>
      <div className="grid grid-cols-2 gap-2 text-xs text-ink-2">
        <div>Volatility: <span className="tabular">{intel.portfolio_volatility_pct}%</span></div>
        <div>Effective positions: <span className="tabular">{intel.diversification.effective_positions}</span></div>
      </div>
      {intel.sector_exposure.length > 0 && (
        <div>
          <div className="mb-1.5 text-xs font-medium text-ink-2">Sector exposure</div>
          <div className="space-y-1.5">
            {intel.sector_exposure.map((s) => (
              <div key={s.sector} className="flex items-center gap-2 text-xs">
                <span className="w-24 truncate text-ink-2">{s.sector}</span>
                <div className="h-2 flex-1 overflow-hidden rounded-full bg-surface-2">
                  <div
                    className={clsx("h-full rounded-full", s.sector === "Cash" ? "bg-ink-3" : "bg-accent")}
                    style={{ width: `${Math.min(s.pct, 100)}%` }}
                  />
                </div>
                <span className="w-12 text-right tabular text-ink-2">{s.pct.toFixed(1)}%</span>
              </div>
            ))}
          </div>
        </div>
      )}
      {intel.correlation.symbols.length >= 2 && (
        <div>
          <div className="mb-1.5 text-xs font-medium text-ink-2">Correlation (180d returns)</div>
          <div className="overflow-x-auto">
            <table className="text-[11px] tabular">
              <thead>
                <tr>
                  <th />
                  {intel.correlation.symbols.map((s) => (
                    <th key={s} className="px-1.5 py-0.5 text-ink-3">{s.slice(0, 6)}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {intel.correlation.symbols.map((row, i) => (
                  <tr key={row}>
                    <td className="pr-1.5 text-ink-3">{row.slice(0, 6)}</td>
                    {intel.correlation.matrix[i].map((v, j) => (
                      <td
                        key={j}
                        className="px-1.5 py-0.5 text-center"
                        style={{
                          backgroundColor:
                            v === null ? undefined : `rgba(37, 99, 235, ${Math.abs(v) * 0.35})`,
                        }}
                      >
                        {v === null ? "–" : v.toFixed(2)}
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
      {intel.suggestions.length > 0 && (
        <div>
          <div className="mb-1.5 text-xs font-medium text-ink-2">Suggestions</div>
          <ul className="list-disc space-y-1 pl-4 text-xs text-ink-2">
            {intel.suggestions.map((s) => (
              <li key={s}>{s}</li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}

function OrderRow({ o, onAccept, onReject, onCancel }: {
  o: SimOrder;
  onAccept: (id: string) => void;
  onReject: (id: string) => void;
  onCancel: (id: string) => void;
}) {
  const statusTone: Record<string, string> = {
    filled: "text-gain", open: "text-accent", proposed: "text-ink",
    cancelled: "text-ink-3", rejected: "text-loss",
  };
  return (
    <tr className="border-t border-line text-sm">
      <td className="py-1.5 pr-2">
        <span className={clsx("font-medium", o.side === "buy" ? "text-gain" : "text-loss")}>
          {o.side}
        </span>{" "}
        {o.qty} {o.symbol}
        {o.source === "ai" && (
          <span className="ml-1.5 rounded-full bg-accent/10 px-1.5 py-0.5 text-[10px] text-accent">
            <Bot size={9} className="mr-0.5 inline" />AI
          </span>
        )}
      </td>
      <td className="px-2 tabular text-ink-2">
        {o.order_type}
        {o.limit_price != null && ` @ ${fmtNum(o.limit_price)}`}
        {o.stop_price != null && ` @ ${fmtNum(o.stop_price)}`}
      </td>
      <td className={clsx("px-2", statusTone[o.status] ?? "text-ink-2")}>
        {o.status}
        {o.reason && <span className="ml-1 text-[10px] text-ink-3" title={o.reason}>ⓘ</span>}
      </td>
      <td className="px-2 text-xs text-ink-3">{new Date(o.created_at).toLocaleDateString()}</td>
      <td className="pl-2 text-right">
        {o.status === "proposed" && (
          <span className="inline-flex gap-1">
            <button
              onClick={() => onAccept(o.id)}
              className="rounded bg-gain px-1.5 py-0.5 text-[11px] font-medium text-white"
              title="Accept and execute as market order"
            >
              <Check size={11} className="inline" /> accept
            </button>
            <button
              onClick={() => onReject(o.id)}
              className="rounded border border-line px-1.5 py-0.5 text-[11px] text-ink-2 hover:text-loss"
            >
              <X size={11} className="inline" /> reject
            </button>
          </span>
        )}
        {o.status === "open" && (
          <button
            onClick={() => onCancel(o.id)}
            className="rounded border border-line px-1.5 py-0.5 text-[11px] text-ink-2 hover:text-loss"
          >
            cancel
          </button>
        )}
      </td>
    </tr>
  );
}

export default function SimulationPage() {
  const qc = useQueryClient();
  const refetchAll = () => {
    qc.invalidateQueries({ queryKey: ["sim"] });
  };

  const portfolio = useQuery({ queryKey: ["sim", "portfolio"], queryFn: api.simPortfolio });
  const orders = useQuery({ queryKey: ["sim", "orders"], queryFn: () => api.simOrders() });
  const trades = useQuery({ queryKey: ["sim", "trades"], queryFn: api.simTrades });
  const performance = useQuery({ queryKey: ["sim", "performance"], queryFn: api.simPerformance });
  const intel = useQuery({ queryKey: ["sim", "intelligence"], queryFn: api.simIntelligence });

  const accept = useMutation({ mutationFn: api.simAcceptOrder, onSuccess: refetchAll });
  const reject = useMutation({ mutationFn: api.simRejectOrder, onSuccess: refetchAll });
  const cancel = useMutation({ mutationFn: api.simCancelOrder, onSuccess: refetchAll });

  const p = portfolio.data;
  const proposals = (orders.data ?? []).filter((o) => o.status === "proposed");
  const actionError = accept.error ?? reject.error ?? cancel.error;

  return (
    <div className="space-y-5">
      <div>
        <h1 className="text-xl font-semibold">Simulation</h1>
        <p className="text-sm text-ink-2">
          Paper trading against stored daily bars — decision support only, no real orders.
        </p>
      </div>

      {portfolio.isLoading && <div className="py-16 text-center text-sm text-ink-2">Loading portfolio…</div>}
      {portfolio.error && <p className="text-sm text-loss">{String(portfolio.error)}</p>}

      {p && (
        <>
          <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
            <Card label="Equity" value={`₹${fmtNum(p.equity)}`} sub={`started ₹${fmtNum(p.starting_cash)}`} />
            <Card label="Cash / buying power" value={`₹${fmtNum(p.cash)}`} sub={`${p.cash_allocation_pct.toFixed(1)}% of equity`} />
            <Card
              label="Total P&L"
              value={`₹${fmtNum(p.total_pnl)}`}
              sub={fmtPct(p.total_pnl_pct)}
              tone={polarity(p.total_pnl)}
            />
            <Card label="Realized P&L" value={`₹${fmtNum(p.realized_pnl)}`} tone={polarity(p.realized_pnl)} />
          </div>

          {proposals.length > 0 && (
            <div className="rounded-lg border border-accent/40 bg-accent/5 p-4">
              <h2 className="mb-2 flex items-center gap-1.5 font-medium">
                <Bot size={15} className="text-accent" /> AI proposals awaiting your decision
              </h2>
              <table className="w-full">
                <tbody>
                  {proposals.map((o) => (
                    <OrderRow
                      key={o.id} o={o}
                      onAccept={(id) => accept.mutate(id)}
                      onReject={(id) => reject.mutate(id)}
                      onCancel={(id) => cancel.mutate(id)}
                    />
                  ))}
                </tbody>
              </table>
            </div>
          )}
          {actionError != null && <p className="text-sm text-loss">{String(actionError)}</p>}

          <div className="grid gap-5 lg:grid-cols-3">
            <div className="space-y-5 lg:col-span-2">
              <div className="rounded-lg border border-line p-4">
                <h2 className="mb-3 font-medium">Performance</h2>
                {performance.data && (
                  <>
                    <div className="mb-4 grid grid-cols-2 gap-3 sm:grid-cols-4">
                      {Object.entries(METRIC_LABELS).map(([key, label]) => {
                        const v = performance.data.metrics[key];
                        const pct = key.endsWith("_pct");
                        return (
                          <div key={key} className="rounded-md bg-surface-2 p-2.5">
                            <div className="text-[11px] text-ink-3">{label}</div>
                            <div className={clsx("tabular text-sm font-semibold", pct ? polarity(v) : "")}>
                              {v === null || v === undefined
                                ? "–"
                                : key === "win_rate"
                                  ? fmtPct((v as number) * 100)
                                  : pct
                                    ? fmtPct(v as number)
                                    : fmtNum(v as number)}
                            </div>
                          </div>
                        );
                      })}
                    </div>
                    <EquityChart series={performance.data.series} />
                    <div className="mt-4 grid grid-cols-2 gap-3">
                      {(["manual", "ai"] as const).map((src) => {
                        const s = performance.data.ai_vs_manual[src];
                        if (!s) return null;
                        return (
                          <div key={src} className="rounded-md bg-surface-2 p-3">
                            <div className="mb-1 flex items-center gap-1.5 text-xs font-medium text-ink-2">
                              {src === "ai" ? <Bot size={12} className="text-accent" /> : null}
                              {src === "ai" ? "AI trades" : "Manual trades"}
                            </div>
                            <div className="space-y-0.5 text-xs text-ink-2">
                              <div>filled orders: <span className="tabular">{s.filled_orders}</span></div>
                              <div>closed trades: <span className="tabular">{s.closed_trades}</span></div>
                              <div>
                                realized P&L:{" "}
                                <span className={clsx("tabular", polarity(s.realized_pnl))}>
                                  ₹{fmtNum(s.realized_pnl)}
                                </span>
                              </div>
                              <div>
                                win rate:{" "}
                                <span className="tabular">
                                  {s.win_rate === null ? "–" : fmtPct(s.win_rate * 100)}
                                </span>
                              </div>
                            </div>
                          </div>
                        );
                      })}
                    </div>
                  </>
                )}
              </div>

              <div className="rounded-lg border border-line p-4">
                <h2 className="mb-2 font-medium">Positions</h2>
                {p.positions.length === 0 ? (
                  <p className="py-4 text-center text-sm text-ink-3">No positions yet.</p>
                ) : (
                  <div className="overflow-x-auto">
                    <table className="w-full text-sm">
                      <thead>
                        <tr className="text-left text-xs text-ink-3">
                          <th className="pb-1.5">SYMBOL</th>
                          <th className="px-2 pb-1.5 text-right">QTY</th>
                          <th className="px-2 pb-1.5 text-right">AVG COST</th>
                          <th className="px-2 pb-1.5 text-right">LAST</th>
                          <th className="px-2 pb-1.5 text-right">VALUE</th>
                          <th className="px-2 pb-1.5 text-right">UNREAL. P&L</th>
                          <th className="pb-1.5 text-right">ALLOC</th>
                        </tr>
                      </thead>
                      <tbody>
                        {p.positions.map((pos) => (
                          <tr key={pos.symbol} className="border-t border-line">
                            <td className="py-1.5 font-medium">{pos.symbol}</td>
                            <td className="px-2 text-right tabular">{pos.qty}</td>
                            <td className="px-2 text-right tabular">{fmtNum(pos.avg_cost)}</td>
                            <td className="px-2 text-right tabular">{fmtNum(pos.last_price)}</td>
                            <td className="px-2 text-right tabular">{fmtNum(pos.market_value)}</td>
                            <td className={clsx("px-2 text-right tabular", polarity(pos.unrealized_pnl))}>
                              {fmtNum(pos.unrealized_pnl)}
                            </td>
                            <td className="text-right tabular">{pos.allocation_pct.toFixed(1)}%</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
              </div>

              <div className="rounded-lg border border-line p-4">
                <h2 className="mb-2 font-medium">Orders</h2>
                {(orders.data ?? []).length === 0 ? (
                  <p className="py-4 text-center text-sm text-ink-3">No orders yet.</p>
                ) : (
                  <table className="w-full">
                    <tbody>
                      {(orders.data ?? []).map((o) => (
                        <OrderRow
                          key={o.id} o={o}
                          onAccept={(id) => accept.mutate(id)}
                          onReject={(id) => reject.mutate(id)}
                          onCancel={(id) => cancel.mutate(id)}
                        />
                      ))}
                    </tbody>
                  </table>
                )}
              </div>

              <div className="rounded-lg border border-line p-4">
                <h2 className="mb-2 font-medium">Trade history</h2>
                {(trades.data ?? []).length === 0 ? (
                  <p className="py-4 text-center text-sm text-ink-3">No trades yet.</p>
                ) : (
                  <div className="overflow-x-auto">
                    <table className="w-full text-sm">
                      <thead>
                        <tr className="text-left text-xs text-ink-3">
                          <th className="pb-1.5">TRADE</th>
                          <th className="px-2 pb-1.5 text-right">PRICE</th>
                          <th className="px-2 pb-1.5 text-right">VALUE</th>
                          <th className="px-2 pb-1.5 text-right">REALIZED P&L</th>
                          <th className="pb-1.5 text-right">DATE</th>
                        </tr>
                      </thead>
                      <tbody>
                        {(trades.data ?? []).map((t) => (
                          <tr key={t.id} className="border-t border-line">
                            <td className="py-1.5">
                              <span className={clsx("font-medium", t.side === "buy" ? "text-gain" : "text-loss")}>
                                {t.side}
                              </span>{" "}
                              {t.qty} {t.symbol}
                            </td>
                            <td className="px-2 text-right tabular">{fmtNum(t.price)}</td>
                            <td className="px-2 text-right tabular">{fmtNum(t.value)}</td>
                            <td className={clsx("px-2 text-right tabular", polarity(t.realized_pnl))}>
                              {t.realized_pnl === null ? "–" : fmtNum(t.realized_pnl)}
                            </td>
                            <td className="text-right text-xs text-ink-3">
                              {new Date(t.created_at).toLocaleDateString()}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
              </div>
            </div>

            <div className="space-y-5">
              <OrderTicket onDone={refetchAll} />
              <div className="rounded-lg border border-line p-4">
                <h2 className="mb-3 font-medium">Allocation</h2>
                <AllocationBars portfolio={p} />
              </div>
              <div className="rounded-lg border border-line p-4">
                <h2 className="mb-3 font-medium">Portfolio intelligence</h2>
                {intel.data ? (
                  <IntelligencePanel intel={intel.data} />
                ) : (
                  <p className="text-sm text-ink-3">Loading…</p>
                )}
              </div>
            </div>
          </div>
        </>
      )}
    </div>
  );
}
