"use client";

import { useMutation, useQuery } from "@tanstack/react-query";
import { Bot, Info } from "lucide-react";
import { useParams, useRouter } from "next/navigation";
import { useEffect, useMemo, useState } from "react";
import clsx from "clsx";
import { TradingChart } from "@/components/chart/TradingChart";
import { ResearchSection } from "@/components/ResearchSection";
import { WatchlistStar } from "@/components/WatchlistStar";
import { Button, ErrorBoundary, Tooltip } from "@/components/ui";
import { api, fmtNum, fmtPct, polarity } from "@/lib/api";
import { DEFAULT_INTERVAL, isIntradayInterval } from "@/lib/chartIntervals.mjs";
import { INDICATOR_IDS, backendNames } from "@/lib/indicators";
import { loadEnabledIndicators, saveEnabledIndicators } from "@/lib/chartPresets.mjs";
import { supportResistance } from "@/lib/supportResistance.mjs";

const METRIC_LABELS: Record<string, string> = {
  total_return_pct: "Total return",
  sharpe_ratio: "Sharpe",
  max_drawdown_pct: "Max drawdown",
  win_rate: "Win rate",
  volatility_pct: "Volatility",
  num_fills: "Fills",
};

const WINDOW_TIPS = {
  fast: "The shorter moving-average length in bars — reacts quickly to price. Smaller = more sensitive with more signals. Typical: 5–20 (e.g. 10).",
  slow: "The longer moving-average length in bars — the trend baseline. Larger = smoother with fewer signals. Typical: 20–50 (e.g. 30); it must be greater than the fast window.",
} as const;

/** Small info icon with an explanatory tooltip (Phase 7). */
function InfoTip({ text }: { text: string }) {
  return (
    <Tooltip content={text} className="max-w-xs whitespace-normal text-left font-normal text-ink-2">
      <span className="cursor-help text-ink-3 transition-colors hover:text-ink">
        <Info size={13} />
      </span>
    </Tooltip>
  );
}

