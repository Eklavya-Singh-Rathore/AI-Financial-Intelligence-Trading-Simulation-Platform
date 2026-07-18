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

export type UniverseSummary = { items: InstrumentSummary[]; total: number };

export type SummaryParams = {
  q?: string; types?: string; watchlist_id?: string; limit?: number; offset?: number;
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

export type ChatCitation = {
  n: number; title: string; url: string | null;
  published_at: string | null; symbol: string | null;
};

export type ChatMessage = {
  id: string; seq: number; role: string; content: string;
  context: {
    symbols?: string[]; decisions_used?: number; memory_notes_used?: number;
    news_used?: number; citations?: ChatCitation[];
  } | null;
  usage: Record<string, number> | null; latency_ms: number | null; created_at: string;
};

export type ChatTurn = { user_message: ChatMessage; assistant_message: ChatMessage };

// --- Simulation (Phase 5) ----------------------------------------------------

export type SimPosition = {
  symbol: string; qty: number; avg_cost: number; last_price: number;
  price_date: string | null; market_value: number; unrealized_pnl: number;
  allocation_pct: number;
};

export type SimPortfolio = {
  portfolio_id: string; name: string; created_at: string;
  starting_cash: number; cash: number; buying_power: number;
  holdings_value: number; equity: number; total_pnl: number; total_pnl_pct: number;
  realized_pnl: number; cash_allocation_pct: number; positions: SimPosition[];
};

export type SimOrder = {
  id: string; symbol: string; side: "buy" | "sell";
  order_type: "market" | "limit" | "stop"; qty: number;
  limit_price: number | null; stop_price: number | null;
  status: string; source: "manual" | "ai"; agent_run_id: string | null;
  reason: string | null; created_at: string; filled_at: string | null;
};

export type SimTrade = {
  id: string; order_id: string; symbol: string; side: string; qty: number;
  price: number; value: number; realized_pnl: number | null; created_at: string;
};

export type SimPerformance = {
  metrics: Record<string, number | null>;
  series: { date: string; equity: number; drawdown_pct: number }[];
  ai_vs_manual: Record<string, {
    filled_orders: number; closed_trades: number;
    realized_pnl: number; win_rate: number | null;
  }>;
};

export type SimIntelligence = {
  risk_score: number; portfolio_volatility_pct: number;
  sector_exposure: { sector: string; value: number; pct: number }[];
  diversification: { positions: number; hhi: number; effective_positions: number };
  concentration: { symbol: string; allocation_pct: number; flag: string }[];
  correlation: { symbols: string[]; matrix: (number | null)[][] };
  suggestions: string[];
};

export type OrderCreate = {
  symbol: string; side: "buy" | "sell"; order_type: "market" | "limit" | "stop";
  qty: number; limit_price?: number; stop_price?: number;
};

export type EvaluationSummary = {
  forecast_accuracy: {
    models: Record<string, { evaluated_points: number; mape_pct: number; bias_pct: number }>;
    evaluated_points: number;
  };
  agents: {
    runs_by_status: Record<string, number>;
    action_mix: Record<string, number>;
    avg_confidence: number | null;
    stance_agreement_pct: number | null;
    stance_pairs_evaluated: number;
  };
  recommendation_success: {
    evaluated: number;
    success_rate: number | null;
    avg_return_pct: number | null;
    by_action: Record<string, { n: number; avg_return_pct: number }>;
  };
  usage: {
    runs_window: number;
    llm_calls: number;
    input_tokens: number;
    output_tokens: number;
    est_cost_usd: number;
    avg_run_seconds: number | null;
    avg_message_latency_ms: number | null;
  };
};

export type RunExplanation = {
  run_id: string; symbol: string; status: string; as_of: string | null;
  decision: Record<string, unknown>;
  why: string[];
  technical: { stance?: string; confidence?: number; report?: string };
  news: {
    stance?: string; sentiment_score?: number; confidence?: number;
    report?: string; headlines: string[];
  };
  debate: {
    bull: { argument?: string; key_points: string[] }[];
    bear: { argument?: string; key_points: string[] }[];
  };
  risk: {
    verdict?: string; adjusted_size_pct?: number; concerns: string[];
    rationale?: string; limited_by: string[];
  };
  indicators: Record<string, number | null>;
  price_summary: Record<string, number | null>;
  forecast: { model?: string; horizon_days?: number; predicted_closes?: number[] };
  backtest: { engine?: string; metrics?: Record<string, number> };
  has_snapshot: boolean;
};

// --- Financial research (Phase 5) --------------------------------------------

export type CompanyProfile = {
  symbol: string;
  profile: Record<string, string | number | null>;
  fetched_at: string | null;
  source: string;
};

export type FinancialStatement = {
  symbol: string; period: string; statement: string;
  data: { periods: string[]; rows: Record<string, (number | null)[]> };
  fetched_at: string | null; source: string;
};

export type EarningsQuarter = {
  period: string; revenue: number | null; net_income: number | null; eps: number | null;
  revenue_qoq_pct: number | null; revenue_yoy_pct: number | null;
  net_income_qoq_pct: number | null; net_income_yoy_pct: number | null;
};

export type EarningsOut = {
  symbol: string; quarters: EarningsQuarter[]; latest: EarningsQuarter | null;
  fetched_at: string | null; source: string;
};

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
  summary: (params?: SummaryParams) => {
    const qs = new URLSearchParams();
    if (params?.q) qs.set("q", params.q);
    if (params?.types) qs.set("types", params.types);
    if (params?.watchlist_id) qs.set("watchlist_id", params.watchlist_id);
    if (params?.limit !== undefined) qs.set("limit", String(params.limit));
    if (params?.offset) qs.set("offset", String(params.offset));
    const suffix = qs.size ? `?${qs}` : "";
    return request<UniverseSummary>(`instruments/summary${suffix}`);
  },
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
  runExplanation: (id: string) => request<RunExplanation>(`agents/runs/${id}/explanation`),
  evaluationSummary: () => request<EvaluationSummary>("evaluation/summary"),
  startRun: (symbol: string) =>
    request<AgentRun>("agents/run", { method: "POST", body: JSON.stringify({ symbol }) }),
  simPortfolio: () => request<SimPortfolio>("simulation/portfolio"),
  simPlaceOrder: (body: OrderCreate) =>
    request<SimOrder>("simulation/orders", { method: "POST", body: JSON.stringify(body) }),
  simOrders: (status?: string) =>
    request<SimOrder[]>(`simulation/orders${status ? `?status=${status}` : ""}`),
  simCancelOrder: (id: string) =>
    request<SimOrder>(`simulation/orders/${id}`, { method: "DELETE" }),
  simAcceptOrder: (id: string) =>
    request<SimOrder>(`simulation/orders/${id}/accept`, { method: "POST" }),
  simRejectOrder: (id: string) =>
    request<SimOrder>(`simulation/orders/${id}/reject`, { method: "POST" }),
  simTrades: () => request<SimTrade[]>("simulation/trades"),
  simPerformance: () => request<SimPerformance>("simulation/performance"),
  simIntelligence: () => request<SimIntelligence>("simulation/intelligence"),
  simPropose: (agentRunId: string) =>
    request<SimOrder>("simulation/proposals", {
      method: "POST",
      body: JSON.stringify({ agent_run_id: agentRunId }),
    }),
  profile: (symbol: string) =>
    request<CompanyProfile>(`instruments/${encodeURIComponent(symbol)}/profile`),
  financials: (symbol: string, period: string, statement: string) =>
    request<FinancialStatement>(
      `instruments/${encodeURIComponent(symbol)}/financials?period=${period}&statement=${statement}`,
    ),
  earnings: (symbol: string) =>
    request<EarningsOut>(`instruments/${encodeURIComponent(symbol)}/earnings`),
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
