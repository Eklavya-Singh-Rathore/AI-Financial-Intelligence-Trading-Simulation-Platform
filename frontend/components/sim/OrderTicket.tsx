"use client";

import { useMutation, useQuery } from "@tanstack/react-query";
import { useState } from "react";
import clsx from "clsx";
import { Button, Input, Select } from "@/components/ui";
import { api, fmtNum, type OrderCreate } from "@/lib/api";
import { validateOrder } from "@/lib/orderTicket.mjs";

/** Order entry with live cost estimate + buying-power pre-validation (Phase 6). */
export function OrderTicket({ buyingPower, onDone }: { buyingPower?: number; onDone: () => void }) {
  const [form, setForm] = useState<OrderCreate>({
    symbol: "", side: "buy", order_type: "market", qty: 1,
  });
  // Latest closes (for cost estimate on market orders); cached across the app.
  const summary = useQuery({ queryKey: ["summary-all"], queryFn: () => api.summary({ limit: 500 }), staleTime: 60_000 });
  const lastPrice = summary.data?.items.find(
    (i) => i.symbol === form.symbol.trim().toUpperCase(),
  )?.last_close;

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

  const check = validateOrder({
    side: form.side,
    orderType: form.order_type,
    qty: form.qty,
    limitPrice: form.limit_price,
    stopPrice: form.stop_price,
    buyingPower,
    lastPrice: lastPrice ?? undefined,
  });
  const canSubmit = !!form.symbol.trim() && check.ok && !place.isPending;

  return (
    <div className="space-y-2.5">
      <Input
        value={form.symbol}
        onChange={(e) => set({ symbol: e.target.value })}
        placeholder="symbol e.g. RELIANCE"
      />
      <div className="grid grid-cols-2 gap-2">
        <Select value={form.side} onChange={(e) => set({ side: e.target.value as "buy" | "sell" })}>
          <option value="buy">buy</option>
          <option value="sell">sell</option>
        </Select>
        <Select
          value={form.order_type}
          onChange={(e) => set({ order_type: e.target.value as OrderCreate["order_type"] })}
        >
          <option value="market">market</option>
          <option value="limit">limit</option>
          <option value="stop">stop</option>
        </Select>
      </div>
      <label className="block text-xs text-ink-2">
        quantity
        <Input type="number" min={1} value={form.qty} onChange={(e) => set({ qty: Number(e.target.value) })} className="tabular mt-1" />
      </label>
      {form.order_type === "limit" && (
        <label className="block text-xs text-ink-2">
          limit price
          <Input type="number" min={0.05} step={0.05} value={form.limit_price ?? ""} onChange={(e) => set({ limit_price: Number(e.target.value) })} className="tabular mt-1" />
        </label>
      )}
      {form.order_type === "stop" && (
        <label className="block text-xs text-ink-2">
          stop price
          <Input type="number" min={0.05} step={0.05} value={form.stop_price ?? ""} onChange={(e) => set({ stop_price: Number(e.target.value) })} className="tabular mt-1" />
        </label>
      )}

      {check.cost != null && (
        <div className="flex items-center justify-between text-xs text-ink-2">
          <span>Est. {form.order_type === "market" ? "cost" : "value"}</span>
          <span className="tabular">₹{fmtNum(check.cost)}</span>
        </div>
      )}
      {form.symbol.trim() && !check.ok && check.reason && (
        <p className="text-xs text-loss">{check.reason}</p>
      )}
      {place.error && <p className="text-xs text-loss">{String(place.error)}</p>}

      <Button
        variant={form.side === "buy" ? "primary" : "danger"}
        onClick={() => place.mutate()}
        disabled={!canSubmit}
        className={clsx("w-full", form.side === "buy" && "bg-gain")}
      >
        {place.isPending ? "…" : `${form.side} ${form.symbol.trim().toUpperCase() || "…"}`}
      </Button>
      <p className="text-[11px] leading-snug text-ink-3">
        Market fills at the latest stored close; limit/stop orders rest and trigger on daily bars.
        Paper simulation only.
      </p>
    </div>
  );
}
