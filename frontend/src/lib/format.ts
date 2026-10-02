import { EVENT_LABELS } from "../api/types";

export const LABEL_COLORS: Record<string, string> = {
  Geopolitical: "#f43f5e",
  Macroeconomic: "#f59e0b",
  "Credit Event": "#a78bfa",
  "Merger/Acquisition": "#38bdf8",
  "Product Launch": "#10b981",
  Other: "#64748b",
};

export const CHART_PALETTE = [
  "#2dd4bf", "#38bdf8", "#a78bfa", "#f59e0b", "#f43f5e",
  "#10b981", "#e879f9", "#facc15", "#fb923c", "#60a5fa",
  "#34d399", "#c084fc", "#f472b6", "#4ade80",
];

export function labelColor(label: string): string {
  return LABEL_COLORS[label] ?? LABEL_COLORS.Other;
}

export function sentimentColor(score: number): string {
  if (score > 0.15) return "text-emerald-400";
  if (score < -0.15) return "text-rose-400";
  return "text-slate-400";
}

export function fmtMoney(v: number, digits = 0): string {
  const abs = Math.abs(v);
  const sign = v < 0 ? "-" : "";
  if (abs >= 1e9) return `${sign}$${(abs / 1e9).toFixed(2)}B`;
  if (abs >= 1e6) return `${sign}$${(abs / 1e6).toFixed(1)}M`;
  if (abs >= 1e3) return `${sign}$${(abs / 1e3).toFixed(1)}K`;
  return `${sign}$${abs.toFixed(digits)}`;
}

export function fmtPct(v: number, digits = 2): string {
  return `${v > 0 ? "+" : ""}${v.toFixed(digits)}%`;
}

export function fmtSent(score: number): string {
  return `${score > 0 ? "+" : ""}${score.toFixed(2)}`;
}

export function timeAgo(iso: string): string {
  const then = new Date(iso).getTime();
  const mins = Math.max(0, Math.round((Date.now() - then) / 60000));
  if (mins < 60) return `${mins}m ago`;
  const hours = Math.round(mins / 60);
  if (hours < 24) return `${hours}h ago`;
  return `${Math.round(hours / 24)}d ago`;
}

export function eventLabelOf(label: string): string {
  return EVENT_LABELS.includes(label as never) ? label : "Other";
}

export const baseOption = {
  backgroundColor: "transparent",
  textStyle: { color: "#94a3b8" },
  tooltip: {
    backgroundColor: "#0e1829",
    borderColor: "#1b2c4d",
    textStyle: { color: "#e2e8f0", fontSize: 12 },
  },
  legend: { textStyle: { color: "#94a3b8", fontSize: 11 } },
} as const;
