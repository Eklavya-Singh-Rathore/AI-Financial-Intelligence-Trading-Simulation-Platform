"use client";

import {
  ChevronDown,
  type LucideIcon,
  Maximize2,
  Minimize2,
  Minus,
  MousePointer2,
  MoveRight,
  PenLine,
  Redo2,
  Ruler,
  Spline,
  Square,
  Trash2,
  Type as TypeIcon,
  Undo2,
} from "lucide-react";
import { useEffect, useRef, useState } from "react";
import type { ForecastOut, IndicatorPoint, PriceBar } from "@/lib/api";
import { fmtNum, fmtPct, polarity } from "@/lib/api";
import { INTERVALS, defaultRangeForInterval, rangesForInterval } from "@/lib/chartIntervals.mjs";
import { loadDrawings, saveDrawings } from "@/lib/chartDrawings.mjs";
import { INDICATORS, enabledDefs } from "@/lib/indicators";
import { cn } from "@/lib/ui";
import { DrawingCanvas, type Drawing, type DrawTool } from "./DrawingCanvas";
import {
  type ChartType,
  type TradeMarker,
  useTradingChart,
} from "./useTradingChart";

const DRAW_TOOLS: { id: DrawTool; label: string; Icon: LucideIcon }[] = [
  { id: "select", label: "Select / move / delete", Icon: MousePointer2 },
  { id: "trendline", label: "Trend line", Icon: PenLine },
  { id: "horizontal", label: "Horizontal line", Icon: Minus },
  { id: "ray", label: "Ray", Icon: MoveRight },
  { id: "rectangle", label: "Rectangle", Icon: Square },
  { id: "fib", label: "Fibonacci retracement", Icon: Spline },
  { id: "measure", label: "Measure", Icon: Ruler },
  { id: "text", label: "Text label", Icon: TypeIcon },
];

const CHART_TYPES: { id: ChartType; label: string }[] = [
  { id: "candles", label: "Candles" },
  { id: "hollow", label: "Hollow" },
  { id: "heikin-ashi", label: "Heikin Ashi" },
  { id: "bar", label: "Bar" },
  { id: "line", label: "Line" },
  { id: "area", label: "Area" },
  { id: "baseline", label: "Baseline" },
];

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
        "rounded px-1.5 py-1 text-xs font-medium transition-colors",
        active ? "bg-accent/10 text-accent" : "text-ink-3 hover:bg-surface-2 hover:text-ink",
      )}
    >
      {children}
    </button>
  );
}

const Sep = () => <span className="mx-1 h-4 w-px shrink-0 bg-line" />;

function IndicatorPicker({
  enabled,
  onChange,
}: {
  enabled: string[];
  onChange: (ids: string[]) => void;
}) {
  const [open, setOpen] = useState(false);
  const set = new Set(enabled);
  const toggle = (id: string) => {
    const next = new Set(set);
    if (next.has(id)) next.delete(id);
    else next.add(id);
    onChange(INDICATORS.filter((i) => next.has(i.id)).map((i) => i.id));
  };
  const overlays = INDICATORS.filter((i) => !i.pane);
  const panes = INDICATORS.filter((i) => i.pane);

  const Group = ({ title, defs }: { title: string; defs: typeof INDICATORS }) => (
    <div className="min-w-[9rem]">
      <div className="mb-1 text-[10px] font-semibold uppercase tracking-wide text-ink-3">{title}</div>
      {defs.map((d) => (
        <label
          key={d.id}
          className="flex cursor-pointer items-center gap-1.5 rounded px-1 py-0.5 text-xs text-ink-2 hover:bg-surface-2"
        >
          <input type="checkbox" checked={set.has(d.id)} onChange={() => toggle(d.id)} className="accent-accent" />
          {d.label}
        </label>
      ))}
    </div>
  );

  return (
    <div className="relative">
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        className="flex items-center gap-1 rounded px-1.5 py-1 text-xs font-medium text-ink-2 hover:bg-surface-2 hover:text-ink"
      >
        Indicators{enabled.length > 0 && <span className="text-accent">({enabled.length})</span>}
        <ChevronDown size={12} />
      </button>
      {open && (
        <>
          <div className="fixed inset-0 z-10" onClick={() => setOpen(false)} aria-hidden />
          <div className="absolute left-0 top-full z-20 mt-1 flex gap-4 rounded-md border border-line bg-surface p-3 shadow-md">
            <Group title="Overlays" defs={overlays} />
            <Group title="Oscillators" defs={panes} />
          </div>
        </>
      )}
    </div>
  );
}

