"use client";

// Equity (area) + drawdown (line) charts for the paper portfolio.
// Same lightweight-charts v5 + CSS-variable theming pattern as CandleChart.
import {
  AreaSeries,
  ColorType,
  LineSeries,
  LineStyle,
  createChart,
  type UTCTimestamp,
} from "lightweight-charts";
import { useTheme } from "next-themes";
import { useEffect, useRef } from "react";
import type { SimPerformance } from "@/lib/api";

function cssVar(name: string): string {
  return getComputedStyle(document.documentElement.querySelector("body")!)
    .getPropertyValue(name)
    .trim();
}

const ts = (date: string) => (new Date(date + "T00:00:00Z").getTime() / 1000) as UTCTimestamp;

export function EquityChart({ series }: { series: SimPerformance["series"] }) {
  const equityEl = useRef<HTMLDivElement>(null);
  const ddEl = useRef<HTMLDivElement>(null);
  const { resolvedTheme } = useTheme();

  useEffect(() => {
    if (!equityEl.current || !ddEl.current || series.length === 0) return;
    const accent = cssVar("--accent") || "#2563eb";
    const loss = cssVar("--loss") || "#dc2626";
    const ink3 = cssVar("--ink-3") || "#94a3b8";
    const border = cssVar("--border") || "#e2e8f0";

    const opts = {
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
    } as const;

    const equityChart = createChart(equityEl.current, { ...opts, height: 220 });
    equityChart
      .addSeries(AreaSeries, {
        lineColor: accent,
        topColor: `${accent}44`,
        bottomColor: `${accent}05`,
        lineWidth: 2,
        priceLineVisible: false,
      })
      .setData(series.map((p) => ({ time: ts(p.date), value: p.equity })));
    equityChart.timeScale().fitContent();

    const ddChart = createChart(ddEl.current, { ...opts, height: 110 });
    ddChart
      .addSeries(LineSeries, {
        color: loss,
        lineWidth: 2,
        priceLineVisible: false,
        lastValueVisible: true,
      })
      .setData(series.map((p) => ({ time: ts(p.date), value: p.drawdown_pct })));
    ddChart.timeScale().fitContent();

    return () => {
      equityChart.remove();
      ddChart.remove();
    };
  }, [series, resolvedTheme]);

  if (series.length === 0) {
    return <div className="py-10 text-center text-sm text-ink-3">No history yet.</div>;
  }
  return (
    <div>
      <div className="mb-1 text-xs text-ink-3">Equity</div>
      <div ref={equityEl} className="w-full" />
      <div className="mb-1 mt-3 text-xs text-ink-3">Drawdown %</div>
      <div ref={ddEl} className="w-full" />
    </div>
  );
}
