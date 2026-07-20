"use client";

// Persisted TradingView-style chart (Phase 6, generalized in 6.5). The chart
// instance and its series are created ONCE and updated in place (setData /
// applyOptions / add / remove). Indicators are rendered generically from the
// catalog in lib/indicators.ts.
import {
  AreaSeries,
  BarSeries,
  BaselineSeries,
  CandlestickSeries,
  ColorType,
  HistogramSeries,
  LineSeries,
  LineStyle,
  type LineWidth,
  createChart,
  createSeriesMarkers,
  type IChartApi,
  type ISeriesApi,
  type ISeriesMarkersPluginApi,
  type SeriesType,
  type Time,
} from "lightweight-charts";
import { useTheme } from "next-themes";
import { useCallback, useEffect, useRef, useState } from "react";
import type { ForecastOut, IndicatorPoint, PriceBar } from "@/lib/api";
import { chartColors, toTime, withAlpha } from "@/lib/chart";
import { tradesToMarkers } from "@/lib/chartMarkers.mjs";
import { visibleRangeFor } from "@/lib/chartRanges.mjs";
import { heikinAshi } from "@/lib/heikinAshi.mjs";
import type { IndColor, IndicatorDef } from "@/lib/indicators";

export type ChartType =
  | "candles"
  | "hollow"
  | "bar"
  | "line"
  | "area"
  | "baseline"
  | "heikin-ashi";

const CANDLE_LIKE = new Set<ChartType>(["candles", "hollow", "heikin-ashi"]);
export type TradeMarker = { date: string; side: string; qty: number; price: number };

export type OhlcLegend = {
  date: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
  changePct: number | null;
};

type Args = {
  bars: PriceBar[];
  indicators: IndicatorPoint[];
  activeIndicators: IndicatorDef[];
  volume: boolean;
  forecast: ForecastOut | null;
  chartType: ChartType;
  trades: TradeMarker[];
  showMarkers: boolean;
  height?: number;
};

type AnySeries = ISeriesApi<SeriesType>;

function createMainSeries(chart: IChartApi, type: ChartType): AnySeries {
  switch (type) {
    case "bar":
      return chart.addSeries(BarSeries, {});
    case "line":
      return chart.addSeries(LineSeries, { lineWidth: 2 });
    case "area":
      return chart.addSeries(AreaSeries, { lineWidth: 2 });
    case "baseline":
      return chart.addSeries(BaselineSeries, {});
    default: // candles | hollow | heikin-ashi
      return chart.addSeries(CandlestickSeries, { borderVisible: type === "hollow" });
  }
}

