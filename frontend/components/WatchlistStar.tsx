"use client";

// Star toggle (Phase 6): membership in a target watchlist. The target is the
// active dashboard tab's list when one is selected, else the user's first list
// (auto-created as "Watchlist" on first star). Optimistic via query invalidation.
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Star } from "lucide-react";
import { api, type Watchlist } from "@/lib/api";
import { cn } from "@/lib/ui";

export function WatchlistStar({
  symbol,
  watchlists,
  activeListId,
  size = 15,
}: {
  symbol: string;
  watchlists: Watchlist[];
  activeListId?: string | null;
  size?: number;
}) {
  const qc = useQueryClient();
  const target = activeListId
    ? watchlists.find((w) => w.id === activeListId)
    : watchlists[0];
  const starred = target
    ? target.symbols.includes(symbol)
    : watchlists.some((w) => w.symbols.includes(symbol));

  const toggle = useMutation({
    mutationFn: async () => {
      let list = target;
      if (!list) list = await api.createWatchlist("Watchlist");
      if (list.symbols.includes(symbol)) {
        return api.removeWatchlistItem(list.id, symbol);
      }
      return api.addWatchlistItem(list.id, symbol);
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["watchlists"] });
      qc.invalidateQueries({ queryKey: ["summary"] });
    },
  });

  return (
    <button
      type="button"
      aria-label={starred ? `Remove ${symbol} from watchlist` : `Add ${symbol} to watchlist`}
      title={target ? `${starred ? "Remove from" : "Add to"} ${target.name}` : "Add to watchlist"}
      disabled={toggle.isPending}
      onClick={(e) => {
        e.preventDefault();
        e.stopPropagation();
        toggle.mutate();
      }}
      className={cn(
        "rounded p-1 transition-colors disabled:opacity-50",
        starred ? "text-amber-500 hover:text-amber-400" : "text-ink-3 hover:text-ink",
      )}
    >
      <Star size={size} fill={starred ? "currentColor" : "none"} />
    </button>
  );
}
