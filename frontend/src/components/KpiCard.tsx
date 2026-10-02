export default function KpiCard({
  label,
  value,
  sub,
  tone = "default",
}: {
  label: string;
  value: string;
  sub?: string;
  tone?: "default" | "good" | "bad" | "warn";
}) {
  const toneClass =
    tone === "good" ? "text-emerald-400"
    : tone === "bad" ? "text-rose-400"
    : tone === "warn" ? "text-amber-400"
    : "text-slate-100";
  return (
    <div className="card p-5">
      <div className="text-xs font-medium uppercase tracking-wider text-slate-500">{label}</div>
      <div className={`mt-1.5 text-2xl font-semibold ${toneClass}`}>{value}</div>
      {sub && <div className="mt-0.5 text-xs text-slate-500">{sub}</div>}
    </div>
  );
}
