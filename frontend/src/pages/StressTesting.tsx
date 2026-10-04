import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import ReactECharts from "echarts-for-react";
import { api } from "../api/client";
import LabelPill from "../components/LabelPill";
import { baseOption, fmtMoney, fmtPct } from "../lib/format";

const CLASS_COLORS: Record<string, string> = {
  loan: "#38bdf8",
  bond: "#a78bfa",
  derivative: "#f59e0b",
  equity: "#10b981",
};

export default function StressTesting() {
  const qc = useQueryClient();
  const [selectedEvent, setSelectedEvent] = useState<number | null>(null);
  const [selectedScenario, setSelectedScenario] = useState<string>("");

  const { data: events } = useQuery({ queryKey: ["events", "stress"], queryFn: () => api.events(true, 40), refetchInterval: 15_000 });
  const { data: portfolio } = useQuery({ queryKey: ["portfolio"], queryFn: api.portfolio });
  const { data: runs } = useQuery({ queryKey: ["stressRuns"], queryFn: () => api.stressRuns(8), refetchInterval: 20_000 });
  const { data: latest } = useQuery({ queryKey: ["stressLatest"], queryFn: api.stressLatest, refetchInterval: 20_000 });
  const { data: scenarios } = useQuery({ queryKey: ["scenarios"], queryFn: api.scenarios });

  const runStress = useMutation({
    mutationFn: () => api.runStress(selectedEvent ?? undefined, selectedScenario || undefined),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["stressLatest"] });
      qc.invalidateQueries({ queryKey: ["stressRuns"] });
      qc.invalidateQueries({ queryKey: ["stats"] });
    },
  });

  const reverse = useMutation({
    mutationFn: (scenario: string) => api.reverseStress(scenario),
  });

  const run = latest?.run;
  const d = run?.details;

  const highRisk = events?.events.filter((e) => e.event_label === "Geopolitical" && e.max_impact > 7) ?? [];

  const composition = {
    ...baseOption,
    tooltip: { ...baseOption.tooltip, trigger: "item" },
    legend: { ...baseOption.legend, bottom: 0 },
    series: [{
      type: "pie",
      radius: ["45%", "70%"],
      center: ["50%", "45%"],
      label: { color: "#94a3b8", fontSize: 11, formatter: (p: { name: string; percent: number }) => `${p.name} ${p.percent}%` },
      data: Object.entries(portfolio?.by_asset_class ?? {}).map(([cls, agg]) => ({
        name: cls,
        value: agg.notional,
        itemStyle: { color: CLASS_COLORS[cls] ?? "#64748b" },
      })),
    }],
  };

  const beforeAfter = d ? {
    ...baseOption,
    grid: { left: 60, right: 20, top: 30, bottom: 30 },
    xAxis: { type: "category", data: ["Before", "After"], axisLabel: { color: "#94a3b8" } },
    yAxis: { type: "value", axisLabel: { color: "#94a3b8" }, splitLine: { lineStyle: { color: "#13203a" } } },
    series: [{
      type: "bar",
      barWidth: "35%",
      data: [
        { value: d.value_before, itemStyle: { color: "#334155" } },
        { value: d.value_after, itemStyle: { color: d.pnl < 0 ? "#f43f5e" : "#10b981" } },
      ],
      label: { show: true, position: "top", color: "#94a3b8", fontSize: 11, formatter: (p: { value: number }) => fmtMoney(p.value) },
    }],
  } : null;

  const waterfall = d ? {
    ...baseOption,
    grid: { left: 60, right: 20, top: 30, bottom: 40 },
    xAxis: { type: "category", data: Object.keys(d.by_asset_class), axisLabel: { color: "#94a3b8", fontSize: 11 } },
    yAxis: { type: "value", axisLabel: { color: "#94a3b8" }, splitLine: { lineStyle: { color: "#13203a" } } },
    series: [{
      type: "bar",
      barWidth: "45%",
      data: Object.entries(d.by_asset_class).map(([, agg]) => ({
        value: Math.round(agg.pnl),
        itemStyle: { color: agg.pnl < 0 ? "#f43f5e" : "#10b981" },
      })),
      label: { show: true, position: "bottom", color: "#94a3b8", fontSize: 10, formatter: (p: { value: number }) => fmtMoney(p.value) },
    }],
  } : null;

  return (
    <div className="space-y-6">
      <header>
        <h1 className="text-xl font-semibold text-slate-100">Module B — Portfolio Stress Testing</h1>
        <p className="mt-1 text-sm text-slate-500">
          Event-driven shocks applied to a synthetic wholesale banking book. High-impact
          geopolitical events (impact &gt; 7) trigger automatically; any event can be stressed
          manually below.
        </p>
      </header>

      {highRisk.length > 0 && (
        <div className="card border-rose-500/40 bg-rose-500/5 p-4">
          <div className="flex items-center gap-2 text-sm font-medium text-rose-300">
            <span className="h-2 w-2 animate-pulse rounded-full bg-rose-400" />
            {highRisk.length} high-impact geopolitical event{highRisk.length > 1 ? "s" : ""} active
            (auto-trigger rule armed)
          </div>
        </div>
      )}

      <div className="card p-5">
        <div className="card-title px-0 pt-0">Trigger a stress test</div>
        <div className="flex flex-wrap items-center gap-3">
          <select
            value={selectedScenario}
            onChange={(e) => { setSelectedScenario(e.target.value); setSelectedEvent(null); }}
            className="min-w-72 flex-1 rounded-lg border border-accent/40 bg-surface-850 px-4 py-2.5 text-sm text-accent outline-none"
          >
            <option value="">Scenario library (supervisory + historical)</option>
            {scenarios?.scenarios.map((s) => (
              <option key={s.name} value={s.name}>
                [{s.family}] {s.name}
              </option>
            ))}
          </select>
          <select
            value={selectedEvent ?? ""}
            onChange={(e) => { setSelectedEvent(e.target.value ? Number(e.target.value) : null); setSelectedScenario(""); }}
            className="min-w-72 flex-1 rounded-lg border border-surface-700 bg-surface-850 px-4 py-2.5 text-sm text-slate-200 outline-none focus:border-accent/60"
          >
            <option value="">Highest-impact live event (default)</option>
            {events?.events.map((ev) => (
              <option key={ev.id} value={ev.id}>
                [{ev.max_impact.toFixed(1)}] {ev.event_label}: {ev.headline.slice(0, 70)}
              </option>
            ))}
          </select>
          <button
            disabled={runStress.isPending}
            onClick={() => runStress.mutate()}
            className="rounded-lg bg-accent px-5 py-2.5 text-sm font-medium text-surface-950 transition-colors hover:bg-accent-dim disabled:opacity-40"
          >
            {runStress.isPending ? "Running…" : "Run stress test"}
          </button>
        </div>
        {selectedScenario && (
          <p className="mt-2 text-xs text-slate-500">
            {scenarios?.scenarios.find((s) => s.name === selectedScenario)?.description}
            <span className="ml-1 text-slate-600">Source: {scenarios?.scenarios.find((s) => s.name === selectedScenario)?.source}</span>
          </p>
        )}
        {runStress.isError && <p className="mt-2 text-xs text-rose-400">{(runStress.error as Error).message}</p>}
        {runStress.data && (
          <p className="mt-2 text-xs text-emerald-400">
            Run #{runStress.data.run_id} stored: {fmtPct(runStress.data.pnl_pct)} under{" "}
            {selectedScenario ? `scenario ${selectedScenario}` : `a ${runStress.data.event_label} shock`}.
          </p>
        )}
      </div>

      {run && d ? (
        <>
          <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
            <div className="card p-5">
              <div className="text-xs uppercase tracking-wider text-slate-500">Triggered by</div>
              <div className="mt-1.5 flex items-center gap-2">
                <span className="pill bg-surface-700 text-slate-200">{run.triggered_by}</span>
                <LabelPill label={run.event_label} />
              </div>
              <div className="mt-1 truncate text-xs text-slate-500" title={run.event_headline}>{run.event_headline}</div>
            </div>
            <div className="card p-5">
              <div className="text-xs uppercase tracking-wider text-slate-500">Impact score</div>
              <div className="mt-1.5 text-2xl font-semibold text-rose-400">{run.impact_score.toFixed(1)}</div>
              <div className="mt-0.5 text-xs text-slate-500">
                shocks: equities {(d.shocks.equity_pct * 100).toFixed(1)}%, rates {d.shocks.rates_bps}bp, spreads {d.shocks.spread_bps}bp
              </div>
            </div>
            <div className="card p-5">
              <div className="text-xs uppercase tracking-wider text-slate-500">Portfolio P&L</div>
              <div className={`mt-1.5 text-2xl font-semibold ${d.pnl < 0 ? "text-rose-400" : "text-emerald-400"}`}>{fmtMoney(d.pnl)}</div>
              <div className="mt-0.5 text-xs text-slate-500">{fmtPct(d.pnl_pct)} of the book</div>
            </div>
            <div className="card p-5">
              <div className="text-xs uppercase tracking-wider text-slate-500">Monte Carlo VaR 95 / ES 95</div>
              <div className="mt-1.5 text-2xl font-semibold text-amber-400">{fmtMoney(d.monte_carlo.var95)}</div>
              <div className="mt-0.5 text-xs text-slate-500">ES {fmtMoney(d.monte_carlo.es95)} over {d.monte_carlo.draws} draws</div>
            </div>
          </div>

          {d.capital && (
            <div className={`card p-5 ${d.capital.breach ? "border-rose-500/40 bg-rose-500/5" : "border-emerald-500/30 bg-emerald-500/5"}`}>
              <div className="flex flex-wrap items-center justify-between gap-4">
                <div>
                  <div className="text-xs uppercase tracking-wider text-slate-500">CET1 capital flow (regulatory view)</div>
                  <div className="mt-1.5 flex items-baseline gap-3">
                    <span className="text-2xl font-semibold text-slate-100">
                      {d.capital.ratio_start_pct.toFixed(2)}% → {d.capital.ratio_end_pct.toFixed(2)}%
                    </span>
                    <span className={`pill ${d.capital.breach ? "bg-rose-500/20 text-rose-300" : "bg-emerald-500/20 text-emerald-300"}`}>
                      {d.capital.breach ? "breaches minimum" : "survives"}
                    </span>
                  </div>
                  <div className="mt-0.5 text-xs text-slate-500">
                    depletion {d.capital.depletion_bps.toFixed(0)} bps · PPNR +{fmtMoney(d.capital.ppnr)} · losses {fmtMoney(d.capital.total_losses)}
                  </div>
                </div>
                <div className="flex items-center gap-2">
                  {selectedScenario && (
                    <button
                      onClick={() => reverse.mutate(selectedScenario)}
                      disabled={reverse.isPending}
                      className="rounded-lg border border-accent/50 px-4 py-2 text-xs font-medium text-accent hover:bg-accent/10 disabled:opacity-40"
                    >
                      {reverse.isPending ? "Solving…" : "Reverse stress: solve for breach"}
                    </button>
                  )}
                </div>
              </div>
              {reverse.data && (
                <p className="mt-2 text-xs text-amber-300">
                  {reverse.data.breach_multiple !== null
                    ? `Breach at ${reverse.data.breach_multiple}× the ${reverse.data.scenario} shocks (CET1 ${reverse.data.cet1_ratio_at_breach_pct?.toFixed(2)}% at breach).`
                    : reverse.data.note}
                </p>
              )}
            </div>
          )}

          <div className="grid gap-4 lg:grid-cols-2">
            <div className="card p-4">
              <div className="card-title px-0 pt-0">Portfolio value before vs after</div>
              {beforeAfter && <ReactECharts option={beforeAfter} style={{ height: 280 }} notMerge />}
            </div>
            <div className="card p-4">
              <div className="card-title px-0 pt-0">P&L by asset class</div>
              {waterfall && <ReactECharts option={waterfall} style={{ height: 280 }} notMerge />}
            </div>
          </div>

          <div className="grid gap-4 lg:grid-cols-3">
            <div className="card p-4">
              <div className="card-title px-0 pt-0">Book composition</div>
              <ReactECharts option={composition} style={{ height: 260 }} notMerge />
            </div>

            <div className="card">
              <div className="card-title">Top losers</div>
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-surface-700/40 text-left text-xs uppercase tracking-wider text-slate-500">
                    <th className="px-5 py-2 font-medium">Position</th>
                    <th className="px-3 py-2 font-medium">Class</th>
                    <th className="px-5 py-2 font-medium">P&L</th>
                  </tr>
                </thead>
                <tbody>
                  {d.top_losers.slice(0, 6).map((pos) => (
                    <tr key={pos.id} className="border-b border-surface-800/60 last:border-0">
                      <td className="max-w-40 truncate px-5 py-2 text-slate-200" title={pos.name}>{pos.name}</td>
                      <td className="px-3 py-2 text-xs text-slate-500">{pos.asset_class}</td>
                      <td className={`px-5 py-2 tabular-nums ${pos.pnl < 0 ? "text-rose-400" : "text-emerald-400"}`}>{fmtMoney(pos.pnl)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            <div className="card p-5">
              <div className="card-title px-0 pt-0">Risk indicators</div>
              <dl className="space-y-2.5 text-sm">
                {[
                  ["Book notional", fmtMoney(d.risk_indicators.portfolio_notional)],
                  ["Bond duration", `${d.risk_indicators.bond_duration.toFixed(2)}y`],
                  ["Spread duration", d.risk_indicators.spread_duration.toFixed(2)],
                  ["Equity delta exposure", fmtMoney(d.risk_indicators.equity_delta_exposure)],
                  ["Loan expected loss", `${fmtMoney(d.risk_indicators.loan_expected_loss)} (${d.risk_indicators.loan_expected_loss_pct.toFixed(2)}%)`],
                ].map(([k, v]) => (
                  <div key={k} className="flex items-center justify-between border-b border-surface-800/60 pb-2 last:border-0">
                    <dt className="text-slate-500">{k}</dt>
                    <dd className="tabular-nums text-slate-200">{v}</dd>
                  </div>
                ))}
              </dl>
            </div>
          </div>
        </>
      ) : (
        <div className="card flex h-40 items-center justify-center text-sm text-slate-500">
          No stress run yet. Pick an event and hit Run, or wait for the auto-trigger.
        </div>
      )}

      <div className="card">
        <div className="card-title">Stress run history</div>
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-surface-700/40 text-left text-xs uppercase tracking-wider text-slate-500">
              <th className="px-5 py-2 font-medium">When</th>
              <th className="px-3 py-2 font-medium">Event</th>
              <th className="px-3 py-2 font-medium">Trigger</th>
              <th className="px-3 py-2 font-medium">Impact</th>
              <th className="px-5 py-2 font-medium">P&L</th>
            </tr>
          </thead>
          <tbody>
            {(runs?.runs ?? []).map((r) => (
              <tr key={r.id} className="border-b border-surface-800/60 last:border-0">
                <td className="px-5 py-2 text-xs text-slate-500">{new Date(r.ts).toLocaleString()}</td>
                <td className="px-3 py-2"><LabelPill label={r.event_label} /></td>
                <td className="px-3 py-2 text-xs text-slate-400">{r.triggered_by}</td>
                <td className="px-3 py-2 tabular-nums text-slate-300">{r.impact_score.toFixed(1)}</td>
                <td className={`px-5 py-2 tabular-nums ${r.pnl < 0 ? "text-rose-400" : "text-emerald-400"}`}>{fmtMoney(r.pnl)} ({fmtPct(r.pnl_pct)})</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
