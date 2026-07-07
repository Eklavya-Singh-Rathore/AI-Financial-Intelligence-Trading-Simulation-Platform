// Typed client over the same-origin proxy (mirrors the FastAPI pydantic schemas).

export type InstrumentSummary = {
  symbol: string;
  display_name: string;
  instrument_type: string;
  last_date: string | null;
  last_close: number | null;
  change_1d_pct: number | null;
  change_5d_pct: number | null;
  change_20d_pct: number | null;
  sparkline: number[];
};

export type PriceBar = {
  date: string; open: number; high: number; low: number; close: number;
  adj_close: number | null; volume: number;
};

export type IndicatorPoint = { date: string; values: Record<string, number | null> };

export type ForecastOut = {
  symbol: string; model_name: string; horizon: number;
  points: { step: number; target_date: string; predicted_close: number }[];
  meta: Record<string, unknown>;
};

export type BacktestResult = {
  strategy_name: string; engine: string; symbol: string;
  start: string | null; end: string | null;
  metrics: Record<string, number>; meta: Record<string, unknown>;
};

export type AgentRun = {
  id: string; symbol: string; status: string; trigger: string;
  llm_provider: string | null; debate_rounds: number;
  final_decision: Record<string, unknown> | null;
  token_usage: Record<string, number> | null;
  error: string | null; started_at: string | null; finished_at: string | null;
  created_at: string;
};

export type AgentMessage = {
  seq: number; agent_name: string; content: string;
  structured: Record<string, unknown> | null;
  provider: string | null; model: string | null;
  usage: Record<string, number> | null; latency_ms: number | null; created_at: string;
};

export type ChatSession = { id: string; title: string; created_at: string; updated_at: string };

export type ChatMessage = {
  id: string; seq: number; role: string; content: string;
  context: { symbols?: string[]; decisions_used?: number; memory_notes_used?: number } | null;
  usage: Record<string, number> | null; latency_ms: number | null; created_at: string;
};

export type ChatTurn = { user_message: ChatMessage; assistant_message: ChatMessage };

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`/api/backend/${path}`, {
    ...init,
    headers: { "content-type": "application/json", ...(init?.headers ?? {}) },
  });
  if (!res.ok) {
    let detail = `${res.status}`;
    try {
      const body = await res.json();
      detail = body.detail ?? JSON.stringify(body);
    } catch { /* keep status */ }
    throw new Error(detail);
  }
  if (res.status === 204) return undefined as T;
  return res.json() as Promise<T>;
}

export const api = {
  health: () => request<{ status: string; database: string }>("health"),
  summary: () => request<InstrumentSummary[]>("instruments/summary"),
  prices: (symbol: string, limit = 400) =>
    request<{ symbol: string; bars: PriceBar[] }>(
      `instruments/${encodeURIComponent(symbol)}/prices?limit=${limit}`,
    ),
  indicators: (symbol: string, names: string) =>
    request<{ points: IndicatorPoint[] }>(
      `instruments/${encodeURIComponent(symbol)}/indicators?names=${names}`,
    ),
  forecast: (symbol: string, model: string, horizon = 5) =>
    request<ForecastOut>(
      `instruments/${encodeURIComponent(symbol)}/forecast?horizon=${horizon}&model=${model}&persist=false`,
    ),
  backtest: (body: {
    symbol: string; engine: string; params: { fast: number; slow: number };
  }) => request<BacktestResult>("backtest", { method: "POST", body: JSON.stringify(body) }),
  ingest: () =>
    request<{ status: string }>("ingest/run", {
      method: "POST",
      body: JSON.stringify({ background: true, days: 30 }),
    }),
  runs: () => request<AgentRun[]>("agents/runs"),
  run: (id: string) => request<AgentRun>(`agents/runs/${id}`),
  runMessages: (id: string) => request<AgentMessage[]>(`agents/runs/${id}/messages`),
  startRun: (symbol: string) =>
    request<AgentRun>("agents/run", { method: "POST", body: JSON.stringify({ symbol }) }),
  chatSessions: () => request<ChatSession[]>("chat/sessions"),
  createChat: () => request<ChatSession>("chat/sessions", { method: "POST" }),
  deleteChat: (id: string) => request<void>(`chat/sessions/${id}`, { method: "DELETE" }),
  chatMessages: (id: string) => request<ChatMessage[]>(`chat/sessions/${id}/messages`),
  sendChat: (id: string, content: string) =>
    request<ChatTurn>(`chat/sessions/${id}/messages`, {
      method: "POST",
      body: JSON.stringify({ content }),
    }),
};

export function fmtPct(v: number | null | undefined): string {
  if (v === null || v === undefined) return "–";
  return `${v > 0 ? "+" : ""}${v.toFixed(2)}%`;
}

export function fmtNum(v: number | null | undefined, digits = 2): string {
  if (v === null || v === undefined) return "–";
  return v.toLocaleString("en-IN", { maximumFractionDigits: digits });
}

export function polarity(v: number | null | undefined): string {
  if (v === null || v === undefined || v === 0) return "text-ink-2";
  return v > 0 ? "text-gain" : "text-loss";
}
