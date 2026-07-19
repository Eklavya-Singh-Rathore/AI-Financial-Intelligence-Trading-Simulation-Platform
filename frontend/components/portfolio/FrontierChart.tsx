"use client";

// Efficient-frontier scatter (Phase 6): risk (x) vs return (y), inline SVG.
import type { OptimizationAnalytics } from "@/lib/api";

type Available = Extract<OptimizationAnalytics, { available: true }>;

export function FrontierChart({ data, height = 240 }: { data: Available; height?: number }) {
  const w = 400, h = height, pad = 34;
  const xs = data.frontier.map((p) => p.risk);
  const ys = data.frontier.map((p) => p.return);
  if (xs.length === 0) return null;
  const xMin = Math.min(...xs), xMax = Math.max(...xs);
  const yMin = Math.min(...ys, 0), yMax = Math.max(...ys);
  const sx = (v: number) => pad + ((v - xMin) / (xMax - xMin || 1)) * (w - pad * 2);
  const sy = (v: number) => h - pad - ((v - yMin) / (yMax - yMin || 1)) * (h - pad * 2);

  const marker = (
    risk: number,
    ret: number,
    color: string,
    label: string,
  ) => (
    <g key={label}>
      <circle cx={sx(risk)} cy={sy(ret)} r={5} fill={color} stroke="var(--surface)" strokeWidth={1.5} />
      <text x={sx(risk) + 7} y={sy(ret) + 3} className="fill-ink-2 text-[9px]">{label}</text>
    </g>
  );

  return (
    <div className="overflow-x-auto">
      <svg viewBox={`0 0 ${w} ${h}`} className="w-full" style={{ minWidth: 320 }}>
        {/* axes */}
        <line x1={pad} y1={h - pad} x2={w - pad} y2={h - pad} className="stroke-line" />
        <line x1={pad} y1={pad} x2={pad} y2={h - pad} className="stroke-line" />
        <text x={w / 2} y={h - 6} textAnchor="middle" className="fill-ink-3 text-[9px]">Risk (annual vol %)</text>
        <text x={10} y={h / 2} transform={`rotate(-90 10 ${h / 2})`} textAnchor="middle" className="fill-ink-3 text-[9px]">Return %</text>
        {/* frontier cloud */}
        {data.frontier.map((p, i) => (
          <circle key={i} cx={sx(p.risk)} cy={sy(p.return)} r={1.6} className="fill-accent" opacity={0.28} />
        ))}
        {/* highlights */}
        {marker(data.max_sharpe.risk_pct, data.max_sharpe.return_pct, "var(--gain)", "max Sharpe")}
        {marker(data.min_vol.risk_pct, data.min_vol.return_pct, "var(--accent)", "min vol")}
      </svg>
    </div>
  );
}
