"use client";

// Watchlist manager (Phase 7): rename, search-and-add, remove, and reorder a
// list in one slide-over. Composes the shared kit; all writes go through the
// existing watchlist API and invalidate the dashboard queries.
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ChevronDown, ChevronUp, Plus, Search, X } from "lucide-react";
import { useEffect, useState } from "react";
import { Button, Input, Sheet, Spinner } from "@/components/ui";
import { api, type Watchlist } from "@/lib/api";

export function WatchlistManager({
  watchlist,
  open,
  onClose,
}: {
  watchlist: Watchlist;
  open: boolean;
  onClose: () => void;
}) {
  const qc = useQueryClient();
  const invalidate = () => {
    qc.invalidateQueries({ queryKey: ["watchlists"] });
    qc.invalidateQueries({ queryKey: ["summary"] });
  };

  // Optimistic member order, re-synced whenever the server order changes.
  const [items, setItems] = useState<string[]>(watchlist.symbols);
  useEffect(() => setItems(watchlist.symbols), [watchlist.symbols]);

  const [name, setName] = useState(watchlist.name);
  useEffect(() => setName(watchlist.name), [watchlist.name]);

  const [query, setQuery] = useState("");
  const [qDebounced, setQDebounced] = useState("");
  useEffect(() => {
    const t = setTimeout(() => setQDebounced(query.trim()), 300);
    return () => clearTimeout(t);
  }, [query]);

  const search = useQuery({
    queryKey: ["wlSearch", qDebounced],
    queryFn: () => api.summary({ q: qDebounced, limit: 8 }),
    enabled: qDebounced.length > 0,
  });
  const results = (search.data?.items ?? []).filter((i) => !items.includes(i.symbol));

  const rename = useMutation({
    mutationFn: (next: string) => api.renameWatchlist(watchlist.id, next),
    onSuccess: invalidate,
  });
  const add = useMutation({
    mutationFn: (symbol: string) => api.addWatchlistItem(watchlist.id, symbol),
    onSuccess: () => {
      setQuery("");
      setQDebounced("");
      invalidate();
    },
  });
  const remove = useMutation({
    mutationFn: (symbol: string) => api.removeWatchlistItem(watchlist.id, symbol),
    onSuccess: invalidate,
  });
  const reorder = useMutation({
    mutationFn: (next: string[]) => api.reorderWatchlist(watchlist.id, next),
    onSuccess: invalidate,
    onError: () => setItems(watchlist.symbols), // revert the optimistic swap
  });

  const move = (index: number, dir: -1 | 1) => {
    const target = index + dir;
    if (target < 0 || target >= items.length) return;
    const next = [...items];
    [next[index], next[target]] = [next[target], next[index]];
    setItems(next); // optimistic
    reorder.mutate(next);
  };

  const saveName = () => {
    const trimmed = name.trim();
    if (!trimmed || trimmed === watchlist.name) {
      setName(watchlist.name);
      return;
    }
    rename.mutate(trimmed);
  };

  return (
    <Sheet open={open} onClose={onClose} side="right" title="Manage watchlist">
      <div className="flex h-full flex-col gap-5 overflow-y-auto p-4">
        {/* Rename */}
        <section>
          <label className="mb-1.5 block text-xs font-medium text-ink-2">Name</label>
          <Input
            value={name}
            onChange={(e) => setName(e.target.value)}
            onBlur={saveName}
            onKeyDown={(e) => e.key === "Enter" && e.currentTarget.blur()}
            maxLength={64}
            aria-label="Watchlist name"
          />
          {rename.error && (
            <p className="mt-1 text-xs text-loss">{String(rename.error)}</p>
          )}
        </section>

        {/* Search + add */}
        <section>
          <label className="mb-1.5 block text-xs font-medium text-ink-2">Add assets</label>
          <div className="relative">
            <Search
              size={15}
              className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-ink-3"
            />
            <Input
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Search instruments to add…"
              className="pl-9"
              aria-label="Search instruments to add"
            />
          </div>
          {qDebounced.length > 0 && (
            <div className="mt-2 overflow-hidden rounded-lg border border-line">
              {search.isLoading ? (
                <div className="flex items-center gap-2 px-3 py-3 text-sm text-ink-3">
                  <Spinner size={14} /> Searching…
                </div>
              ) : results.length === 0 ? (
                <p className="px-3 py-3 text-sm text-ink-3">
                  {search.data ? "No matching instruments to add." : "No matches."}
                </p>
              ) : (
                <ul className="divide-y divide-line">
                  {results.map((r) => (
                    <li key={r.symbol}>
                      <button
                        type="button"
                        onClick={() => add.mutate(r.symbol)}
                        disabled={add.isPending}
                        className="flex w-full items-center gap-2 px-3 py-2 text-left transition-colors hover:bg-surface-2 disabled:opacity-60"
                      >
                        <span className="grid size-6 shrink-0 place-items-center rounded-md bg-accent/10 text-accent">
                          <Plus size={14} />
                        </span>
                        <span className="min-w-0 flex-1">
                          <span className="block truncate text-sm font-medium text-ink">
                            {r.symbol}
                          </span>
                          <span className="block truncate text-xs text-ink-3">
                            {r.display_name}
                          </span>
                        </span>
                      </button>
                    </li>
                  ))}
                </ul>
              )}
            </div>
          )}
          {add.error && <p className="mt-1 text-xs text-loss">{String(add.error)}</p>}
        </section>

        {/* Members + reorder */}
        <section className="min-h-0 flex-1">
          <div className="mb-1.5 flex items-center justify-between">
            <label className="text-xs font-medium text-ink-2">
              Assets ({items.length})
            </label>
            {(reorder.isPending || remove.isPending) && <Spinner size={12} />}
          </div>
          {items.length === 0 ? (
            <p className="rounded-lg border border-dashed border-line px-3 py-6 text-center text-sm text-ink-3">
              No assets yet. Search above to add some.
            </p>
          ) : (
            <ul className="space-y-1.5">
              {items.map((symbol, i) => (
                <li
                  key={symbol}
                  className="flex items-center gap-2 rounded-lg border border-line bg-surface px-2.5 py-2"
                >
                  <div className="flex flex-col">
                    <button
                      type="button"
                      aria-label={`Move ${symbol} up`}
                      onClick={() => move(i, -1)}
                      disabled={i === 0 || reorder.isPending}
                      className="text-ink-3 transition-colors hover:text-ink disabled:opacity-30"
                    >
                      <ChevronUp size={14} />
                    </button>
                    <button
                      type="button"
                      aria-label={`Move ${symbol} down`}
                      onClick={() => move(i, 1)}
                      disabled={i === items.length - 1 || reorder.isPending}
                      className="text-ink-3 transition-colors hover:text-ink disabled:opacity-30"
                    >
                      <ChevronDown size={14} />
                    </button>
                  </div>
                  <span className="flex-1 truncate text-sm font-medium text-ink">{symbol}</span>
                  <button
                    type="button"
                    aria-label={`Remove ${symbol}`}
                    onClick={() => remove.mutate(symbol)}
                    disabled={remove.isPending}
                    className="rounded-md p-1 text-ink-3 transition-colors hover:bg-surface-2 hover:text-loss disabled:opacity-50"
                  >
                    <X size={15} />
                  </button>
                </li>
              ))}
            </ul>
          )}
          {remove.error && <p className="mt-1 text-xs text-loss">{String(remove.error)}</p>}
          {reorder.error && <p className="mt-1 text-xs text-loss">{String(reorder.error)}</p>}
        </section>

        <Button variant="outline" onClick={onClose} className="w-full">
          Done
        </Button>
      </div>
    </Sheet>
  );
}
