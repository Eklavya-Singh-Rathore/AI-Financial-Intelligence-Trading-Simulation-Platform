"use client";

import { useMutation, useQuery } from "@tanstack/react-query";
import { RefreshCw } from "lucide-react";
import Link from "next/link";
import clsx from "clsx";
import { Button } from "@/components/ui";
import { api, fmtNum, fmtPct, polarity, type InstrumentSummary } from "@/lib/api";

function Sparkline({ points }: { points: number[] }) {
  if (points.length < 2) return <span className="text-ink-3">–</span>;
  const w = 96, h = 28, pad = 2;
  const min = Math.min(...points), max = Math.max(...points);
  const span = max - min || 1;
  const step = (w - pad * 2) / (points.length - 1);
  const d = points
    .map((v, i) => `${i === 0 ? "M" : "L"}${(pad + i * step).toFixed(1)},${(h - pad - ((v - min) / span) * (h - pad * 2)).toFixed(1)}`)
    .join(" ");
  const up = points[points.length - 1] >= points[0];
  return (
    <svg width={w} height={h} aria-hidden className="block">
      <path d={d} fill="none" strokeWidth={2} className={up ? "stroke-gain" : "stroke-loss"} />
    </svg>
  );
}

function Row({ r }: { r: InstrumentSummary }) {
  return (
    <tr className="border-b border-line hover:bg-surface-2">
      <td className="py-2.5 pr-4">
        <Link href={`/instruments/${encodeURIComponent(r.symbol)}`} className="group">
          <div className="font-medium group-hover:text-accent">{r.symbol}</div>
          <div className="text-xs text-ink-3">{r.display_name}</div>
        </Link>
      </td>
      <td className="pr-4 text-xs uppercase text-ink-3">{r.instrument_type}</td>
      <td className="tabular pr-4 text-right font-medium">{fmtNum(r.last_close)}</td>
      {[r.change_1d_pct, r.change_5d_pct, r.change_20d_pct].map((v, i) => (
        <td key={i} className={clsx("tabular pr-4 text-right", polarity(v))}>{fmtPct(v)}</td>
      ))}
      <td className="pr-4"><Sparkline points={r.sparkline} /></td>
      <td className="text-right text-xs text-ink-3">{r.last_date ?? "–"}</td>
    </tr>
  );
}

export default function Dashboard() {
  const { data, isLoading, error, refetch } = useQuery({
    queryKey: ["summary"],
    queryFn: api.summary,
  });
  const ingest = useMutation({
    mutationFn: api.ingest,
    onSuccess: () => setTimeout(() => refetch(), 20_000),
  });

  return (
    <div>
      <div className="mb-5 flex items-center justify-between">
        <div>
          <h1 className="text-xl font-semibold">Market overview</h1>
          <p className="text-sm text-ink-2">16-asset Indian-market universe · daily bars</p>
        </div>
        <Button variant="outline" size="sm" onClick={() => ingest.mutate()} disabled={ingest.isPending}>
          <RefreshCw size={14} className={ingest.isPending ? "animate-spin motion-reduce:animate-none" : ""} />
          {ingest.isPending ? "Refreshing…" : ingest.isSuccess ? "Refresh queued" : "Refresh data"}
        </Button>
      </div>

      {error && (
        <div className="rounded-md border border-loss/40 bg-loss/5 p-3 text-sm text-loss">
          {String(error)}
        </div>
      )}
      {isLoading && <div className="text-sm text-ink-2">Loading universe…</div>}

      {data && (
        <div className="overflow-x-auto rounded-lg border border-line">
          <table className="w-full min-w-[760px] text-sm">
            <thead>
              <tr className="border-b border-line text-left text-xs uppercase tracking-wide text-ink-3">
                <th className="py-2.5 pl-3 pr-4 font-medium">Instrument</th>
                <th className="pr-4 font-medium">Type</th>
                <th className="pr-4 text-right font-medium">Last close</th>
                <th className="pr-4 text-right font-medium">1D</th>
                <th className="pr-4 text-right font-medium">5D</th>
                <th className="pr-4 text-right font-medium">20D</th>
                <th className="pr-4 font-medium">30-day trend</th>
                <th className="pr-3 text-right font-medium">As of</th>
              </tr>
            </thead>
            <tbody className="[&>tr>td:first-child]:pl-3">
              {data.map((r) => <Row key={r.symbol} r={r} />)}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
