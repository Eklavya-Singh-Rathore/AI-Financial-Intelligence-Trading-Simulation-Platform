"use client";

import { CandlestickChart, LineChart } from "lucide-react";
import { useEffect, useState } from "react";
import type { ForecastOut, IndicatorPoint, PriceBar } from "@/lib/api";
import { fmtNum, fmtPct, polarity } from "@/lib/api";
import { RANGE_PRESETS } from "@/lib/chartRanges.mjs";
import { cn } from "@/lib/ui";
import { type ChartType, type Overlays, useTradingChart } from "./useTradingChart";

function Toggle({
  active,
  onClick,
  children,
  title,
}: {
  active: boolean;
  onClick: () => void;
  children: React.ReactNode;
  title?: string;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      title={title}
      className={cn(
        "rounded-md px-2 py-1 text-xs font-medium transition-colors",
        active ? "bg-accent/10 text-accent" : "text-ink-3 hover:bg-surface-2 hover:text-ink",
      )}
    >
      {children}
    </button>
  );
}

export function TradingChart({
  bars,
  indicators,
  forecast,
  height = 440,
}: {
  bars: PriceBar[];
  indicators: IndicatorPoint[];
  forecast: ForecastOut | null;
  height?: number;
}) {
  const [chartType, setChartType] = useState<ChartType>("candles");
  const [overlays, setOverlays] = useState<Overlays>({ sma: true, ema: false, volume: true });
  const [range, setRange] = useState<string>("6M");

  const { containerRef, legend, setRange: applyRange } = useTradingChart({
    bars,
    indicators,
    forecast,
    chartType,
    overlays,
    height,
  });

  // Apply the default range when data first loads, and on preset change.
  const hasData = bars.length > 0;
  useEffect(() => {
    if (hasData) applyRange(range);
  }, [range, hasData, applyRange]);

  const toggle = (k: keyof Overlays) => setOverlays((o) => ({ ...o, [k]: !o[k] }));

  return (
    <div className="rounded-lg border border-line bg-surface">
      {/* Toolbar */}
      <div className="flex flex-wrap items-center justify-between gap-2 border-b border-line px-2.5 py-1.5">
        <div className="flex items-center gap-1">
          <div className="flex items-center rounded-md border border-line p-0.5">
            <Toggle active={chartType === "candles"} onClick={() => setChartType("candles")} title="Candles">
              <CandlestickChart size={14} />
            </Toggle>
            <Toggle active={chartType === "line"} onClick={() => setChartType("line")} title="Line">
              <LineChart size={14} />
            </Toggle>
          </div>
          <span className="mx-1 h-4 w-px bg-line" />
          <Toggle active={overlays.sma} onClick={() => toggle("sma")} title="20-period simple MA">
            SMA
          </Toggle>
          <Toggle active={overlays.ema} onClick={() => toggle("ema")} title="20-period exponential MA">
            EMA
          </Toggle>
          <Toggle active={overlays.volume} onClick={() => toggle("volume")} title="Volume">
            Vol
          </Toggle>
        </div>
        <div className="flex items-center gap-0.5">
          {RANGE_PRESETS.map((p) => (
            <Toggle key={p} active={range === p} onClick={() => setRange(p)}>
              {p}
            </Toggle>
          ))}
        </div>
      </div>

      {/* Chart + crosshair legend */}
      <div className="relative">
        {legend && (
          <div className="pointer-events-none absolute left-2.5 top-2 z-10 flex flex-wrap items-center gap-x-3 gap-y-0.5 text-[11px]">
            <span className="text-ink-3">{legend.date}</span>
            <span className="tabular text-ink-2">
              O <span className="text-ink">{fmtNum(legend.open)}</span>
            </span>
            <span className="tabular text-ink-2">
              H <span className="text-ink">{fmtNum(legend.high)}</span>
            </span>
            <span className="tabular text-ink-2">
              L <span className="text-ink">{fmtNum(legend.low)}</span>
            </span>
            <span className="tabular text-ink-2">
              C <span className="text-ink">{fmtNum(legend.close)}</span>
            </span>
            {legend.changePct !== null && (
              <span className={cn("tabular", polarity(legend.changePct))}>{fmtPct(legend.changePct)}</span>
            )}
            <span className="tabular text-ink-3">Vol {fmtNum(legend.volume, 0)}</span>
          </div>
        )}
        {/* Container is ALWAYS mounted so the create-once effect can attach; the
            empty message overlays it until bars arrive. */}
        <div ref={containerRef} className="w-full" style={{ height }} />
        {!hasData && (
          <div className="absolute inset-0 flex items-center justify-center text-sm text-ink-3">
            No price history yet.
          </div>
        )}
      </div>
    </div>
  );
}
