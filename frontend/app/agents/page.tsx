"use client";

import { useQuery } from "@tanstack/react-query";
import { Bot } from "lucide-react";
import Link from "next/link";
import { DecisionBadge, StatusChip } from "@/components/RunBits";
import { EmptyState, SkeletonRows } from "@/components/ui";
import { api } from "@/lib/api";

export default function AgentsPage() {
  const { data, isLoading, error } = useQuery({
    queryKey: ["runs"],
    queryFn: api.runs,
    refetchInterval: (q) =>
      q.state.data?.some((r) => r.status === "pending" || r.status === "running") ? 3000 : false,
  });

  return (
    <div>
      <h1 className="mb-1 text-xl font-semibold">Agent runs</h1>
      <p className="mb-5 text-sm text-ink-2">
        Multi-agent pipeline: analysts → bull/bear debate → trader → risk → portfolio manager.
        Start one from an instrument page.
      </p>
      {error && <p className="text-sm text-loss">{String(error)}</p>}
      {isLoading && <SkeletonRows rows={4} />}
      {data && data.length === 0 && (
        <EmptyState
          icon={Bot}
          title="No agent runs yet"
          description="Open any instrument and start a run — the multi-agent pipeline's decisions will appear here."
        />
      )}
      <div className="space-y-2">
        {data?.map((run) => (
          <Link
            key={run.id}
            href={`/agents/${run.id}`}
            className="flex items-center justify-between rounded-lg border border-line bg-surface p-3 shadow-xs transition-colors hover:bg-surface-2"
          >
            <div className="flex min-w-0 items-center gap-3">
              <StatusChip status={run.status} />
              <span className="font-medium">{run.symbol}</span>
              <span className="truncate text-xs text-ink-3">
                {new Date(run.created_at).toLocaleString()}
              </span>
            </div>
            <div className="flex shrink-0 items-center gap-4">
              {run.token_usage?.calls != null && (
                <span className="tabular hidden text-xs text-ink-3 sm:inline">
                  {run.token_usage.calls} calls · {(run.token_usage.input_tokens ?? 0) + (run.token_usage.output_tokens ?? 0)} tok
                </span>
              )}
              <DecisionBadge run={run} />
            </div>
          </Link>
        ))}
      </div>
    </div>
  );
}
