import { useQuery } from "@tanstack/react-query";
import { api } from "../api/client";
import KpiCard from "../components/KpiCard";
import LabelPill from "../components/LabelPill";
import { fmtMoney, fmtSent, timeAgo } from "../lib/format";

export default function Overview() {
  const { data: stats } = useQuery({ queryKey: ["stats"], queryFn: api.stats, refetchInterval: 15_000 });
  const { data: events } = useQuery({ queryKey: ["events", "overview"], queryFn: () => api.events(true, 8), refetchInterval: 15_000 });
  const { data: weights } = useQuery({ queryKey: ["weights"], queryFn: api.weights, refetchInterval: 30_000 });
  const { data: latestStress } = useQuery({ queryKey: ["stressLatest"], queryFn: api.stressLatest, refetchInterval: 30_000 });

  const top = events?.events.slice(0, 6) ?? [];
  const movers = (weights?.weights ?? []).slice(0, 5);
  const stress = latestStress?.run;

  return (
    <div className="space-y-6">
      <header>
        <h1 className="text-xl font-semibold text-slate-100">Overview</h1>
        <p className="mt-1 text-sm text-slate-500">
          Live risk signals from unstructured news and social text, feeding a tactical
          index rebalancer and a strategic stress-testing engine.
        </p>
      </header>

      <div className="grid grid-cols-2 gap-4 lg:grid-cols-5">
        <KpiCard label="Articles 24h" value={String(stats?.articles_24h ?? "…")} sub={`${stats?.articles ?? "…"} total`} />
        <KpiCard label="Active events" value={String(stats?.active_events ?? "…")} sub={`${stats?.signals ?? "…"} signals`} />
        <KpiCard label="Stress runs" value={String(stats?.stress_runs ?? "…")} sub="auto + manual" />
        <KpiCard label="Top risk event" value={top[0] ? top[0].max_impact.toFixed(1) : "…"} sub={top[0]?.event_label ?? "none"} tone={(top[0]?.max_impact ?? 0) >= 8 ? "bad" : "default"} />
        <KpiCard
          label="Last stress P&L"
          value={stress ? fmtMoney(stress.pnl) : "…"}
          sub={stress ? `${stress.pnl_pct.toFixed(2)}% of book` : "no runs yet"}
          tone={stress ? (stress.pnl < 0 ? "bad" : "good") : "default"}
        />
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <div className="card">
          <div className="card-title">Active risk events</div>
          <div className="divide-y divide-surface-700/40">
            {top.map((ev) => (
              <div key={ev.id} className="flex items-center justify-between gap-3 px-5 py-3">
                <div className="min-w-0">
                  <div className="truncate text-sm text-slate-200">{ev.headline}</div>
                  <div className="mt-1 flex items-center gap-2 text-xs text-slate-500">
                    <LabelPill label={ev.event_label} />
                    <span>{ev.n_sources} sources</span>
                    <span>{timeAgo(ev.last_seen)}</span>
                  </div>
                </div>
                <div className="shrink-0 text-right">
                  <div className={`text-sm font-semibold ${ev.max_impact >= 8 ? "text-rose-400" : ev.max_impact >= 6 ? "text-amber-400" : "text-slate-300"}`}>
                    {ev.max_impact.toFixed(1)}
                  </div>
                  <div className="text-[11px] text-slate-600">impact</div>
                </div>
              </div>
            ))}
            {top.length === 0 && <div className="px-5 py-6 text-sm text-slate-500">No active events yet.</div>}
          </div>
        </div>

        <div className="card">
          <div className="card-title">Index movers (Module A)</div>
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-surface-700/40 text-left text-xs uppercase tracking-wider text-slate-500">
                <th className="px-5 py-2 font-medium">Ticker</th>
                <th className="px-3 py-2 font-medium">Weight</th>
                <th className="px-3 py-2 font-medium">vs anchor</th>
                <th className="px-5 py-2 font-medium">Sentiment</th>
              </tr>
            </thead>
            <tbody>
              {movers.map((w) => (
                <tr key={w.ticker} className="border-b border-surface-800/60 last:border-0">
                  <td className="px-5 py-2.5 font-medium text-slate-200">{w.ticker}</td>
                  <td className="px-3 py-2.5 tabular-nums text-slate-300">{(w.weight * 100).toFixed(2)}%</td>
                  <td className={`px-3 py-2.5 tabular-nums ${w.delta >= 0 ? "text-emerald-400" : "text-rose-400"}`}>
                    {w.delta >= 0 ? "+" : ""}{(w.delta * 100).toFixed(2)}%
                  </td>
                  <td className={`px-5 py-2.5 tabular-nums ${w.sentiment > 0.15 ? "text-emerald-400" : w.sentiment < -0.15 ? "text-rose-400" : "text-slate-400"}`}>
                    {fmtSent(w.sentiment)}
                  </td>
                </tr>
              ))}
              {movers.length === 0 && (
                <tr><td className="px-5 py-6 text-sm text-slate-500" colSpan={4}>Rebalancer has not ticked yet.</td></tr>
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
