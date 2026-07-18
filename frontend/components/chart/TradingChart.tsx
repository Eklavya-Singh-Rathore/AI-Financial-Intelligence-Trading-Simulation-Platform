"use client";

import { CandlestickChart, LineChart, Maximize2, Minimize2 } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import type { ForecastOut, IndicatorPoint, PriceBar } from "@/lib/api";
import { fmtNum, fmtPct, polarity } from "@/lib/api";
import { RANGE_PRESETS } from "@/lib/chartRanges.mjs";
import { cn } from "@/lib/ui";
import {
  type ChartType,
  type Overlays,
  type Panes,
  type TradeMarker,
  useTradingChart,
} from "./useTradingChart";

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
  trades = [],
  height = 440,
}: {
  bars: PriceBar[];
  indicators: IndicatorPoint[];
  forecast: ForecastOut | null;
  trades?: TradeMarker[];
  height?: number;
}) {
  const [chartType, setChartType] = useState<ChartType>("candles");
  const [overlays, setOverlays] = useState<Overlays>({ sma: true, ema: false, volume: true });
  const [panes, setPanes] = useState<Panes>({ rsi: false, macd: false });
  const [showMarkers, setShowMarkers] = useState(true);
  const [range, setRange] = useState<string>("6M");

  const cardRef = useRef<HTMLDivElement>(null);
  const [isFs, setIsFs] = useState(false);

  const { containerRef, legend, setRange: applyRange } = useTradingChart({
    bars,
    indicators,
    forecast,
    chartType,
    overlays,
    panes,
    trades,
    showMarkers,
    height,
  });

  const hasData = bars.length > 0;
  useEffect(() => {
    if (hasData) applyRange(range);
  }, [range, hasData, applyRange]);

  useEffect(() => {
    const onFs = () => setIsFs(document.fullscreenElement === cardRef.current);
    document.addEventListener("fullscreenchange", onFs);
    return () => document.removeEventListener("fullscreenchange", onFs);
  }, []);
  const toggleFs = () => {
    if (document.fullscreenElement) document.exitFullscreen();
    else cardRef.current?.requestFullscreen?.();
  };

  const toggleOverlay = (k: keyof Overlays) => setOverlays((o) => ({ ...o, [k]: !o[k] }));
  const togglePane = (k: keyof Panes) => setPanes((p) => ({ ...p, [k]: !p[k] }));

  return (
    <div ref={cardRef} className={cn("rounded-lg border border-line bg-surface", isFs && "flex flex-col")}>
      {/* Toolbar */}
      <div className="flex flex-wrap items-center justify-between gap-2 border-b border-line px-2.5 py-1.5">
        <div className="flex flex-wrap items-center gap-1">
          <div className="flex items-center rounded-md border border-line p-0.5">
            <Toggle active={chartType === "candles"} onClick={() => setChartType("candles")} title="Candles">
              <CandlestickChart size={14} />
            </Toggle>
            <Toggle active={chartType === "line"} onClick={() => setChartType("line")} title="Line">
              <LineChart size={14} />
            </Toggle>
          </div>
          <span className="mx-1 h-4 w-px bg-line" />
          <Toggle active={overlays.sma} onClick={() => toggleOverlay("sma")} title="20-period simple MA">
            SMA
          </Toggle>
          <Toggle active={overlays.ema} onClick={() => toggleOverlay("ema")} title="20-period exponential MA">
            EMA
          </Toggle>
          <Toggle active={overlays.volume} onClick={() => toggleOverlay("volume")} title="Volume">
            Vol
          </Toggle>
          <span className="mx-1 h-4 w-px bg-line" />
          <Toggle active={panes.rsi} onClick={() => togglePane("rsi")} title="RSI pane">
            RSI
          </Toggle>
          <Toggle active={panes.macd} onClick={() => togglePane("macd")} title="MACD pane">
            MACD
          </Toggle>
          {trades.length > 0 && (
            <Toggle active={showMarkers} onClick={() => setShowMarkers((m) => !m)} title="Trade markers">
              Trades
            </Toggle>
          )}
        </div>
        <div className="flex items-center gap-0.5">
          {RANGE_PRESETS.map((p) => (
            <Toggle key={p} active={range === p} onClick={() => setRange(p)}>
              {p}
            </Toggle>
          ))}
          <span className="mx-1 h-4 w-px bg-line" />
          <button
            type="button"
            onClick={toggleFs}
            title={isFs ? "Exit fullscreen" : "Fullscreen"}
            className="rounded-md p-1 text-ink-3 transition-colors hover:bg-surface-2 hover:text-ink"
          >
            {isFs ? <Minimize2 size={14} /> : <Maximize2 size={14} />}
          </button>
        </div>
      </div>

      {/* Chart + crosshair legend */}
      <div className={cn("relative", isFs && "flex-1")}>
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
        {/* Container is ALWAYS mounted so the create-once effect can attach. */}
        <div
          ref={containerRef}
          className="w-full"
          style={{ height: isFs ? "100%" : height }}
        />
        {!hasData && (
          <div className="absolute inset-0 flex items-center justify-center text-sm text-ink-3">
            No price history yet.
          </div>
        )}
      </div>
    </div>
  );
}
