"use client";

import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { DecisionBadge, StatusChip } from "@/components/RunBits";
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
      {isLoading && <p className="text-sm text-ink-2">Loading…</p>}
      {data && data.length === 0 && <p className="text-sm text-ink-3">No runs yet.</p>}
      <div className="space-y-2">
        {data?.map((run) => (
          <Link
            key={run.id}
            href={`/agents/${run.id}`}
            className="flex items-center justify-between rounded-lg border border-line p-3 hover:bg-surface-2"
          >
            <div className="flex items-center gap-3">
              <StatusChip status={run.status} />
              <span className="font-medium">{run.symbol}</span>
              <span className="text-xs text-ink-3">
                {new Date(run.created_at).toLocaleString()}
              </span>
            </div>
            <div className="flex items-center gap-4">
              {run.token_usage?.calls != null && (
                <span className="tabular text-xs text-ink-3">
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
