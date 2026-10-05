import { useQuery } from "@tanstack/react-query";
import ReactECharts from "echarts-for-react";
import { api } from "../api/client";
import { baseOption, CHART_PALETTE, fmtSent, sentimentColor } from "../lib/format";

export default function Rebalancer() {
  const { data: snapshot } = useQuery({ queryKey: ["weights"], queryFn: api.weights, refetchInterval: 20_000 });
  const { data: history } = useQuery({ queryKey: ["weightHistory"], queryFn: () => api.weightHistory(720), refetchInterval: 60_000 });

  const weights = snapshot?.weights ?? [];
  const ticks = history?.ticks ?? [];

  const stacked = {
    ...baseOption,
    tooltip: { ...baseOption.tooltip, trigger: "axis", axisPointer: { type: "line" } },
    legend: { ...baseOption.legend, type: "scroll", bottom: 0, data: weights.map((w) => w.ticker) },
    grid: { left: 55, right: 20, top: 20, bottom: 60 },
    xAxis: {
      type: "category",
      data: ticks.map((t) => new Date(t.ts).toLocaleString([], { month: "short", day: "numeric", hour: "2-digit" })),
      axisLabel: { color: "#94a3b8", fontSize: 10 },
    },
    yAxis: { type: "value", max: 1, axisLabel: { color: "#94a3b8", formatter: (v: number) => `${(v * 100).toFixed(0)}%` }, splitLine: { lineStyle: { color: "#13203a" } } },
    series: weights.map((w, i) => ({
      name: w.ticker,
      type: "line",
      stack: "total",
      areaStyle: { opacity: 0.85 },
      emphasis: { focus: "series" },
      symbol: "none",
      lineStyle: { width: 0.5 },
      data: ticks.map((t) => t.weights[w.ticker] ?? 0),
      color: CHART_PALETTE[i % CHART_PALETTE.length],
    })),
  };

  const currentVsAnchor = {
    ...baseOption,
    grid: { left: 16, right: 16, top: 34, bottom: 8, containLabel: true },
    legend: { ...baseOption.legend, top: 0 },
    xAxis: {
      type: "category",
      data: weights.map((w) => w.ticker),
      axisTick: { show: false },
      axisLine: { lineStyle: { color: "#1b2c4d" } },
      axisLabel: { color: "#94a3b8", fontSize: 10.5, interval: 0, rotate: 40 },
    },
    yAxis: { type: "value", axisLabel: { color: "#64748b", fontSize: 11, formatter: (v: number) => `${(v * 100).toFixed(0)}%` }, splitLine: { lineStyle: { color: "#13203a" } } },
    series: [
      { name: "anchor", type: "bar", barGap: "-100%", data: weights.map((w) => w.anchor_weight), itemStyle: { color: "#334155" }, barWidth: "55%" },
      { name: "current", type: "bar", data: weights.map((w) => w.weight), itemStyle: { color: "#2dd4bf" }, barWidth: "35%" },
    ],
  };

  return (
    <div className="space-y-6">
      <header>
        <h1 className="text-xl font-semibold text-slate-100">Module A · Tactical Index Rebalancer</h1>
        <p className="mt-1 text-sm text-slate-500">
          Sentiment-driven rebalancing of a 14-name mock S&amp;P 100 index. Weights blend the
          market-cap anchor with an inverse-volatility-scaled sentiment tilt, capped at 20% per
          name with 2% daily turnover.
        </p>
      </header>

      <div className="card p-4">
        <div className="card-title px-0 pt-0">Index composition over time</div>
        <ReactECharts option={stacked} style={{ height: 380 }} notMerge />
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <div className="card p-4">
          <div className="card-title px-0 pt-0">Current weights vs market-cap anchor</div>
          <ReactECharts option={currentVsAnchor} style={{ height: 320 }} notMerge />
        </div>

        <div className="card">
          <div className="card-title">Position sheet</div>
          <div className="max-h-72 overflow-y-auto">
            <table className="w-full text-sm">
              <thead className="sticky top-0 bg-surface-900">
                <tr className="border-b border-surface-700/40 text-left text-xs uppercase tracking-wider text-slate-500">
                  <th className="px-5 py-2 font-medium">Ticker</th>
                  <th className="px-3 py-2 font-medium">Weight</th>
                  <th className="px-3 py-2 font-medium">Anchor</th>
                  <th className="px-3 py-2 font-medium">Active bet</th>
                  <th className="px-5 py-2 font-medium">Sentiment</th>
                </tr>
              </thead>
              <tbody>
                {weights.map((w) => (
                  <tr key={w.ticker} className="border-b border-surface-800/60 last:border-0">
                    <td className="px-5 py-2 font-medium text-slate-200">{w.ticker}</td>
                    <td className="px-3 py-2 tabular-nums text-slate-300">{(w.weight * 100).toFixed(2)}%</td>
                    <td className="px-3 py-2 tabular-nums text-slate-500">{(w.anchor_weight * 100).toFixed(2)}%</td>
                    <td className={`px-3 py-2 tabular-nums font-medium ${w.delta >= 0 ? "text-emerald-400" : "text-rose-400"}`}>
                      {w.delta >= 0 ? "+" : ""}{(w.delta * 100).toFixed(2)}%
                    </td>
                    <td className={`px-5 py-2 tabular-nums ${sentimentColor(w.sentiment)}`}>{fmtSent(w.sentiment)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      </div>
    </div>
  );
}
