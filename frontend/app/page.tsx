"use client";

import { useMutation, useQuery } from "@tanstack/react-query";
import { Plus, RefreshCw, Search, Trash2 } from "lucide-react";
import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import clsx from "clsx";
import { WatchlistStar } from "@/components/WatchlistStar";
import {
  Badge,
  Button,
  EmptyState,
  Input,
  SkeletonRows,
  Tabs,
  Table,
  Tbody,
  Td,
  Th,
  Thead,
  Tr,
} from "@/components/ui";
import { api, fmtNum, fmtPct, polarity, type InstrumentSummary } from "@/lib/api";
import { nextSort, sortRows } from "@/lib/tableSort.mjs";

const PAGE_SIZE = 100;
const TYPE_CHIPS = ["equity", "index", "etf"] as const;

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

type SortState = { key: string; dir: "asc" | "desc" } | null;

export default function Dashboard() {
  const [tab, setTab] = useState("all");
  const [q, setQ] = useState("");
  const [qDebounced, setQDebounced] = useState("");
  const [types, setTypes] = useState<string[]>([]);
  const [page, setPage] = useState(0);
  const [sort, setSort] = useState<SortState>(null);
  const [creating, setCreating] = useState(false);
  const [newName, setNewName] = useState("");

  useEffect(() => {
    const t = setTimeout(() => setQDebounced(q.trim()), 300);
    return () => clearTimeout(t);
  }, [q]);
  useEffect(() => setPage(0), [qDebounced, types, tab]);

  const watchlists = useQuery({ queryKey: ["watchlists"], queryFn: api.watchlists });
  const summary = useQuery({
    queryKey: ["summary", qDebounced, types.join(","), tab, page],
    queryFn: () =>
      api.summary({
        q: qDebounced || undefined,
        types: types.length ? types.join(",") : undefined,
        watchlist_id: tab !== "all" ? tab : undefined,
        limit: PAGE_SIZE,
        offset: page * PAGE_SIZE,
      }),
    placeholderData: (prev) => prev,
  });
  const ingest = useMutation({
    mutationFn: api.ingest,
    onSuccess: () => setTimeout(() => summary.refetch(), 20_000),
  });
  const createList = useMutation({
    mutationFn: (name: string) => api.createWatchlist(name),
    onSuccess: (wl) => {
      watchlists.refetch();
      setCreating(false);
      setNewName("");
      setTab(wl.id);
    },
  });
  const deleteList = useMutation({
    mutationFn: (id: string) => api.deleteWatchlist(id),
    onSuccess: () => {
      watchlists.refetch();
      setTab("all");
    },
  });

  const items = useMemo(
    () => sortRows(summary.data?.items ?? [], sort) as InstrumentSummary[],
    [summary.data, sort],
  );
  const total = summary.data?.total ?? 0;
  const pages = Math.max(1, Math.ceil(total / PAGE_SIZE));

  const breadth = useMemo(() => {
    const rows = summary.data?.items ?? [];
    let up = 0, down = 0, flat = 0;
    for (const r of rows) {
      if (r.change_1d_pct === null || r.change_1d_pct === undefined) flat++;
      else if (r.change_1d_pct > 0) up++;
      else if (r.change_1d_pct < 0) down++;
      else flat++;
    }
    return { up, down, flat };
  }, [summary.data]);

  const tabItems = [
    { value: "all", label: "All", count: tab === "all" ? total : undefined },
    ...(watchlists.data ?? []).map((w) => ({
      value: w.id,
      label: w.name,
      count: w.symbols.length,
    })),
  ];
  const activeList = tab !== "all" ? (watchlists.data ?? []).find((w) => w.id === tab) : null;

  const sortableTh = (key: string, label: string, numeric = false) => (
    <Th
      numeric={numeric}
      sortable
      sortDir={sort?.key === key ? sort.dir : null}
      onSort={() => setSort(nextSort(sort, key))}
    >
      {label}
    </Th>
  );

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-xl font-semibold">Market overview</h1>
          <p className="text-sm text-ink-2">
            Indian-market universe · daily bars
            {summary.data && (
              <span className="tabular ml-2 text-xs text-ink-3">
                <span className="text-gain">▲ {breadth.up}</span>
                {" · "}
                <span className="text-loss">▼ {breadth.down}</span>
                {" · "}
                <span>– {breadth.flat}</span>
              </span>
            )}
          </p>
        </div>
        <Button variant="outline" size="sm" onClick={() => ingest.mutate()} disabled={ingest.isPending}>
          <RefreshCw size={14} className={ingest.isPending ? "animate-spin motion-reduce:animate-none" : ""} />
          {ingest.isPending ? "Refreshing…" : ingest.isSuccess ? "Refresh queued" : "Refresh data"}
        </Button>
      </div>

      <div className="flex flex-wrap items-center gap-2">
        <Tabs items={tabItems} value={tab} onValueChange={setTab} className="min-w-0 flex-1 border-b-0" />
        {creating ? (
          <form
            className="flex items-center gap-1.5"
            onSubmit={(e) => {
              e.preventDefault();
              if (newName.trim()) createList.mutate(newName.trim());
            }}
          >
            <Input
              autoFocus
              value={newName}
              onChange={(e) => setNewName(e.target.value)}
              placeholder="List name"
              className="h-8 w-36 text-xs"
            />
            <Button size="sm" type="submit" disabled={createList.isPending || !newName.trim()}>
              Add
            </Button>
            <Button size="sm" variant="ghost" onClick={() => setCreating(false)}>
              Cancel
            </Button>
          </form>
        ) : (
          <Button size="sm" variant="ghost" onClick={() => setCreating(true)}>
            <Plus size={14} /> New list
          </Button>
        )}
        {activeList && (
          <Button
            size="sm"
            variant="ghost"
            className="text-ink-3 hover:text-loss"
            title={`Delete "${activeList.name}"`}
            onClick={() => deleteList.mutate(activeList.id)}
            disabled={deleteList.isPending}
          >
            <Trash2 size={14} />
          </Button>
        )}
      </div>
      {createList.error && <p className="text-xs text-loss">{createList.error.message}</p>}

      <div className="flex flex-wrap items-center gap-2">
        <div className="relative w-64 max-w-full">
          <Search size={14} className="pointer-events-none absolute left-2.5 top-1/2 -translate-y-1/2 text-ink-3" />
          <Input
            value={q}
            onChange={(e) => setQ(e.target.value)}
            placeholder="Search symbol or name…"
            className="pl-8"
          />
        </div>
        {TYPE_CHIPS.map((t) => {
          const active = types.includes(t);
          return (
            <button
              key={t}
              type="button"
              onClick={() =>
                setTypes(active ? types.filter((x) => x !== t) : [...types, t])
              }
              className={clsx(
                "rounded-full border px-2.5 py-1 text-xs font-medium transition-colors",
                active
                  ? "border-accent/30 bg-accent/10 text-accent"
                  : "border-line text-ink-2 hover:text-ink",
              )}
            >
              {t}
            </button>
          );
        })}
        {total > 0 && (
          <span className="tabular ml-auto text-xs text-ink-3">
            {total} instrument{total === 1 ? "" : "s"}
          </span>
        )}
      </div>

      {summary.error && (
        <div className="rounded-md border border-loss/40 bg-loss/5 p-3 text-sm text-loss">
          {String(summary.error)}
        </div>
      )}
      {summary.isLoading && <SkeletonRows rows={8} />}

      {summary.data && items.length === 0 && (
        <EmptyState
          title={tab !== "all" ? "This watchlist is empty" : "No instruments match"}
          description={
            tab !== "all"
              ? "Star instruments from the All tab (or an instrument page) to add them here."
              : "Try a different search or clear the type filters."
          }
        />
      )}

      {summary.data && items.length > 0 && (
        <div className="rounded-lg border border-line">
          <Table minWidth="760px">
            <Thead>
              <tr>
                <Th className="w-8 pl-2" />
                {sortableTh("symbol", "Instrument")}
                <Th>Type</Th>
                {sortableTh("last_close", "Last close", true)}
                {sortableTh("change_1d_pct", "1D", true)}
                {sortableTh("change_5d_pct", "5D", true)}
                {sortableTh("change_20d_pct", "20D", true)}
                <Th>30-day trend</Th>
                <Th numeric>As of</Th>
              </tr>
            </Thead>
            <Tbody>
              {items.map((r) => (
                <Tr key={r.symbol}>
                  <Td className="w-8 pl-2">
                    <WatchlistStar
                      symbol={r.symbol}
                      watchlists={watchlists.data ?? []}
                      activeListId={tab !== "all" ? tab : null}
                    />
                  </Td>
                  <Td>
                    <Link href={`/instruments/${encodeURIComponent(r.symbol)}`} className="group block">
                      <div className="font-medium text-ink group-hover:text-accent">{r.symbol}</div>
                      <div className="text-xs text-ink-3">{r.display_name}</div>
                    </Link>
                  </Td>
                  <Td>
                    <Badge>{r.instrument_type}</Badge>
                  </Td>
                  <Td numeric className="font-medium">{fmtNum(r.last_close)}</Td>
                  {[r.change_1d_pct, r.change_5d_pct, r.change_20d_pct].map((v, i) => (
                    <Td key={i} numeric className={polarity(v)}>{fmtPct(v)}</Td>
                  ))}
                  <Td><Sparkline points={r.sparkline} /></Td>
                  <Td numeric className="text-xs text-ink-3">{r.last_date ?? "–"}</Td>
                </Tr>
              ))}
            </Tbody>
          </Table>
        </div>
      )}

      {pages > 1 && (
        <div className="flex items-center justify-end gap-2 text-xs text-ink-2">
          <Button size="sm" variant="ghost" disabled={page === 0} onClick={() => setPage(page - 1)}>
            Prev
          </Button>
          <span className="tabular">
            {page + 1} / {pages}
          </span>
          <Button
            size="sm"
            variant="ghost"
            disabled={page + 1 >= pages}
            onClick={() => setPage(page + 1)}
          >
            Next
          </Button>
        </div>
      )}
    </div>
  );
}
