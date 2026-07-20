// Indicator catalog (Phase 6.5). Data-driven so useTradingChart renders any
// selected indicator generically. Each `id` doubles as the backend indicator
// name sent to GET /indicators?names=… and matches the output column keys.

export type IndColor = "accent" | "gain" | "loss" | "ink3";
export type IndLine = { col: string; color: IndColor; dashed?: boolean; width?: number };
export type IndBand = { upper: string; lower: string; fill?: boolean };
export type IndLevel = { value: number; color: IndColor };

export type IndicatorDef = {
  id: string;
  label: string;
  /** true = its own sub-pane below price; false = overlaid on the price pane. */
  pane: boolean;
  lines?: IndLine[];
  /** green-when-positive / red-when-negative histogram column (macd, obv). */
  histogram?: string;
  band?: IndBand;
  /** horizontal reference lines (pane indicators like RSI 30/70). */
  levels?: IndLevel[];
};

export const INDICATORS: IndicatorDef[] = [
  // --- price overlays ---
  { id: "sma", label: "SMA (20)", pane: false, lines: [{ col: "sma_20", color: "accent" }] },
  { id: "ema", label: "EMA (20)", pane: false, lines: [{ col: "ema_20", color: "ink3" }] },
  {
    id: "bollinger",
    label: "Bollinger Bands",
    pane: false,
    band: { upper: "bb_upper", lower: "bb_lower" },
    lines: [{ col: "bb_mid", color: "ink3" }],
  },
  { id: "vwap", label: "VWAP", pane: false, lines: [{ col: "vwap", color: "accent", dashed: true }] },
  { id: "supertrend", label: "SuperTrend", pane: false, lines: [{ col: "supertrend", color: "gain", width: 2 }] },
  { id: "psar", label: "Parabolic SAR", pane: false, lines: [{ col: "psar", color: "loss" }] },
  {
    id: "donchian",
    label: "Donchian Channel",
    pane: false,
    band: { upper: "donchian_upper", lower: "donchian_lower" },
    lines: [{ col: "donchian_mid", color: "ink3" }],
  },
  {
    id: "ichimoku",
    label: "Ichimoku Cloud",
    pane: false,
    band: { upper: "ichimoku_senkou_a", lower: "ichimoku_senkou_b", fill: true },
    lines: [
      { col: "ichimoku_tenkan", color: "accent" },
      { col: "ichimoku_kijun", color: "loss" },
    ],
  },
  // --- sub-panes ---
  {
    id: "rsi",
    label: "RSI (14)",
    pane: true,
    lines: [{ col: "rsi_14", color: "accent" }],
    levels: [
      { value: 70, color: "loss" },
      { value: 30, color: "gain" },
    ],
  },
  {
    id: "macd",
    label: "MACD",
    pane: true,
    histogram: "macd_hist",
    lines: [
      { col: "macd", color: "accent" },
      { col: "macd_signal", color: "ink3" },
    ],
  },
  { id: "atr", label: "ATR (14)", pane: true, lines: [{ col: "atr_14", color: "accent" }] },
  {
    id: "adx",
    label: "ADX (14)",
    pane: true,
    lines: [
      { col: "adx_14", color: "accent", width: 2 },
      { col: "plus_di_14", color: "gain" },
      { col: "minus_di_14", color: "loss" },
    ],
    levels: [{ value: 25, color: "ink3" }],
  },
  {
    id: "stochrsi",
    label: "Stochastic RSI",
    pane: true,
    lines: [
      { col: "stochrsi_k", color: "accent" },
      { col: "stochrsi_d", color: "ink3" },
    ],
    levels: [
      { value: 80, color: "loss" },
      { value: 20, color: "gain" },
    ],
  },
  {
    id: "cci",
    label: "CCI (20)",
    pane: true,
    lines: [{ col: "cci_20", color: "accent" }],
    levels: [
      { value: 100, color: "loss" },
      { value: -100, color: "gain" },
    ],
  },
  { id: "obv", label: "OBV", pane: true, lines: [{ col: "obv", color: "accent" }] },
];

export const INDICATOR_IDS: string[] = INDICATORS.map((i) => i.id);

const BY_ID: Record<string, IndicatorDef> = Object.fromEntries(INDICATORS.map((i) => [i.id, i]));

export function indicatorById(id: string): IndicatorDef | undefined {
  return BY_ID[id];
}

/** Resolve enabled ids to defs, preserving catalog order (stable pane indices). */
export function enabledDefs(ids: readonly string[]): IndicatorDef[] {
  const set = new Set(ids);
  return INDICATORS.filter((i) => set.has(i.id));
}

/** Comma-joined backend names to request from GET /indicators. */
export function backendNames(ids: readonly string[]): string {
  return enabledDefs(ids)
    .map((i) => i.id)
    .join(",");
}
