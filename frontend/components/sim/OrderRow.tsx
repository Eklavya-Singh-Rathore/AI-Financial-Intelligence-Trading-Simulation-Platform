import { Bot, Check, X } from "lucide-react";
import clsx from "clsx";
import { Badge } from "@/components/ui";
import { fmtNum, type SimOrder } from "@/lib/api";
import { type Tone } from "@/lib/ui";

const STATUS_TONE: Record<string, Tone> = {
  filled: "gain", open: "accent", proposed: "neutral", cancelled: "neutral", rejected: "loss",
};

/** One order row with accept/reject (proposed) or cancel (open) — Phase 6, shared. */
export function OrderRow({ o, onAccept, onReject, onCancel }: {
  o: SimOrder;
  onAccept: (id: string) => void;
  onReject: (id: string) => void;
  onCancel: (id: string) => void;
}) {
  return (
    <tr className="border-t border-line text-sm">
      <td className="py-1.5 pr-2">
        <span className={clsx("font-medium", o.side === "buy" ? "text-gain" : "text-loss")}>{o.side}</span>{" "}
        {o.qty} {o.symbol}
        {o.source === "ai" && (
          <Badge tone="accent" className="ml-1.5"><Bot size={9} />AI</Badge>
        )}
      </td>
      <td className="tabular px-2 text-ink-2">
        {o.order_type}
        {o.limit_price != null && ` @ ${fmtNum(o.limit_price)}`}
        {o.stop_price != null && ` @ ${fmtNum(o.stop_price)}`}
      </td>
      <td className="px-2">
        <Badge tone={STATUS_TONE[o.status] ?? "neutral"}>{o.status}</Badge>
        {o.reason && <span className="ml-1 text-[10px] text-ink-3" title={o.reason}>ⓘ</span>}
      </td>
      <td className="px-2 text-xs text-ink-3">{new Date(o.created_at).toLocaleDateString()}</td>
      <td className="pl-2 text-right">
        {o.status === "proposed" && (
          <span className="inline-flex gap-1">
            <button
              onClick={() => onAccept(o.id)}
              className="rounded bg-gain px-1.5 py-0.5 text-[11px] font-medium text-white"
              title="Accept and execute as market order"
            >
              <Check size={11} className="inline" /> accept
            </button>
            <button
              onClick={() => onReject(o.id)}
              className="rounded border border-line px-1.5 py-0.5 text-[11px] text-ink-2 hover:text-loss"
            >
              <X size={11} className="inline" /> reject
            </button>
          </span>
        )}
        {o.status === "open" && (
          <button
            onClick={() => onCancel(o.id)}
            className="rounded border border-line px-1.5 py-0.5 text-[11px] text-ink-2 hover:text-loss"
          >
            cancel
          </button>
        )}
      </td>
    </tr>
  );
}
