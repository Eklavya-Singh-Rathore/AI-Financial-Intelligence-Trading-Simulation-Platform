"use client";

// TradingView lightweight-charts v5 wrapper: candles + optional SMA/EMA
// overlays + dashed forecast projection. Theme-aware via CSS variables.
import {
  CandlestickSeries,
  ColorType,
  LineSeries,
  LineStyle,
  createChart,
  type IChartApi,
  type UTCTimestamp,
} from "lightweight-charts";
import { useTheme } from "next-themes";
import { useEffect, useRef } from "react";
import type { ForecastOut, IndicatorPoint, PriceBar } from "@/lib/api";

function cssVar(name: string): string {
  return getComputedStyle(document.documentElement.querySelector("body")!)
    .getPropertyValue(name)
    .trim();
}

const ts = (date: string) => (new Date(date + "T00:00:00Z").getTime() / 1000) as UTCTimestamp;

export function CandleChart({
  bars,
  indicators,
  forecast,
  overlays,
}: {
  bars: PriceBar[];
  indicators: IndicatorPoint[];
  forecast: ForecastOut | null;
  overlays: { sma: boolean; ema: boolean };
}) {
  const el = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const { resolvedTheme } = useTheme();

  useEffect(() => {
    if (!el.current || bars.length === 0) return;
    const gain = cssVar("--gain") || "#059669";
    const loss = cssVar("--loss") || "#dc2626";
    const accent = cssVar("--accent") || "#2563eb";
    const ink3 = cssVar("--ink-3") || "#94a3b8";
    const border = cssVar("--border") || "#e2e8f0";

    const chart = createChart(el.current, {
      height: 380,
      autoSize: true,
      layout: {
        background: { type: ColorType.Solid, color: "transparent" },
        textColor: ink3,
        attributionLogo: false,
      },
      grid: {
        vertLines: { color: border, style: LineStyle.Dotted },
        horzLines: { color: border, style: LineStyle.Dotted },
      },
      rightPriceScale: { borderColor: border },
      timeScale: { borderColor: border },
    });
    chartRef.current = chart;

    const candles = chart.addSeries(CandlestickSeries, {
      upColor: gain,
      downColor: loss,
      wickUpColor: gain,
      wickDownColor: loss,
      borderVisible: false,
    });
    candles.setData(
      bars.map((b) => ({ time: ts(b.date), open: b.open, high: b.high, low: b.low, close: b.close })),
    );

    const addIndicatorLine = (key: string, color: string) => {
      const data = indicators
        .filter((p) => p.values[key] !== null && p.values[key] !== undefined)
        .map((p) => ({ time: ts(p.date), value: p.values[key] as number }));
      if (!data.length) return;
      chart
        .addSeries(LineSeries, {
          color,
          lineWidth: 2,
          priceLineVisible: false,
          lastValueVisible: false,
          crosshairMarkerVisible: false,
        })
        .setData(data);
    };
    if (overlays.sma) addIndicatorLine("sma_20", accent);
    if (overlays.ema) addIndicatorLine("ema_20", ink3);

    if (forecast && forecast.points.length && bars.length) {
      const last = bars[bars.length - 1];
      chart
        .addSeries(LineSeries, {
          color: accent,
          lineWidth: 2,
          lineStyle: LineStyle.Dashed,
          priceLineVisible: false,
          lastValueVisible: true,
          title: `${forecast.model_name} forecast`,
        })
        .setData([
          { time: ts(last.date), value: last.close },
          ...forecast.points.map((p) => ({ time: ts(p.target_date), value: p.predicted_close })),
        ]);
    }

    chart.timeScale().fitContent();
    return () => {
      chart.remove();
      chartRef.current = null;
    };
  }, [bars, indicators, forecast, overlays, resolvedTheme]);

  return <div ref={el} className="w-full" />;
}
