"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Plus, Send, Trash2 } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import ReactMarkdown from "react-markdown";
import clsx from "clsx";
import { api, type ChatMessage } from "@/lib/api";

function ContextChips({ ctx }: { ctx: ChatMessage["context"] }) {
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

export default function ChatPage() {
  const qc = useQueryClient();
  const [active, setActive] = useState<string | null>(null);
  const [draft, setDraft] = useState("");
  const bottom = useRef<HTMLDivElement>(null);

  const sessions = useQuery({ queryKey: ["chatSessions"], queryFn: api.chatSessions });
  const messages = useQuery({
    queryKey: ["chatMessages", active],
    queryFn: () => api.chatMessages(active!),
    enabled: !!active,
  });

  const createSession = useMutation({
    mutationFn: api.createChat,
    onSuccess: (s) => {
      qc.invalidateQueries({ queryKey: ["chatSessions"] });
      setActive(s.id);
    },
  });
  const deleteSession = useMutation({
    mutationFn: api.deleteChat,
    onSuccess: (_d, id) => {
      qc.invalidateQueries({ queryKey: ["chatSessions"] });
      if (active === id) setActive(null);
    },
  });
  const send = useMutation({
    mutationFn: ({ id, content }: { id: string; content: string }) => api.sendChat(id, content),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["chatMessages", active] });
      qc.invalidateQueries({ queryKey: ["chatSessions"] });
    },
  });

  useEffect(() => {
    bottom.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages.data, send.isPending]);

  const submit = () => {
    const content = draft.trim();
    if (!content || !active || send.isPending) return;
    setDraft("");
    send.mutate({ id: active, content });
  };

  return (
    <div className="flex h-[calc(100vh-3rem)] gap-4">
      <aside className="flex w-60 shrink-0 flex-col rounded-lg border border-line">
        <button
          onClick={() => createSession.mutate()}
          className="m-2 flex items-center justify-center gap-1.5 rounded-md border border-line px-2 py-1.5 text-sm text-ink-2 hover:text-ink"
        >
          <Plus size={14} /> New chat
        </button>
        <div className="min-h-0 flex-1 overflow-y-auto px-2 pb-2">
          {sessions.data?.map((s) => (
            <div
              key={s.id}
              className={clsx(
                "group mb-1 flex cursor-pointer items-center justify-between rounded-md px-2 py-1.5 text-sm",
                active === s.id ? "bg-accent/10 text-accent" : "text-ink-2 hover:bg-surface-2",
              )}
              onClick={() => setActive(s.id)}
            >
              <span className="truncate">{s.title}</span>
              <button
                aria-label="Delete chat"
                onClick={(e) => { e.stopPropagation(); deleteSession.mutate(s.id); }}
                className="hidden text-ink-3 hover:text-loss group-hover:block"
              >
                <Trash2 size={13} />
              </button>
            </div>
          ))}
        </div>
      </aside>

      <section className="flex min-w-0 flex-1 flex-col rounded-lg border border-line">
        {!active ? (
          <div className="flex flex-1 items-center justify-center text-sm text-ink-3">
            Start a new chat — ask about any instrument, forecast, or agent decision.
          </div>
        ) : (
          <>
            <div className="min-h-0 flex-1 space-y-4 overflow-y-auto p-4">
              {messages.data?.map((m) => (
                <div key={m.id} className={clsx("flex", m.role === "user" ? "justify-end" : "justify-start")}>
                  <div
                    className={clsx(
                      "max-w-[80%] rounded-lg px-3.5 py-2.5 text-sm leading-relaxed",
                      m.role === "user" ? "bg-accent text-white" : "bg-surface-2",
                    )}
                  >
                    {m.role === "assistant" ? (
                      <div className="prose-sm [&_h1]:text-base [&_h2]:text-sm [&_h3]:text-sm [&_li]:my-0.5 [&_p]:my-1 [&_strong]:font-semibold [&_ul]:my-1 [&_ul]:list-disc [&_ul]:pl-4">
                        <ReactMarkdown>{m.content}</ReactMarkdown>
                        <ContextChips ctx={m.context} />
                      </div>
                    ) : (
                      m.content
                    )}
                  </div>
                </div>
              ))}
              {send.isPending && (
                <div className="flex justify-start">
                  <div className="rounded-lg bg-surface-2 px-3.5 py-2.5 text-sm text-ink-3">thinking…</div>
                </div>
              )}
              {send.error && <p className="text-sm text-loss">{String(send.error)}</p>}
              <div ref={bottom} />
            </div>
            <div className="flex gap-2 border-t border-line p-3">
              <input
                value={draft}
                onChange={(e) => setDraft(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && submit()}
                placeholder="How does RELIANCE look this week?"
                disabled={send.isPending}
                className="min-w-0 flex-1 rounded-md border border-line bg-surface px-3 py-2 text-sm outline-none focus:border-accent disabled:opacity-60"
              />
              <button
                onClick={submit}
                disabled={send.isPending || !draft.trim()}
                aria-label="Send"
                className="rounded-md bg-accent px-3 py-2 text-white hover:opacity-90 disabled:opacity-50"
              >
                <Send size={15} />
              </button>
            </div>
          </>
        )}
      </section>
    </div>
  );
}