export function useTradingChart({
  bars,
  indicators,
  activeIndicators,
  volume,
  forecast,
  chartType,
  trades,
  showMarkers,
  height = 440,
}: Args) {
  const containerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const series = useRef<Map<string, AnySeries>>(new Map());
  const mainType = useRef<ChartType | null>(null);
  const indSig = useRef<string | null>(null);
  const levelsDone = useRef<Set<string>>(new Set());
  const markersApi = useRef<ISeriesMarkersPluginApi<Time> | null>(null);
  const dataRef = useRef({ bars, indicators });
  const { resolvedTheme } = useTheme();
  const [legend, setLegend] = useState<OhlcLegend | null>(null);

  dataRef.current = { bars, indicators };

  // --- create the chart once ------------------------------------------------
  useEffect(() => {
    if (!containerRef.current) return;
    const c = chartColors();
    const chart = createChart(containerRef.current, {
      height,
      autoSize: true,
      layout: {
        background: { type: ColorType.Solid, color: "transparent" },
        textColor: c.ink3,
        attributionLogo: false,
        fontFamily: "var(--font-sans)",
      },
      grid: {
        vertLines: { color: c.border, style: LineStyle.Dotted },
        horzLines: { color: c.border, style: LineStyle.Dotted },
      },
      rightPriceScale: { borderColor: c.border, scaleMargins: { top: 0.1, bottom: 0.25 } },
      timeScale: { borderColor: c.border, rightOffset: 4 },
    });
    chartRef.current = chart;

    const onMove = (param: { time?: unknown }) => {
      const bs = dataRef.current.bars;
      if (!bs.length) return;
      const idx = param.time ? bs.findIndex((b) => toTime(b.date) === param.time) : bs.length - 1;
      const i = idx < 0 ? bs.length - 1 : idx;
      const b = bs[i];
      const prev = bs[i - 1];
      setLegend({
        date: b.date,
        open: b.open,
        high: b.high,
        low: b.low,
        close: b.close,
        volume: b.volume,
        changePct: prev && prev.close ? (b.close / prev.close - 1) * 100 : null,
      });
    };
    chart.subscribeCrosshairMove(onMove);

    return () => {
      chart.unsubscribeCrosshairMove(onMove);
      chart.remove();
      chartRef.current = null;
      series.current.clear();
      mainType.current = null;
      indSig.current = null;
      levelsDone.current.clear();
      markersApi.current = null;
    };
  }, [height]);

  // --- reconcile series against props (no teardown) -------------------------
  useEffect(() => {
    const chart = chartRef.current;
    if (!chart || bars.length === 0) return;
    const c = chartColors();
    const S = series.current;
    const colorOf = (name: IndColor) =>
      name === "gain" ? c.gain : name === "loss" ? c.loss : name === "ink3" ? c.ink3 : c.accent;

    chart.applyOptions({
      layout: { textColor: c.ink3 },
      grid: { vertLines: { color: c.border }, horzLines: { color: c.border } },
      rightPriceScale: { borderColor: c.border },
      timeScale: { borderColor: c.border },
    });

    const drop = (key: string) => {
      const s = S.get(key);
      if (s) {
        chart.removeSeries(s);
        S.delete(key);
      }
    };

    // Main price series — swap type when chartType changes (markers live on it).
    if (mainType.current !== chartType) {
      markersApi.current?.detach();
      markersApi.current = null;
      drop("main");
      mainType.current = chartType;
    }
    if (!S.get("main")) S.set("main", createMainSeries(chart, chartType));
    const main = S.get("main")!;
    if (CANDLE_LIKE.has(chartType)) {
      const hollow = chartType === "hollow";
      main.applyOptions({
        upColor: hollow ? "transparent" : c.gain,
        downColor: c.loss,
        wickUpColor: c.gain,
        wickDownColor: c.loss,
        borderUpColor: c.gain,
        borderDownColor: c.loss,
        borderVisible: hollow,
      });
      const src = chartType === "heikin-ashi" ? heikinAshi(bars) : bars;
      main.setData(
        src.map((b) => ({ time: toTime(b.date), open: b.open, high: b.high, low: b.low, close: b.close })),
      );
    } else if (chartType === "bar") {
      main.applyOptions({ upColor: c.gain, downColor: c.loss });
      main.setData(
        bars.map((b) => ({ time: toTime(b.date), open: b.open, high: b.high, low: b.low, close: b.close })),
      );
    } else if (chartType === "line") {
      main.applyOptions({ color: c.accent });
      main.setData(bars.map((b) => ({ time: toTime(b.date), value: b.close })));
    } else if (chartType === "area") {
      main.applyOptions({
        lineColor: c.accent,
        topColor: withAlpha(c.accent, 51),
        bottomColor: withAlpha(c.accent, 5),
      });
      main.setData(bars.map((b) => ({ time: toTime(b.date), value: b.close })));
    } else {
      main.applyOptions({
        baseValue: { type: "price", price: bars[0]?.close ?? 0 },
        topLineColor: c.gain,
        bottomLineColor: c.loss,
        topFillColor1: withAlpha(c.gain, 40),
        topFillColor2: withAlpha(c.gain, 8),
        bottomFillColor1: withAlpha(c.loss, 40),
        bottomFillColor2: withAlpha(c.loss, 8),
      });
      main.setData(bars.map((b) => ({ time: toTime(b.date), value: b.close })));
    }

    // Volume histogram on its own hidden scale at the bottom.
    if (volume) {
      if (!S.get("volume")) {
        S.set(
          "volume",
          chart.addSeries(HistogramSeries, {
            priceScaleId: "vol",
            priceFormat: { type: "volume" },
            lastValueVisible: false,
            priceLineVisible: false,
          }),
        );
        chart.priceScale("vol").applyOptions({ scaleMargins: { top: 0.82, bottom: 0 } });
      }
      S.get("volume")!.setData(
        bars.map((b) => ({
          time: toTime(b.date),
          value: b.volume,
          color: withAlpha(b.close >= b.open ? c.gain : c.loss, 90),
        })),
      );
    } else {
      drop("volume");
    }

    // Forecast projection (dashed, stitched from the last close).
    if (forecast && forecast.points.length) {
      const last = bars[bars.length - 1];
      if (!S.get("forecast")) {
        S.set(
          "forecast",
          chart.addSeries(LineSeries, {
            lineStyle: LineStyle.Dashed,
            lineWidth: 2,
            priceLineVisible: false,
            lastValueVisible: true,
          }),
        );
      }
      S.get("forecast")!.applyOptions({ color: c.accent, title: `${forecast.model_name}` });
      S.get("forecast")!.setData([
        { time: toTime(last.date), value: last.close },
        ...forecast.points.map((p) => ({ time: toTime(p.target_date), value: p.predicted_close })),
      ]);
    } else {
      drop("forecast");
    }

    // --- indicators (generic, catalog-driven) -----------------------------
    // Rebuild all indicator series when the enabled set / pane order changes so
    // pane indices stay gap-free.
    const sig = activeIndicators.map((d) => d.id).join(",");
    if (indSig.current !== sig) {
      [...S.keys()].filter((k) => k.startsWith("ind:")).forEach(drop);
      levelsDone.current.clear();
      indSig.current = sig;
    }

    const colData = (col: string) =>
      indicators
        .filter((p) => p.values[col] != null)
        .map((p) => ({ time: toTime(p.date), value: p.values[col] as number }));

    const ensureLine = (key: string, pane: number, width: LineWidth, dashed = false) => {
      if (!S.get(key)) {
        S.set(
          key,
          chart.addSeries(
            LineSeries,
            {
              lineWidth: width,
              lineStyle: dashed ? LineStyle.Dashed : LineStyle.Solid,
              priceLineVisible: false,
              lastValueVisible: false,
              crosshairMarkerVisible: false,
            },
            pane,
          ),
        );
      }
      return S.get(key)!;
    };

    const renderIndicator = (def: IndicatorDef, pane: number) => {
      for (const ln of def.lines ?? []) {
        const s = ensureLine(`ind:${def.id}:${ln.col}`, pane, (ln.width ?? 2) as LineWidth, ln.dashed);
        s.applyOptions({ color: colorOf(ln.color) });
        s.setData(colData(ln.col));
      }
      if (def.band) {
        for (const edge of [def.band.upper, def.band.lower]) {
          const s = ensureLine(`ind:${def.id}:${edge}`, pane, 1 as LineWidth);
          s.applyOptions({ color: withAlpha(c.ink3, 160) });
          s.setData(colData(edge));
        }
      }
      if (def.histogram) {
        const key = `ind:${def.id}:hist`;
        if (!S.get(key)) {
          S.set(
            key,
            chart.addSeries(
              HistogramSeries,
              { priceLineVisible: false, lastValueVisible: false },
              pane,
            ),
          );
        }
        S.get(key)!.setData(
          colData(def.histogram).map((d) => ({
            ...d,
            color: withAlpha(d.value >= 0 ? c.gain : c.loss, 140),
          })),
        );
      }
      // Reference levels — created once on the first line series of the pane.
      if (def.levels && def.lines?.[0] && !levelsDone.current.has(def.id)) {
        const anchor = S.get(`ind:${def.id}:${def.lines[0].col}`);
        if (anchor) {
          for (const lv of def.levels) {
            anchor.createPriceLine({
              price: lv.value,
              color: colorOf(lv.color),
              lineStyle: LineStyle.Dotted,
              lineWidth: 1,
            });
          }
          levelsDone.current.add(def.id);
        }
      }
    };

    for (const def of activeIndicators.filter((d) => !d.pane)) renderIndicator(def, 0);
    activeIndicators
      .filter((d) => d.pane)
      .forEach((def, k) => renderIndicator(def, k + 1));

    // Give the price pane the bulk of the height, sub-panes a slim share.
    const paneApis = chart.panes();
    paneApis[0]?.setStretchFactor(4);
    for (let i = 1; i < paneApis.length; i++) paneApis[i]?.setStretchFactor(1.4);

    // --- trade markers on the price series --------------------------------
    if (showMarkers && trades.length) {
      const m = S.get("main");
      if (m) {
        if (!markersApi.current) markersApi.current = createSeriesMarkers(m, []);
        markersApi.current.setMarkers(tradesToMarkers(trades, { gain: c.gain, loss: c.loss }) as never);
      }
    } else {
      markersApi.current?.setMarkers([]);
    }
  }, [bars, indicators, activeIndicators, volume, forecast, chartType, trades, showMarkers, resolvedTheme]);

  const setRange = useCallback((preset: string) => {
    const chart = chartRef.current;
    if (!chart) return;
    const range = visibleRangeFor(
      dataRef.current.bars.map((b) => b.date),
      preset,
    );
    if (!range) {
      chart.timeScale().fitContent();
      return;
    }
    chart.timeScale().setVisibleRange({ from: toTime(range.from), to: toTime(range.to) });
  }, []);

  const getMain = useCallback(() => series.current.get("main") ?? null, []);

  return { containerRef, legend, setRange, chartRef, getMain };
}
