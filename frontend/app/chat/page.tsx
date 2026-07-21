"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { MessageSquare, Plus, Send, Trash2 } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import ReactMarkdown from "react-markdown";
import clsx from "clsx";
import { ContextChips } from "@/components/chat/ContextChips";
import { Button, EmptyState, Input } from "@/components/ui";
import { api } from "@/lib/api";

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
    <div className="flex flex-col gap-4 md:h-[calc(100vh-6.5rem)] md:flex-row">
      <aside className="flex max-h-56 w-full shrink-0 flex-col rounded-xl border border-line md:max-h-none md:w-64">
        <Button
          variant="outline"
          size="sm"
          onClick={() => createSession.mutate()}
          className="m-2"
        >
          <Plus size={14} /> New chat
        </Button>
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

      <section className="flex min-h-[24rem] min-w-0 flex-1 flex-col rounded-xl border border-line md:min-h-0">
        {!active ? (
          <div className="flex flex-1 items-center justify-center">
            <EmptyState
              icon={MessageSquare}
              title="Start a conversation"
              description="Ask about any instrument, its forecast, recent news, or a past agent decision."
            />
          </div>
        ) : (
          <>
            <div className="min-h-0 flex-1 space-y-4 overflow-y-auto p-4">
              {messages.data?.map((m) => (
                <div key={m.id} className={clsx("flex", m.role === "user" ? "justify-end" : "justify-start")}>
                  <div
                    className={clsx(
                      "max-w-[80%] rounded-2xl px-3.5 py-2.5 text-sm leading-relaxed shadow-xs",
                      m.role === "user" ? "bg-accent text-on-accent" : "bg-surface-2",
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
              <Input
                value={draft}
                onChange={(e) => setDraft(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && submit()}
                placeholder="How does RELIANCE look this week?"
                disabled={send.isPending}
                className="flex-1"
              />
              <Button
                onClick={submit}
                disabled={send.isPending || !draft.trim()}
                size="icon"
                aria-label="Send"
              >
                <Send size={15} />
              </Button>
            </div>
          </>
        )}
      </section>
    </div>
  );
}
