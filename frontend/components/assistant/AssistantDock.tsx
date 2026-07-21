"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Bot, Send, Sparkles } from "lucide-react";
import { usePathname } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import ReactMarkdown from "react-markdown";
import clsx from "clsx";
import { ContextChips } from "@/components/chat/ContextChips";
import { Sheet, Spinner } from "@/components/ui";
import { api } from "@/lib/api";
import { resolveAssistantSession, withRouteContext } from "@/lib/assistantSession.mjs";

const STORAGE_KEY = "assistant_session_id";

/** Site-wide floating assistant (Phase 6). Talks to a single dedicated chat
 *  session (persisted in localStorage, validated against the server on open).
 *  Reuses the /chat backend — messages on an instrument page are grounded with
 *  a "[viewing SYMBOL]" prefix. /chat remains the place for long sessions. */
export function AssistantDock() {
  const pathname = usePathname();
  const qc = useQueryClient();
  const [open, setOpen] = useState(false);
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [initError, setInitError] = useState<string | null>(null);
  const [initializing, setInitializing] = useState(false);
  const [draft, setDraft] = useState("");
  const bottom = useRef<HTMLDivElement>(null);

  const symbolMatch = pathname.match(/^\/instruments\/([^/]+)/);
  const symbol = symbolMatch ? decodeURIComponent(symbolMatch[1]) : null;
  const suggestions = symbol
    ? ["How does it look this week?", "What's the forecast?", "Any recent news?"]
    : [
        "Summarize the market today",
        "How are my holdings doing?",
        "What did the agents decide recently?",
      ];

  const messages = useQuery({
    queryKey: ["chatMessages", sessionId],
    queryFn: () => api.chatMessages(sessionId!),
    enabled: !!sessionId,
  });

  const send = useMutation({
    mutationFn: (content: string) =>
      api.sendChat(sessionId!, withRouteContext(pathname, content)),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["chatMessages", sessionId] }),
  });

  // Lazily resolve (or create) the dedicated assistant session when opened.
  const openDock = async () => {
    setOpen(true);
    if (sessionId || initializing) return;
    setInitializing(true);
    setInitError(null);
    try {
      const list = await qc.fetchQuery({ queryKey: ["chatSessions"], queryFn: api.chatSessions });
      const resolved = resolveAssistantSession(localStorage.getItem(STORAGE_KEY), list);
      if (resolved) {
        setSessionId(resolved);
      } else {
        const created = await api.createChat();
        localStorage.setItem(STORAGE_KEY, created.id);
        setSessionId(created.id);
        qc.invalidateQueries({ queryKey: ["chatSessions"] });
      }
    } catch (e) {
      setInitError(String(e));
    } finally {
      setInitializing(false);
    }
  };

  useEffect(() => {
    if (open) bottom.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages.data, send.isPending, open]);

  const submit = (text?: string) => {
    const content = (text ?? draft).trim();
    if (!content || !sessionId || send.isPending) return;
    setDraft("");
    send.mutate(content);
  };

  // Hidden on the auth/landing page and on the dedicated Chat page (which is the
  // full chat surface — a floating mini-chat there would be redundant/confusing).
  if (pathname.startsWith("/login") || pathname.startsWith("/chat")) return null;
  const empty = !!sessionId && (messages.data?.length ?? 0) === 0 && !send.isPending;

  return (
    <>
      {!open && (
        <button
          type="button"
          aria-label="Open AI assistant"
          onClick={openDock}
          className="fixed bottom-5 right-5 z-40 flex size-12 items-center justify-center rounded-full bg-grad-primary text-on-accent shadow-glow transition hover:brightness-105 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/50"
        >
          <Bot size={20} />
        </button>
      )}

      <Sheet
        open={open}
        onClose={() => setOpen(false)}
        side="right"
        title={
          <span className="flex items-center gap-1.5">
            <Sparkles size={15} className="text-accent" /> Assistant
          </span>
        }
      >
        <div className="flex h-full flex-col">
          <div className="min-h-0 flex-1 space-y-3 overflow-y-auto p-4">
            {initError ? (
              <p className="text-sm text-loss">Couldn&apos;t start the assistant. {initError}</p>
            ) : !sessionId ? (
              <div className="flex h-full items-center justify-center gap-2 text-sm text-ink-3">
                <Spinner size={16} /> Starting…
              </div>
            ) : (
              <>
                {empty && (
                  <div className="pt-1">
                    <p className="text-sm text-ink-2">
                      Ask about any instrument{symbol ? ` — you're viewing ${symbol}` : ""}, its
                      Kronos forecast, recent news, or a recent agent decision.
                    </p>
                    <div className="mt-3 flex flex-col gap-1.5">
                      {suggestions.map((s) => (
                        <button
                          key={s}
                          type="button"
                          onClick={() => submit(s)}
                          className="rounded-md border border-line px-3 py-1.5 text-left text-sm text-ink-2 transition hover:border-accent/50 hover:text-ink"
                        >
                          {s}
                        </button>
                      ))}
                    </div>
                  </div>
                )}
                {messages.data?.map((m) => (
                  <div
                    key={m.id}
                    className={clsx("flex", m.role === "user" ? "justify-end" : "justify-start")}
                  >
                    <div
                      className={clsx(
                        "max-w-[85%] rounded-lg px-3 py-2 text-sm leading-relaxed",
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
                    <div className="rounded-lg bg-surface-2 px-3 py-2 text-sm text-ink-3">
                      thinking…
                    </div>
                  </div>
                )}
                {send.error && <p className="text-sm text-loss">{String(send.error)}</p>}
              </>
            )}
            <div ref={bottom} />
          </div>

          <div className="flex gap-2 border-t border-line p-3">
            <input
              value={draft}
              onChange={(e) => setDraft(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && submit()}
              placeholder={symbol ? `Ask about ${symbol}…` : "Ask about any instrument…"}
              disabled={!sessionId || send.isPending}
              className="min-w-0 flex-1 rounded-md border border-line bg-surface px-3 py-2 text-sm outline-none focus:border-accent disabled:opacity-60"
            />
            <button
              type="button"
              onClick={() => submit()}
              disabled={!sessionId || send.isPending || !draft.trim()}
              aria-label="Send"
              className="rounded-md bg-accent px-3 py-2 text-on-accent transition hover:opacity-90 disabled:opacity-50"
            >
              <Send size={15} />
            </button>
          </div>
        </div>
      </Sheet>
    </>
  );
}
