"use client";

// Monte Carlo projection fan (Phase 6): p5/p25/p50/p75/p95 percentile lines.
import {
  ColorType,
  LineSeries,
  LineStyle,
  createChart,
  type UTCTimestamp,
} from "lightweight-charts";
import { useTheme } from "next-themes";
import { useEffect, useRef } from "react";
import type { MonteCarloAnalytics } from "@/lib/api";
import { chartColors, withAlpha } from "@/lib/chart";

type Available = Extract<MonteCarloAnalytics, { available: true }>;

export function MonteCarloChart({ data, height = 280 }: { data: Available; height?: number }) {
  const el = useRef<HTMLDivElement>(null);
  const { resolvedTheme } = useTheme();

  useEffect(() => {
    if (!el.current || data.bands.length === 0) return;
    const c = chartColors();
    const chart = createChart(el.current, {
      height,
      autoSize: true,
      layout: {
        background: { type: ColorType.Solid, color: "transparent" },
        textColor: c.ink3,
        attributionLogo: false,
        fontFamily: "var(--font-sans)",
      },
      grid: { vertLines: { visible: false }, horzLines: { color: c.border, style: LineStyle.Dotted } },
      rightPriceScale: { borderColor: c.border },
      timeScale: { borderColor: c.border },
    });
    const t0 = Math.floor(Date.now() / 1000);
    const time = (day: number) => (t0 + day * 86400) as UTCTimestamp;
    const line = (key: keyof Available["bands"][number], color: string, width: 1 | 2, dashed = false) => {
      const s = chart.addSeries(LineSeries, {
        color,
        lineWidth: width,
        lineStyle: dashed ? LineStyle.Dashed : LineStyle.Solid,
        priceLineVisible: false,
        lastValueVisible: key === "p50",
        crosshairMarkerVisible: false,
      });
      s.setData(data.bands.map((b) => ({ time: time(b.day), value: b[key] as number })));
    };
    line("p95", withAlpha(c.ink3, 140), 1, true);
    line("p75", withAlpha(c.accent, 140), 1);
    line("p50", c.accent, 2);
    line("p25", withAlpha(c.accent, 140), 1);
    line("p5", withAlpha(c.ink3, 140), 1, true);
    chart.timeScale().fitContent();
    return () => chart.remove();
  }, [data, height, resolvedTheme]);

  return <div ref={el} className="w-full" style={{ height }} />;
}