export function TradingChart({
  bars,
  indicators,
  forecast,
  trades = [],
  interval,
  onIntervalChange,
  enabled,
  onEnabledChange,
  symbol,
  levels = [],
  height = 440,
}: {
  bars: PriceBar[];
  indicators: IndicatorPoint[];
  forecast: ForecastOut | null;
  trades?: TradeMarker[];
  interval: string;
  onIntervalChange: (interval: string) => void;
  enabled: string[];
  onEnabledChange: (ids: string[]) => void;
  symbol: string;
  levels?: { price: number; label: string; color: "gain" | "loss" | "accent" }[];
  height?: number;
}) {
  const [chartType, setChartType] = useState<ChartType>("candles");
  const [volume, setVolume] = useState(true);
  const [showMarkers, setShowMarkers] = useState(true);
  const [range, setRange] = useState<string>(() => defaultRangeForInterval(interval));

  // Drawings (Phase 6.5) — per-symbol, persisted, with an undo/redo stack.
  const [tool, setTool] = useState<DrawTool | null>(null);
  const [drawings, setDrawings] = useState<Drawing[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [showVP, setShowVP] = useState(false);
  const history = useRef<Drawing[][]>([[]]);
  const histIdx = useRef(0);

  useEffect(() => {
    const d = loadDrawings(symbol) as Drawing[];
    setDrawings(d);
    history.current = [d];
    histIdx.current = 0;
    setSelectedId(null);
    setTool(null);
  }, [symbol]);

  const commit = (next: Drawing[]) => {
    history.current = history.current.slice(0, histIdx.current + 1);
    history.current.push(next);
    histIdx.current = history.current.length - 1;
    setDrawings(next);
    saveDrawings(symbol, next);
  };
  const handleDrawingChange = (next: Drawing[], doCommit: boolean) => {
    if (doCommit) commit(next);
    else setDrawings(next); // live drag preview — not pushed to history
  };
  const undo = () => {
    if (histIdx.current > 0) {
      histIdx.current -= 1;
      const d = history.current[histIdx.current];
      setDrawings(d);
      saveDrawings(symbol, d);
      setSelectedId(null);
    }
  };
  const redo = () => {
    if (histIdx.current < history.current.length - 1) {
      histIdx.current += 1;
      const d = history.current[histIdx.current];
      setDrawings(d);
      saveDrawings(symbol, d);
    }
  };
  const deleteSelected = () => {
    if (!selectedId) return;
    commit(drawings.filter((d) => d.id !== selectedId));
    setSelectedId(null);
  };
  // Delete key removes the selected drawing.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.key === "Delete" || e.key === "Backspace") && selectedId) {
        e.preventDefault();
        deleteSelected();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedId, drawings]);

  const cardRef = useRef<HTMLDivElement>(null);
  const [isFs, setIsFs] = useState(false);

  const { containerRef, legend, setRange: applyRange, chartRef, getMain, ready } = useTradingChart({
    bars,
    indicators,
    activeIndicators: enabledDefs(enabled),
    volume,
    forecast,
    chartType,
    trades,
    showMarkers,
    height,
  });

  const hasData = bars.length > 0;
  useEffect(() => {
    setRange(defaultRangeForInterval(interval));
  }, [interval]);
  useEffect(() => {
    if (hasData) applyRange(range);
  }, [range, hasData, applyRange, bars]);

  useEffect(() => {
    const onFs = () => setIsFs(document.fullscreenElement === cardRef.current);
    document.addEventListener("fullscreenchange", onFs);
    return () => document.removeEventListener("fullscreenchange", onFs);
  }, []);
  const toggleFs = () => {
    if (document.fullscreenElement) document.exitFullscreen();
    else cardRef.current?.requestFullscreen?.();
  };
  const ranges = rangesForInterval(interval);

  return (
    <div ref={cardRef} className={cn("rounded-lg border border-line bg-surface", isFs && "flex flex-col")}>
      {/* Toolbar */}
      <div className="flex flex-wrap items-center justify-between gap-2 border-b border-line px-2.5 py-1.5">
        <div className="flex flex-wrap items-center gap-1">
          <div className="flex items-center rounded-md border border-line p-0.5">
            {INTERVALS.map((iv) => (
              <Toggle key={iv.id} active={interval === iv.id} onClick={() => onIntervalChange(iv.id)}>
                {iv.label}
              </Toggle>
            ))}
          </div>
          <Sep />
          <select
            value={chartType}
            onChange={(e) => setChartType(e.target.value as ChartType)}
            title="Chart type"
            className="rounded-md border border-line bg-surface px-1.5 py-1 text-xs text-ink-2 outline-none focus:border-accent"
          >
            {CHART_TYPES.map((t) => (
              <option key={t.id} value={t.id}>
                {t.label}
              </option>
            ))}
          </select>
          <Sep />
          <IndicatorPicker enabled={enabled} onChange={onEnabledChange} />
          <Toggle active={volume} onClick={() => setVolume((v) => !v)} title="Volume">
            Vol
          </Toggle>
          <Toggle active={showVP} onClick={() => setShowVP((v) => !v)} title="Volume Profile">
            VP
          </Toggle>
          {trades.length > 0 && (
            <Toggle active={showMarkers} onClick={() => setShowMarkers((m) => !m)} title="Trade markers">
              Trades
            </Toggle>
          )}
        </div>
        <div className="flex items-center gap-0.5">
          {ranges.map((p) => (
            <Toggle key={p} active={range === p} onClick={() => setRange(p)}>
              {p}
            </Toggle>
          ))}
          <Sep />
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

      {/* Chart + crosshair legend + drawing overlay */}
      <div className={cn("relative", isFs && "flex-1")}>
        {/* Drawing tool rail */}
        <div className="absolute left-1 top-1 z-30 flex flex-col gap-0.5 rounded-md border border-line bg-surface/95 p-0.5 shadow-xs">
          {DRAW_TOOLS.map(({ id, label, Icon }) => (
            <button
              key={id}
              type="button"
              title={label}
              onClick={() => setTool((t) => (t === id ? null : id))}
              className={cn(
                "rounded p-1 transition-colors",
                tool === id ? "bg-accent/10 text-accent" : "text-ink-3 hover:bg-surface-2 hover:text-ink",
              )}
            >
              <Icon size={14} />
            </button>
          ))}
          <span className="my-0.5 h-px w-full bg-line" />
          <button type="button" title="Undo" onClick={undo} className="rounded p-1 text-ink-3 transition-colors hover:bg-surface-2 hover:text-ink">
            <Undo2 size={14} />
          </button>
          <button type="button" title="Redo" onClick={redo} className="rounded p-1 text-ink-3 transition-colors hover:bg-surface-2 hover:text-ink">
            <Redo2 size={14} />
          </button>
          <button
            type="button"
            title="Clear all drawings"
            onClick={() => {
              commit([]);
              setSelectedId(null);
            }}
            className="rounded p-1 text-ink-3 transition-colors hover:bg-surface-2 hover:text-loss"
          >
            <Trash2 size={14} />
          </button>
        </div>
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
        <div ref={containerRef} className="w-full" style={{ height: isFs ? "100%" : height }} />
        {hasData && (
          <DrawingCanvas
            chartRef={chartRef}
            getMain={getMain}
            ready={ready}
            tool={tool}
            drawings={drawings}
            selectedId={selectedId}
            setSelectedId={setSelectedId}
            onChange={handleDrawingChange}
            onToolDone={() => setTool(null)}
            bars={bars}
            showVolumeProfile={showVP}
            levels={levels}
          />
        )}
        {!hasData && (
          <div className="absolute inset-0 flex items-center justify-center text-sm text-ink-3">
            No price history yet.
          </div>
        )}
      </div>
    </div>
  );
}
