"use client";

// Command palette (Phase 6): Cmd/Ctrl-K to search the tracked universe locally,
// then "Add from market" to track any Indian symbol (background backfill).
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { CornerDownLeft, Download, Loader2, Search, TrendingUp } from "lucide-react";
import { useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { api, type MarketSearchResult } from "@/lib/api";
import { filterInstruments } from "@/lib/search.mjs";
import { cn } from "@/lib/ui";

function TrackRow({ r, onDone }: { r: MarketSearchResult; onDone: (symbol: string) => void }) {
  const [tracked, setTracked] = useState<string | null>(null);
  const track = useMutation({
    mutationFn: () => api.marketTrack(r.provider_symbol),
    onSuccess: (res) => setTracked(res.symbol),
  });
  const status = useQuery({
    queryKey: ["trackStatus", tracked],
    queryFn: () => api.trackStatus(tracked!),
    enabled: !!tracked,
    refetchInterval: (q) =>
      q.state.data && ["done", "error", "none"].includes(q.state.data.status) ? false : 2000,
  });
  useEffect(() => {
    if (status.data?.status === "done") onDone(status.data.symbol);
  }, [status.data, onDone]);

  const st = status.data?.status;
  return (
    <div className="flex items-center justify-between gap-2 px-3 py-2">
      <div className="min-w-0">
        <div className="truncate text-sm text-ink">
          {r.provider_symbol}
          {r.exchange && <span className="ml-1.5 text-xs text-ink-3">{r.exchange}</span>}
        </div>
        <div className="truncate text-xs text-ink-3">{r.name}</div>
      </div>
      {r.already_tracked ? (
        <span className="text-xs text-ink-3">tracked</span>
      ) : !tracked ? (
        <button
          type="button"
          onClick={() => track.mutate()}
          disabled={track.isPending}
          className="inline-flex shrink-0 items-center gap-1 rounded-md bg-accent px-2 py-1 text-xs font-medium text-on-accent hover:brightness-110 disabled:opacity-50"
        >
          <Download size={12} /> Track
        </button>
      ) : st === "done" ? (
        <span className="text-xs text-gain">ready ✓</span>
      ) : st === "error" ? (
        <span className="text-xs text-loss">failed</span>
      ) : (
        <span className="inline-flex items-center gap-1 text-xs text-ink-3">
          <Loader2 size={12} className="animate-spin" /> backfilling…
        </span>
      )}
    </div>
  );
}

const OPEN_EVENT = "finintel:open-search";

/** Trigger button (may appear in several places); opens the single palette. */
export function SearchTrigger({ className }: { className?: string }) {
  return (
    <button
      type="button"
      onClick={() => window.dispatchEvent(new Event(OPEN_EVENT))}
      className={cn(
        "inline-flex items-center gap-2 rounded-md border border-line px-2.5 py-1.5 text-xs text-ink-3 transition-colors hover:text-ink",
        className,
      )}
    >
      <Search size={13} className="shrink-0" /> Search instruments, indices, assets...
      <kbd className="tabular ml-auto rounded border border-line px-1 text-[10px]">⌘K</kbd>
    </button>
  );
}

export function SearchCommand() {
  const [open, setOpen] = useState(false);
  const [q, setQ] = useState("");
  const [qDebounced, setQDebounced] = useState("");
  const [mounted, setMounted] = useState(false);
  const router = useRouter();
  const qc = useQueryClient();
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => setMounted(true), []);

  // Global Cmd/Ctrl-K toggle + custom open event from triggers.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        setOpen((o) => !o);
      } else if (e.key === "Escape") {
        setOpen(false);
      }
    };
    const onOpen = () => setOpen(true);
    window.addEventListener("keydown", onKey);
    window.addEventListener(OPEN_EVENT, onOpen);
    return () => {
      window.removeEventListener("keydown", onKey);
      window.removeEventListener(OPEN_EVENT, onOpen);
    };
  }, []);

  useEffect(() => {
    if (open) setTimeout(() => inputRef.current?.focus(), 10);
    else {
      setQ("");
      setQDebounced("");
    }
  }, [open]);

  useEffect(() => {
    const t = setTimeout(() => setQDebounced(q.trim()), 300);
    return () => clearTimeout(t);
  }, [q]);

  const universe = useQuery({
    queryKey: ["summary-all"],
    queryFn: () => api.summary({ limit: 500 }),
    enabled: open,
    staleTime: 60_000,
  });
  const market = useQuery({
    queryKey: ["marketSearch", qDebounced],
    queryFn: () => api.marketSearch(qDebounced),
    enabled: open && qDebounced.length >= 2,
    staleTime: 30_000,
  });

  const local = filterInstruments(universe.data?.items ?? [], q, 8) as {
    symbol: string;
    display_name: string;
  }[];
  const localSymbols = new Set(local.map((i) => i.symbol.toUpperCase()));
  const marketResults = (market.data?.results ?? []).filter(
    (r) => !localSymbols.has(r.provider_symbol.replace(/\.(NS|BO)$/i, "").toUpperCase()),
  );

  const go = (symbol: string) => {
    setOpen(false);
    router.push(`/instruments/${encodeURIComponent(symbol)}`);
  };
  const onTracked = (symbol: string) => {
    qc.invalidateQueries({ queryKey: ["summary"] });
    qc.invalidateQueries({ queryKey: ["summary-all"] });
  };

  if (!mounted || !open) return null;

  return (
    <>
      {createPortal(
          <div className="fixed inset-0 z-50 flex items-start justify-center p-4 pt-[12vh]">
            <div className="absolute inset-0 bg-black/40 motion-safe:animate-fade-in" onClick={() => setOpen(false)} />
            <div className="relative w-full max-w-lg overflow-hidden rounded-lg border border-line bg-surface shadow-md">
              <div className="flex items-center gap-2 border-b border-line px-3">
                <Search size={16} className="text-ink-3" />
                <input
                  ref={inputRef}
                  value={q}
                  onChange={(e) => setQ(e.target.value)}
                  placeholder="Search instruments, or type any NSE symbol…"
                  className="h-11 w-full bg-transparent text-sm text-ink outline-none placeholder:text-ink-3"
                />
              </div>
              <div className="max-h-[50vh] overflow-y-auto py-1">
                {local.length > 0 && (
                  <div>
                    <div className="px-3 py-1 text-[10px] uppercase tracking-wide text-ink-3">Your universe</div>
                    {local.map((i) => (
                      <button
                        key={i.symbol}
                        onClick={() => go(i.symbol)}
                        className="flex w-full items-center justify-between gap-2 px-3 py-2 text-left hover:bg-surface-2"
                      >
                        <span className="min-w-0">
                          <span className="text-sm font-medium text-ink">{i.symbol}</span>
                          <span className="ml-2 truncate text-xs text-ink-3">{i.display_name}</span>
                        </span>
                        <CornerDownLeft size={12} className="shrink-0 text-ink-3" />
                      </button>
                    ))}
                  </div>
                )}
                {qDebounced.length >= 2 && (
                  <div>
                    <div className="flex items-center gap-1.5 px-3 py-1 text-[10px] uppercase tracking-wide text-ink-3">
                      <TrendingUp size={11} /> Add from market
                      {market.isFetching && <Loader2 size={10} className="animate-spin" />}
                    </div>
                    {marketResults.length === 0 && !market.isFetching && (
                      <div className="px-3 py-2 text-xs text-ink-3">No new symbols found.</div>
                    )}
                    {marketResults.map((r) => (
                      <TrackRow key={r.provider_symbol} r={r} onDone={onTracked} />
                    ))}
                  </div>
                )}
                {q.trim().length > 0 && local.length === 0 && qDebounced.length < 2 && (
                  <div className="px-3 py-3 text-xs text-ink-3">Keep typing to search the market…</div>
                )}
                {q.trim().length === 0 && (
                  <div className="px-3 py-3 text-xs text-ink-3">
                    Type to search your tracked universe, or any Indian symbol to add it.
                  </div>
                )}
              </div>
            </div>
          </div>,
          document.body,
        )}
    </>
  );
}