export default function InstrumentPage() {
  const { symbol: raw } = useParams<{ symbol: string }>();
  const symbol = decodeURIComponent(raw);
  const router = useRouter();
  // Phase 6: Kronos is the default forecaster and shows on load (users can
  // still switch to baseline or hide it). First call per idle symbol rides the
  // Space wake-up, covered by the proxy maxDuration + keepalive.
  const [model, setModel] = useState<"kronos" | "baseline">("kronos");
  const [showForecast, setShowForecast] = useState(true);
  const [btParams, setBtParams] = useState({ fast: 10, slow: 30, engine: "nautilus" });
  // Chart interval (Phase 6.5): daily by default; intraday grains fetch from yfinance.
  const [interval, setChartInterval] = useState<string>(DEFAULT_INTERVAL);
  const intraday = isIntradayInterval(interval);
  // Enabled indicators (Phase 6.5): default set, then hydrate from localStorage.
  const [enabled, setEnabled] = useState<string[]>(["sma", "rsi"]);
  useEffect(() => {
    setEnabled(loadEnabledIndicators(INDICATOR_IDS, ["sma", "rsi"]));
  }, []);
  const changeIndicators = (ids: string[]) => {
    setEnabled(ids);
    saveEnabledIndicators(ids);
  };
  // Always request rsi (for the header badge) plus the enabled indicators.
  const indicatorNames = backendNames([...new Set(["rsi", ...enabled])]);
  // Chart overlays + docked trading (Phase 6.5).
  const [showSR, setShowSR] = useState(false);

  // 2000 bars covers the daily 3Y/MAX presets and a full intraday window.
  const prices = useQuery({
    queryKey: ["prices", symbol, interval],
    queryFn: () => api.prices(symbol, 2000, interval),
  });
  // Backfill status for freshly tracked symbols (Phase 6): poll while queued/running.
  const track = useQuery({
    queryKey: ["trackStatus", symbol],
    queryFn: () => api.trackStatus(symbol),
    retry: false,
    refetchInterval: (q) =>
      q.state.data && ["queued", "running"].includes(q.state.data.status) ? 2500 : false,
  });
  const backfilling = track.data && ["queued", "running"].includes(track.data.status);
  const indicators = useQuery({
    queryKey: ["indicators", symbol, interval, indicatorNames],
    queryFn: () => api.indicators(symbol, indicatorNames, interval),
  });
  // Trades for this symbol → buy/sell markers on the chart (memoized so the
  // chart effect doesn't re-run on every render).
  const trades = useQuery({ queryKey: ["simTrades"], queryFn: api.simTrades, staleTime: 60_000 });
  const symbolTrades = useMemo(
    () =>
      (trades.data ?? [])
        .filter((t) => t.symbol === symbol)
        .map((t) => ({ date: t.created_at.slice(0, 10), side: t.side, qty: t.qty, price: t.price })),
    [trades.data, symbol],
  );
  const forecast = useQuery({
    queryKey: ["forecast", symbol, model, interval],
    queryFn: () => api.forecast(symbol, model, 5, interval),
    enabled: showForecast, // Phase 6.1: Kronos forecasts every interval, incl. intraday
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
  const watchlists = useQuery({ queryKey: ["watchlists"], queryFn: api.watchlists });
  const srLevels = useMemo(() => {
    if (!showSR) return [];
    return supportResistance(prices.data?.bars ?? [], { window: 5, max: 3 }).map((l) => ({
      price: l.price,
      label: l.kind === "resistance" ? "R" : "S",
      color: (l.kind === "resistance" ? "loss" : "gain") as "loss" | "gain",
    }));
  }, [showSR, prices.data]);

  return (
    <div className="space-y-5">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="flex items-center gap-1.5 text-xl font-semibold">
            {symbol}
            <WatchlistStar symbol={symbol} watchlists={watchlists.data ?? []} size={17} />
          </h1>
          <p className="text-sm text-ink-2">
            RSI(14): <span className={clsx("tabular", (rsiLast ?? 50) > 70 ? "text-loss" : (rsiLast ?? 50) < 30 ? "text-gain" : "")}>{fmtNum(rsiLast ?? null)}</span>
          </p>
        </div>
        <Button onClick={() => startRun.mutate()} disabled={startRun.isPending}>
          <Bot size={15} /> {startRun.isPending ? "Queuing…" : "Analyze with agents"}
        </Button>
      </div>
      {startRun.error && <p className="text-sm text-loss">{String(startRun.error)}</p>}
      {backfilling && (
        <div className="rounded-md border border-accent/30 bg-accent/5 p-2.5 text-sm text-accent">
          Backfilling price history… the chart will fill in shortly.
        </div>
      )}

      <ErrorBoundary label="Chart">
      <div className="space-y-2">
        <div className="flex flex-wrap items-center gap-3 text-sm">
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
              <option value="kronos">kronos</option>
              <option value="baseline">baseline</option>
            </select>
          )}
          {showForecast && forecast.isLoading && (
            <span className="text-xs text-ink-3">running {model}…</span>
          )}
          {showForecast && forecast.error && (
            <span className="text-xs text-loss">forecast unavailable</span>
          )}
          {intraday && (
            <span className="text-xs text-ink-3">
              intraday ({interval}) from yfinance — delayed, recent window
            </span>
          )}
        </div>
        <label className="flex w-fit items-center gap-1.5 text-sm text-ink-2">
          <input type="checkbox" checked={showSR} onChange={(e) => setShowSR(e.target.checked)} />
          Support / resistance overlay
        </label>
        <TradingChart
          bars={prices.data?.bars ?? []}
          indicators={indicators.data?.points ?? []}
          forecast={showForecast ? (forecast.data ?? null) : null}
          trades={symbolTrades}
          interval={interval}
          onIntervalChange={setChartInterval}
          enabled={enabled}
          onEnabledChange={changeIndicators}
          symbol={symbol}
          levels={srLevels}
        />
      </div>
      </ErrorBoundary>

      <div className="rounded-lg border border-line p-4">
        <h2 className="mb-3 flex items-center gap-1.5 font-medium">
          SMA-crossover backtest
          <InfoTip text="Simulates a strategy that buys when a fast moving average crosses above a slower one and sells when it crosses below, then measures how that rule would have performed on this instrument's history. Results are hypothetical, not a prediction." />
        </h2>
        <div className="mb-3 flex flex-wrap items-end gap-3 text-sm">
          {(["fast", "slow"] as const).map((k) => (
            <label key={k} className="flex flex-col gap-1 text-xs text-ink-2">
              <span className="flex items-center gap-1">
                {k} window
                <InfoTip text={WINDOW_TIPS[k]} />
              </span>
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

      <ErrorBoundary label="Research">
        <ResearchSection symbol={symbol} />
      </ErrorBoundary>
    </div>
  );
}
