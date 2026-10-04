import type {
  AnalyzeResult,
  Health,
  Portfolio,
  RiskEvent,
  ScenarioInfo,
  Signal,
  Stats,
  StressResult,
  StressRunSummary,
  TickerInfo,
  WeightsSnapshot,
  HistoryTick,
} from "./types";

const BASE = "/api";

async function get<T>(path: string, params?: Record<string, string | number | boolean | undefined>): Promise<T> {
  const qs = params
    ? "?" + new URLSearchParams(
        Object.entries(params)
          .filter(([, v]) => v !== undefined)
          .map(([k, v]) => [k, String(v)]),
      ).toString()
    : "";
  const res = await fetch(`${BASE}${path}${qs}`);
  if (!res.ok) throw new Error(`${path} failed: ${res.status}`);
  return res.json() as Promise<T>;
}

async function post<T>(path: string, body: unknown): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    const detail = await res.json().catch(() => null);
    throw new Error(detail?.detail ?? `${path} failed: ${res.status}`);
  }
  return res.json() as Promise<T>;
}

export const api = {
  health: () => get<Health>("/health"),
  stats: () => get<Stats>("/stats"),
  signals: (limit = 100, scope?: string, entity?: string) =>
    get<{ count: number; signals: Signal[] }>("/signals", { limit, scope, entity }),
  events: (activeOnly = true, limit = 50) =>
    get<{ count: number; events: RiskEvent[] }>("/events", { active_only: activeOnly, limit }),
  analyze: (text: string) => post<AnalyzeResult>("/analyze", { text }),
  universe: () => get<{ tickers: TickerInfo[]; sectors: string[] }>("/universe"),
  weights: () => get<WeightsSnapshot>("/rebalance/weights"),
  weightHistory: (hours = 168) =>
    get<{ ticks: HistoryTick[] }>("/rebalance/history", { hours }),
  portfolio: () => get<Portfolio>("/portfolio"),
  scenarios: () => get<{ count: number; scenarios: ScenarioInfo[] }>("/stress/scenarios"),
  runStress: (eventId?: number, scenario?: string) =>
    post<StressResult>("/stress/run", { event_id: eventId ?? null, scenario: scenario ?? null }),
  reverseStress: (scenario: string) =>
    post<{ scenario: string; breach_multiple: number | null; cet1_ratio_at_breach_pct?: number; note?: string }>("/stress/reverse", { scenario }),
  stressRuns: (limit = 20) =>
    get<{ count: number; runs: StressRunSummary[] }>("/stress/runs", { limit }),
  stressLatest: () => get<{ run: (StressRunSummary & { details: StressResult }) | null }>("/stress/latest"),
};
