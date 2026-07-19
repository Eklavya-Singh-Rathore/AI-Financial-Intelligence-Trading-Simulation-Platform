import { type ChatMessage } from "@/lib/api";

/** Grounding-context chips + news citations under an assistant message.
 *  Shared by the full chat page and the floating assistant (Phase 6). */
export function ContextChips({ ctx }: { ctx: ChatMessage["context"] }) {
  if (!ctx) return null;
  const chips = [
    ...(ctx.symbols ?? []).map((s) => `data: ${s}`),
    ctx.decisions_used ? `${ctx.decisions_used} decisions` : null,
    ctx.memory_notes_used ? `${ctx.memory_notes_used} memory notes` : null,
    ctx.news_used ? `${ctx.news_used} news` : null,
  ].filter(Boolean) as string[];
  const citations = ctx.citations ?? [];
  if (!chips.length && !citations.length) return null;
  return (
    <div className="mt-2 space-y-1.5">
      {chips.length > 0 && (
        <div className="flex flex-wrap gap-1.5">
          {chips.map((c) => (
            <span key={c} className="rounded-full bg-accent/10 px-2 py-0.5 text-[11px] text-accent">{c}</span>
          ))}
        </div>
      )}
      {citations.length > 0 && (
        <ul className="space-y-0.5 text-[11px] text-ink-3">
          {citations.map((c) => (
            <li key={c.n} className="truncate">
              [{c.n}]{" "}
              {c.url ? (
                <a href={c.url} target="_blank" rel="noreferrer" className="hover:text-accent hover:underline">
                  {c.title}
                </a>
              ) : (
                c.title
              )}
              {c.published_at ? ` · ${c.published_at.slice(0, 10)}` : ""}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
