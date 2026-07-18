"use client";

// Persisted TradingView-style chart (Phase 6). The chart instance and its
// series are created ONCE and updated in place (setData / applyOptions / add /
// remove) — unlike the old CandleChart which rebuilt everything on every prop
// change. This keeps the viewport, is cheap at scale, and lets the crosshair
// legend read live data.
import {
  AreaSeries,
  CandlestickSeries,
  ColorType,
  HistogramSeries,
  LineSeries,
  LineStyle,
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

export type ChartType = "candles" | "line";
export type Overlays = { sma: boolean; ema: boolean; volume: boolean };
export type Panes = { rsi: boolean; macd: boolean };
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
  forecast: ForecastOut | null;
  chartType: ChartType;
  overlays: Overlays;
  panes: Panes;
  trades: TradeMarker[];
  showMarkers: boolean;
  height?: number;
};

type AnySeries = ISeriesApi<SeriesType>;

export function useTradingChart({
  bars,
  indicators,
  forecast,
  chartType,
  overlays,
  panes,
  trades,
  showMarkers,
  height = 440,
}: Args) {
  const containerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const series = useRef<Map<string, AnySeries>>(new Map());
  const mainType = useRef<ChartType | null>(null);
  const panesKey = useRef<string | null>(null);
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
      const idx = param.time
        ? bs.findIndex((b) => toTime(b.date) === param.time)
        : bs.length - 1;
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
      panesKey.current = null;
      markersApi.current = null;
    };
  }, [height]);

  // --- reconcile series against props (no teardown) -------------------------
  useEffect(() => {
    const chart = chartRef.current;
    if (!chart || bars.length === 0) return;
    const c = chartColors();
    const S = series.current;

    chart.applyOptions({
      layout: { textColor: c.ink3 },
      grid: {
        vertLines: { color: c.border },
        horzLines: { color: c.border },
      },
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

    // Main price series — swap type when chartType changes (markers live on it,
    // so detach them first; they re-attach below on the new series).
    if (mainType.current !== chartType) {
      markersApi.current?.detach();
      markersApi.current = null;
      drop("main");
      mainType.current = chartType;
    }
    if (!S.get("main")) {
      S.set(
        "main",
        chartType === "candles"
          ? chart.addSeries(CandlestickSeries, { borderVisible: false })
          : chart.addSeries(AreaSeries, { lineWidth: 2 }),
      );
    }
    const main = S.get("main")!;
    if (chartType === "candles") {
      main.applyOptions({
        upColor: c.gain,
        downColor: c.loss,
        wickUpColor: c.gain,
        wickDownColor: c.loss,
      });
      main.setData(
        bars.map((b) => ({
          time: toTime(b.date),
          open: b.open,
          high: b.high,
          low: b.low,
          close: b.close,
        })),
      );
    } else {
      main.applyOptions({
        lineColor: c.accent,
        topColor: withAlpha(c.accent, 51),
        bottomColor: withAlpha(c.accent, 5),
      });
      main.setData(bars.map((b) => ({ time: toTime(b.date), value: b.close })));
    }

    // Volume histogram (overlaid on its own hidden scale at the bottom).
    if (overlays.volume) {
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

    // Indicator overlays.
    const line = (key: string, valueKey: string, color: string, on: boolean) => {
      if (!on) return drop(key);
      const data = indicators
        .filter((p) => p.values[valueKey] != null)
        .map((p) => ({ time: toTime(p.date), value: p.values[valueKey] as number }));
      if (!data.length) return drop(key);
      if (!S.get(key)) {
        S.set(
          key,
          chart.addSeries(LineSeries, {
            lineWidth: 2,
            priceLineVisible: false,
            lastValueVisible: false,
            crosshairMarkerVisible: false,
          }),
        );
      }
      S.get(key)!.applyOptions({ color });
      S.get(key)!.setData(data);
    };
    line("sma", "sma_20", c.accent, overlays.sma);
    line("ema", "ema_20", c.ink3, overlays.ema);

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

    // --- indicator sub-panes (RSI / MACD) ---------------------------------
    // Rebuild pane series only when the enabled set changes, so pane indices
    // stay gap-free (RSI=1, MACD after it) without empty panes.
    const key = `${panes.rsi}:${panes.macd}`;
    if (panesKey.current !== key) {
      ["rsi", "macd_hist", "macd", "macd_signal"].forEach(drop);
      panesKey.current = key;
    }
    const rsiPane = 1;
    const macdPane = panes.rsi ? 2 : 1;
    const seriesData = (valueKey: string) =>
      indicators
        .filter((p) => p.values[valueKey] != null)
        .map((p) => ({ time: toTime(p.date), value: p.values[valueKey] as number }));

    if (panes.rsi) {
      if (!S.get("rsi")) {
        const s = chart.addSeries(
          LineSeries,
          { lineWidth: 2, priceLineVisible: false, lastValueVisible: false },
          rsiPane,
        );
        s.createPriceLine({ price: 70, color: c.loss, lineStyle: LineStyle.Dotted, lineWidth: 1 });
        s.createPriceLine({ price: 30, color: c.gain, lineStyle: LineStyle.Dotted, lineWidth: 1 });
        S.set("rsi", s);
      }
      S.get("rsi")!.applyOptions({ color: c.accent });
      S.get("rsi")!.setData(seriesData("rsi_14"));
    }
    if (panes.macd) {
      if (!S.get("macd_hist")) {
        S.set(
          "macd_hist",
          chart.addSeries(
            HistogramSeries,
            { priceLineVisible: false, lastValueVisible: false },
            macdPane,
          ),
        );
        S.set(
          "macd",
          chart.addSeries(
            LineSeries,
            { lineWidth: 2, priceLineVisible: false, lastValueVisible: false },
            macdPane,
          ),
        );
        S.set(
          "macd_signal",
          chart.addSeries(
            LineSeries,
            { lineWidth: 1, priceLineVisible: false, lastValueVisible: false },
            macdPane,
          ),
        );
      }
      const hist = seriesData("macd_hist").map((d) => ({
        ...d,
        color: withAlpha(d.value >= 0 ? c.gain : c.loss, 140),
      }));
      S.get("macd_hist")!.setData(hist);
      S.get("macd")!.applyOptions({ color: c.accent });
      S.get("macd")!.setData(seriesData("macd"));
      S.get("macd_signal")!.applyOptions({ color: c.ink3 });
      S.get("macd_signal")!.setData(seriesData("macd_signal"));
    }
    // Give the price pane the bulk of the height, sub-panes a slim share.
    const paneApis = chart.panes();
    paneApis[0]?.setStretchFactor(4);
    for (let i = 1; i < paneApis.length; i++) paneApis[i]?.setStretchFactor(1.4);

    // --- trade markers on the price series --------------------------------
    if (showMarkers && trades.length) {
      const main2 = S.get("main");
      if (main2) {
        if (!markersApi.current) markersApi.current = createSeriesMarkers(main2, []);
        markersApi.current.setMarkers(
          tradesToMarkers(trades, { gain: c.gain, loss: c.loss }) as never,
        );
      }
    } else {
      markersApi.current?.setMarkers([]);
    }
  }, [bars, indicators, forecast, chartType, overlays, panes, trades, showMarkers, resolvedTheme]);

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

  return { containerRef, legend, setRange, chartRef };
}
