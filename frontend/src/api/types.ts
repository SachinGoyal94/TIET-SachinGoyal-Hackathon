/** Shared API types, kept in sync with src/engine/api/schemas.py. */

export interface Health {
  status: "ok" | "initializing";
  version: string;
  ready: boolean;
  models_loaded: boolean;
  components: {
    risk_engine: boolean;
    rebalancer_module: boolean;
    stress_testing_module: boolean;
  };
}

export const EVENT_LABELS = [
  "Geopolitical",
  "Macroeconomic",
  "Credit Event",
  "Merger/Acquisition",
  "Product Launch",
  "Other",
] as const;

export type EventLabel = (typeof EVENT_LABELS)[number];

export interface Signal {
  id: number;
  scope: "company" | "sector" | "market";
  entity: string;
  sentiment_score: number;
  event_label: EventLabel;
  event_confidence: number;
  impact_score: number;
  analyzed_at: string;
}

export interface RiskEvent {
  id: number;
  event_label: EventLabel;
  headline: string;
  first_entity: string | null;
  first_seen: string;
  last_seen: string;
  n_sources: number;
  avg_sentiment: number;
  avg_impact: number;
  max_impact: number;
  is_active: boolean;
}

export interface AnalyzeResult {
  article_id: number;
  event_id: number;
  cluster_action: "created" | "merged";
  n_sources: number;
  sentiment_score: number;
  event_label: EventLabel;
  impact_score: number;
  cluster_max_impact: number;
  entities: string[];
  per_entity?: Record<string, number>;
}

export interface TickerInfo {
  ticker: string;
  name: string;
  sector: string;
}

export interface Stats {
  articles: number;
  signals: number;
  active_events: number;
  articles_24h: number;
  stress_runs: number;
}

export interface WeightRow {
  ticker: string;
  weight: number;
  anchor_weight: number;
  delta: number;
  sentiment: number;
}

export interface WeightsSnapshot {
  ts: string | null;
  weights: WeightRow[];
}

export interface HistoryTick {
  ts: string;
  weights: Record<string, number>;
}

export interface AssetClassAgg {
  value_before: number;
  pnl: number;
  pnl_pct: number;
}

export interface ScenarioInfo {
  name: string;
  family: string;
  description: string;
  source: string;
  shocks: {
    equity_pct: number;
    rates_bps: number;
    spread_bps: number;
    fx_pct: number;
  };
}

export interface CapitalView {
  cet1_start: number;
  ppnr: number;
  total_losses: number;
  cet1_end: number;
  ratio_start_pct: number;
  ratio_end_pct: number;
  depletion_bps: number;
  breach: boolean;
}

export interface StressResult {
  event_label: EventLabel;
  impact_score: number;
  scenario?: string | null;
  shocks: {
    equity_pct: number;
    rates_bps: number;
    spread_bps: number;
    fx_pct: number;
    band_scale: number;
  };
  value_before: number;
  value_after: number;
  pnl: number;
  pnl_pct: number;
  by_asset_class: Record<string, AssetClassAgg>;
  top_losers: { id: string; name: string; asset_class: string; value_before: number; pnl: number }[];
  risk_indicators: {
    portfolio_notional: number;
    bond_duration: number;
    spread_duration: number;
    equity_delta_exposure: number;
    loan_expected_loss: number;
    loan_expected_loss_pct: number;
  };
  monte_carlo: {
    draws: number;
    var95: number;
    es95: number;
    p5_pnl: number;
    median_pnl: number;
    p95_pnl: number;
  };
  capital?: CapitalView;
  run_id?: number;
  triggered_by?: string;
}

export interface StressRunSummary {
  id: number;
  ts: string;
  event_id: number | null;
  event_label: EventLabel;
  event_headline: string;
  impact_score: number;
  triggered_by: string;
  value_before: number;
  value_after: number;
  pnl: number;
  pnl_pct: number;
}

export interface PortfolioPosition {
  id: string;
  asset_class: string;
  sub_type: string;
  name: string;
  notional?: number;
  value?: number;
  rating?: string;
  sector?: string;
  region?: string;
}

export interface Portfolio {
  portfolio_name: string;
  base_currency: string;
  total_notional: number;
  by_asset_class: Record<string, { count: number; notional: number }>;
  positions: PortfolioPosition[];
}
