"use client";

import { useMutation, useQuery } from "@tanstack/react-query";
import { Bot } from "lucide-react";
import { useParams, useRouter } from "next/navigation";
import { useState } from "react";
import clsx from "clsx";
import { CandleChart } from "@/components/CandleChart";
import { ResearchSection } from "@/components/ResearchSection";
import { api, fmtNum, fmtPct, polarity } from "@/lib/api";

const METRIC_LABELS: Record<string, string> = {
  total_return_pct: "Total return",
  sharpe_ratio: "Sharpe",
  max_drawdown_pct: "Max drawdown",
  win_rate: "Win rate",
  volatility_pct: "Volatility",
  num_fills: "Fills",
};

export default function InstrumentPage() {
  const { symbol: raw } = useParams<{ symbol: string }>();
  const symbol = decodeURIComponent(raw);
  const router = useRouter();
  const [overlays, setOverlays] = useState({ sma: true, ema: false });
  const [model, setModel] = useState<"kronos" | "baseline">("baseline");
  const [showForecast, setShowForecast] = useState(false);
  const [btParams, setBtParams] = useState({ fast: 10, slow: 30, engine: "nautilus" });

  const prices = useQuery({ queryKey: ["prices", symbol], queryFn: () => api.prices(symbol) });
  const indicators = useQuery({
    queryKey: ["indicators", symbol],
    queryFn: () => api.indicators(symbol, "sma,ema,rsi"),
  });
  const forecast = useQuery({
    queryKey: ["forecast", symbol, model],
    queryFn: () => api.forecast(symbol, model),
    enabled: showForecast,
    staleTime: Infinity,
  });
  const backtest = useMutation({
    mutationFn: () =>
      api.backtest({ symbol, engine: btParams.engine, params: { fast: btParams.fast, slow: btParams.slow } }),
  });
  const startRun = useMutation({
    mutationFn: () => api.startRun(symbol),
    onSuccess: (run) => router.push(`/agents/${run.id}`),
  });

  const rsiLast = indicators.data?.points.at(-1)?.values["rsi_14"];

  return (
    <div className="space-y-5">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-semibold">{symbol}</h1>
          <p className="text-sm text-ink-2">
            RSI(14): <span className={clsx("tabular", (rsiLast ?? 50) > 70 ? "text-loss" : (rsiLast ?? 50) < 30 ? "text-gain" : "")}>{fmtNum(rsiLast ?? null)}</span>
          </p>
        </div>
        <button
          onClick={() => startRun.mutate()}
          disabled={startRun.isPending}
          className="flex items-center gap-2 rounded-md bg-accent px-3 py-1.5 text-sm font-medium text-white hover:opacity-90 disabled:opacity-50"
        >
          <Bot size={15} /> {startRun.isPending ? "Queuing…" : "Analyze with agents"}
        </button>
      </div>
      {startRun.error && <p className="text-sm text-loss">{String(startRun.error)}</p>}

      <div className="rounded-lg border border-line p-3">
        <div className="mb-2 flex flex-wrap items-center gap-3 text-sm">
          {(["sma", "ema"] as const).map((k) => (
            <label key={k} className="flex items-center gap-1.5 text-ink-2">
              <input
                type="checkbox"
                checked={overlays[k]}
                onChange={(e) => setOverlays({ ...overlays, [k]: e.target.checked })}
              />
              {k.toUpperCase()} 20
            </label>
          ))}
          <span className="mx-1 text-line">|</span>
          <label className="flex items-center gap-1.5 text-ink-2">
            <input
              type="checkbox"
              checked={showForecast}
              onChange={(e) => setShowForecast(e.target.checked)}
            />
            Forecast
          </label>
          {showForecast && (
            <select
              value={model}
              onChange={(e) => setModel(e.target.value as "kronos" | "baseline")}
              className="rounded border border-line bg-surface px-2 py-1 text-xs"
            >
              <option value="baseline">baseline</option>
              <option value="kronos">kronos</option>
            </select>
          )}
          {showForecast && forecast.isLoading && (
            <span className="text-xs text-ink-3">running {model}…</span>
          )}
        </div>
        {prices.isLoading && <div className="py-24 text-center text-sm text-ink-2">Loading chart…</div>}
        {prices.data && indicators.data && (
          <CandleChart
            bars={prices.data.bars}
            indicators={indicators.data.points}
            forecast={showForecast ? (forecast.data ?? null) : null}
            overlays={overlays}
          />
        )}
      </div>

      <div className="rounded-lg border border-line p-4">
        <h2 className="mb-3 font-medium">SMA-crossover backtest</h2>
        <div className="mb-3 flex flex-wrap items-end gap-3 text-sm">
          {(["fast", "slow"] as const).map((k) => (
            <label key={k} className="flex flex-col gap-1 text-xs text-ink-2">
              {k} window
              <input
                type="number"
                value={btParams[k]}
                min={2}
                max={400}
                onChange={(e) => setBtParams({ ...btParams, [k]: Number(e.target.value) })}
                className="w-24 rounded border border-line bg-surface px-2 py-1.5 tabular"
              />
            </label>
          ))}
          <label className="flex flex-col gap-1 text-xs text-ink-2">
            engine
            <select
              value={btParams.engine}
              onChange={(e) => setBtParams({ ...btParams, engine: e.target.value })}
              className="rounded border border-line bg-surface px-2 py-1.5"
            >
              <option value="nautilus">nautilus</option>
              <option value="simple">simple</option>
            </select>
          </label>
          <button
            onClick={() => backtest.mutate()}
            disabled={backtest.isPending}
            className="rounded-md border border-line px-3 py-1.5 hover:bg-surface-2 disabled:opacity-50"
          >
            {backtest.isPending ? "Running…" : "Run backtest"}
          </button>
        </div>
        {backtest.error && <p className="text-sm text-loss">{String(backtest.error)}</p>}
        {backtest.data && (
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-6">
            {Object.entries(METRIC_LABELS).map(([key, label]) => {
              const v = backtest.data.metrics[key];
              const pct = key.endsWith("_pct");
              return (
                <div key={key} className="rounded-md bg-surface-2 p-3">
                  <div className="text-xs text-ink-3">{label}</div>
                  <div className={clsx("tabular text-lg font-semibold", pct ? polarity(v) : "")}>
                    {key === "win_rate" ? fmtPct((v ?? 0) * 100) : pct ? fmtPct(v) : fmtNum(v)}
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>

      <ResearchSection symbol={symbol} />
    </div>
  );
}
