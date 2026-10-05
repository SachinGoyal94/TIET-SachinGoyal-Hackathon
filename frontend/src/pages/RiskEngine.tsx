import { useState } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import ReactECharts from "echarts-for-react";
import { api } from "../api/client";
import LabelPill from "../components/LabelPill";
import { baseOption, labelColor, sentimentColor, timeAgo, fmtSent } from "../lib/format";
import { EVENT_LABELS } from "../api/types";

export default function RiskEngine() {
  const [scope, setScope] = useState<string | undefined>(undefined);
  const [input, setInput] = useState("");

  const { data: signals } = useQuery({
    queryKey: ["signals", scope],
    queryFn: () => api.signals(120, scope),
    refetchInterval: 15_000,
  });
  const { data: events } = useQuery({
    queryKey: ["events", "engine"],
    queryFn: () => api.events(true, 60),
    refetchInterval: 15_000,
  });

  const analyze = useMutation({ mutationFn: api.analyze });

  const rows = signals?.signals ?? [];

  const histogram = {
    ...baseOption,
    grid: { left: 130, right: 30, top: 20, bottom: 20, containLabel: false },
    xAxis: {
      type: "value",
      minInterval: 1,
      axisLabel: { color: "#64748b", fontSize: 11 },
      splitLine: { lineStyle: { color: "#13203a" } },
    },
    yAxis: {
      type: "category",
      data: [...EVENT_LABELS].reverse(),
      axisLabel: { color: "#cbd5e1", fontSize: 12 },
      axisTick: { show: false },
      axisLine: { lineStyle: { color: "#1b2c4d" } },
    },
    series: [{
      type: "bar",
      barWidth: 14,
      data: [...EVENT_LABELS].reverse().map(
        (label) => ({
          value: (events?.events ?? []).filter((e) => e.event_label === label).length,
          itemStyle: { color: labelColor(label), borderRadius: [0, 7, 7, 0] },
        }),
      ),
      label: { show: true, position: "right", color: "#94a3b8", fontSize: 11 },
      backgroundStyle: { color: "rgba(148,163,184,0.04)" },
      showBackground: true,
    }],
  };

  const sentimentHist = {
    ...baseOption,
    grid: { left: 16, right: 16, top: 30, bottom: 20, containLabel: true },
    xAxis: {
      type: "category",
      data: ["< -0.6", "-0.6 to -0.2", "-0.2 to 0.2", "0.2 to 0.6", "> 0.6"],
      axisLabel: { color: "#94a3b8", fontSize: 10.5, interval: 0 },
      axisTick: { show: false },
      axisLine: { lineStyle: { color: "#1b2c4d" } },
      splitLine: { show: false },
    },
    yAxis: {
      type: "value",
      minInterval: 1,
      axisLabel: { color: "#64748b", fontSize: 11 },
      splitLine: { lineStyle: { color: "#13203a" } },
    },
    series: [{
      type: "bar",
      barWidth: "52%",
      itemStyle: { borderRadius: [7, 7, 0, 0] },
      label: { show: true, position: "top", color: "#94a3b8", fontSize: 11 },
      data: (() => {
        const s = rows.map((r) => r.sentiment_score);
        const buckets = [0, 0, 0, 0, 0];
        for (const v of s) {
          if (v < -0.6) buckets[0]++;
          else if (v < -0.2) buckets[1]++;
          else if (v <= 0.2) buckets[2]++;
          else if (v <= 0.6) buckets[3]++;
          else buckets[4]++;
        }
        return [
          { value: buckets[0], itemStyle: { color: "#f43f5e" } },
          { value: buckets[1], itemStyle: { color: "#fb7185" } },
          { value: buckets[2], itemStyle: { color: "#64748b" } },
          { value: buckets[3], itemStyle: { color: "#4ade80" } },
          { value: buckets[4], itemStyle: { color: "#10b981" } },
        ];
      })(),
    }],
  };

  return (
    <div className="space-y-6">
      <header>
        <h1 className="text-xl font-semibold text-slate-100">Risk Engine</h1>
        <p className="mt-1 text-sm text-slate-500">
          Structured risk signals extracted from unstructured text: sentiment, event
          classification, and impact.
        </p>
      </header>

      <div className="card p-5">
        <div className="card-title px-0 pt-0">Live analyzer</div>
        <div className="flex gap-3">
          <input
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => { if (e.key === "Enter" && input.trim().length >= 3) analyze.mutate(input); }}
            placeholder="Paste a headline, e.g. sanctions hit global trade and shipping lanes close"
            className="flex-1 rounded-lg border border-surface-700 bg-surface-850 px-4 py-2.5 text-sm text-slate-200 placeholder-slate-600 outline-none focus:border-accent/60"
          />
          <button
            disabled={input.trim().length < 3 || analyze.isPending}
            onClick={() => analyze.mutate(input)}
            className="rounded-lg bg-accent px-5 py-2.5 text-sm font-medium text-surface-950 transition-colors hover:bg-accent-dim disabled:opacity-40"
          >
            {analyze.isPending ? "Analyzing…" : "Analyze"}
          </button>
        </div>
        {analyze.isError && <p className="mt-2 text-xs text-rose-400">{(analyze.error as Error).message}</p>}
        {analyze.data && (
          <div className="mt-4 grid grid-cols-2 gap-3 rounded-lg border border-surface-700/60 bg-surface-850 p-4 md:grid-cols-4">
            <div>
              <div className="text-xs text-slate-500">Sentiment</div>
              <div className={`text-lg font-semibold ${sentimentColor(analyze.data.sentiment_score)}`}>
                {fmtSent(analyze.data.sentiment_score)}
              </div>
            </div>
            <div>
              <div className="text-xs text-slate-500">Event type</div>
              <div className="mt-1"><LabelPill label={analyze.data.event_label} /></div>
            </div>
            <div>
              <div className="text-xs text-slate-500">Impact</div>
              <div className="text-lg font-semibold text-slate-100">{analyze.data.impact_score.toFixed(1)}</div>
            </div>
            <div>
              <div className="text-xs text-slate-500">Entities / cluster</div>
              <div className="text-sm text-slate-300">
                {analyze.data.entities.length ? analyze.data.entities.join(", ") : "market-wide"}
                <span className="ml-1 text-xs text-slate-500">({analyze.data.cluster_action})</span>
              </div>
              {analyze.data.per_entity && Object.keys(analyze.data.per_entity).length > 0 && (
                <div className="mt-1 text-xs">
                  {Object.entries(analyze.data.per_entity).map(([t, v]) => (
                    <span key={t} className={`mr-2 font-medium ${v > 0.15 ? "text-emerald-400" : v < -0.15 ? "text-rose-400" : "text-slate-400"}`}>
                      {t} {v > 0 ? "+" : ""}{v.toFixed(2)}
                    </span>
                  ))}
                </div>
              )}
            </div>
          </div>
        )}
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <div className="card p-4">
          <div className="card-title px-0 pt-0">Signals by event type (active events)</div>
          {histogram && <ReactECharts option={histogram} style={{ height: 260 }} notMerge />}
        </div>
        <div className="card p-4">
          <div className="card-title px-0 pt-0">Sentiment distribution (recent signals)</div>
          <ReactECharts option={sentimentHist} style={{ height: 260 }} notMerge />
        </div>
      </div>

      <div className="card">
        <div className="card-title flex items-center justify-between">
          <span>Signal feed</span>
          <div className="flex gap-1">
            {["all", "company", "sector", "market"].map((s) => (
              <button
                key={s}
                onClick={() => setScope(s === "all" ? undefined : s)}
                className={`rounded-md px-2.5 py-1 text-xs ${scope === s || (s === "all" && !scope) ? "bg-surface-700 text-slate-100" : "text-slate-500 hover:text-slate-300"}`}
              >
                {s}
              </button>
            ))}
          </div>
        </div>
        <div className="max-h-96 overflow-y-auto">
          <table className="w-full text-sm">
            <thead className="sticky top-0 bg-surface-900">
              <tr className="border-b border-surface-700/40 text-left text-xs uppercase tracking-wider text-slate-500">
                <th className="px-5 py-2 font-medium">Entity</th>
                <th className="px-3 py-2 font-medium">Event</th>
                <th className="px-3 py-2 font-medium">Sentiment</th>
                <th className="px-3 py-2 font-medium">Impact</th>
                <th className="px-5 py-2 font-medium">When</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r) => (
                <tr key={r.id} className="border-b border-surface-800/60 last:border-0 hover:bg-surface-850/60">
                  <td className="px-5 py-2 font-medium text-slate-200">{r.entity}</td>
                  <td className="px-3 py-2"><LabelPill label={r.event_label} /></td>
                  <td className={`px-3 py-2 tabular-nums ${sentimentColor(r.sentiment_score)}`}>{fmtSent(r.sentiment_score)}</td>
                  <td className="px-3 py-2 tabular-nums text-slate-300">{r.impact_score.toFixed(1)}</td>
                  <td className="px-5 py-2 text-xs text-slate-500">{timeAgo(r.analyzed_at)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
