import { cn } from "@/lib/ui";

type Props = {
  points: number[];
  width?: number;
  height?: number;
  /** Fill the area under the line with a soft tint. */
  area?: boolean;
  className?: string;
};

/** Tiny trend line, auto-colored gain/loss by first→last direction. */
export function Sparkline({ points, width = 96, height = 28, area = false, className }: Props) {
  if (points.length < 2) return <span className="text-ink-3">–</span>;
  const pad = 2;
  const min = Math.min(...points);
  const max = Math.max(...points);
  const span = max - min || 1;
  const step = (width - pad * 2) / (points.length - 1);
  const y = (v: number) => height - pad - ((v - min) / span) * (height - pad * 2);
  const line = points
    .map((v, i) => `${i === 0 ? "M" : "L"}${(pad + i * step).toFixed(1)},${y(v).toFixed(1)}`)
    .join(" ");
  const up = points[points.length - 1] >= points[0];
  const lastX = (pad + (points.length - 1) * step).toFixed(1);
  const areaPath = `${line} L${lastX},${height - pad} L${pad},${height - pad} Z`;
  return (
    <svg
      width={width}
      height={height}
      viewBox={`0 0 ${width} ${height}`}
      preserveAspectRatio="none"
      aria-hidden
      className={cn("block", className)}
    >
      {area && <path d={areaPath} stroke="none" className={up ? "fill-gain/10" : "fill-loss/10"} />}
      <path
        d={line}
        fill="none"
        strokeWidth={2}
        strokeLinejoin="round"
        strokeLinecap="round"
        className={up ? "stroke-gain" : "stroke-loss"}
      />
    </svg>
  );
}
