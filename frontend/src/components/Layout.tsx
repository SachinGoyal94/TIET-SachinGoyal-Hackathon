import { NavLink, useLocation } from "react-router-dom";
import {
  Activity,
  GitCompareArrows,
  Landmark,
  Network,
  ShieldAlert,
} from "lucide-react";
import { useQuery } from "@tanstack/react-query";
import { api } from "../api/client";

const NAV = [
  { to: "/", label: "Overview", icon: Landmark },
  { to: "/risk-engine", label: "Risk Engine", icon: Network },
  { to: "/rebalancer", label: "Index Rebalancer", icon: GitCompareArrows },
  { to: "/stress-testing", label: "Stress Testing", icon: ShieldAlert },
  { to: "/architecture", label: "Architecture", icon: Activity },
];

function TickerTape() {
  const { data: events } = useQuery({
    queryKey: ["events", "tape"],
    queryFn: () => api.events(true, 12),
    refetchInterval: 30_000,
  });
  const items = events?.events ?? [];
  if (items.length === 0) return null;
  const doubled = [...items, ...items];

  return (
    <div className="relative h-7 overflow-hidden border-b border-surface-700/30 bg-surface-950">
      <div className="flex h-full animate-ticker-scroll items-center">
        {doubled.map((ev, i) => (
          <div key={`${ev.id}-${i}`} className="ticker-item">
            <span
              className="h-1.5 w-1.5 rounded-full"
              style={{ backgroundColor: ev.max_impact >= 8 ? "#ff4757" : ev.max_impact >= 6 ? "#ffa502" : "#2ed573" }}
            />
            <span className="font-mono text-[10px] text-slate-500">{ev.event_label.slice(0, 4).toUpperCase()}</span>
            <span className="max-w-48 truncate font-mono text-[10px] text-slate-400">{ev.headline}</span>
            <span className={`font-mono text-[10px] font-semibold ${ev.max_impact >= 8 ? "text-rose-400" : ev.max_impact >= 6 ? "text-amber-400" : "text-slate-500"}`}>
              {ev.max_impact.toFixed(1)}
            </span>
            <span className="text-surface-600">│</span>
          </div>
        ))}
      </div>
    </div>
  );
}

export default function Layout({ children }: { children: React.ReactNode }) {
  const location = useLocation();
  const { data: health } = useQuery({
    queryKey: ["health"],
    queryFn: api.health,
    refetchInterval: 30_000,
  });
  const { data: stats } = useQuery({
    queryKey: ["stats"],
    queryFn: api.stats,
    refetchInterval: 15_000,
  });

  const ready = health?.ready;

  return (
    <div className="flex h-full flex-col">
      {/* Top bar */}
      <header className="flex h-11 items-center justify-between border-b border-surface-700/30 bg-surface-900 px-4">
        <div className="flex items-center gap-3">
          <Landmark size={16} className="text-accent" />
          <span className="text-[13px] font-bold tracking-tight text-slate-100">Risk Intelligence</span>
          <span className="rounded border border-surface-600/50 px-1.5 py-px font-mono text-[9px] text-slate-500">
            S&amp;P × CRISIL
          </span>
        </div>
        <div className="flex items-center gap-4">
          {stats && (
            <div className="hidden items-center gap-4 font-mono text-[10px] text-slate-500 md:flex">
              <span>
                <span className="text-slate-600">ARTICLES </span>
                <span className="text-slate-300">{stats.articles.toLocaleString()}</span>
              </span>
              <span>
                <span className="text-slate-600">EVENTS </span>
                <span className="text-slate-300">{stats.active_events}</span>
              </span>
              <span>
                <span className="text-slate-600">SIGNALS </span>
                <span className="text-slate-300">{stats.signals.toLocaleString()}</span>
              </span>
            </div>
          )}
          <div className="flex items-center gap-1.5">
            <span className={`live-dot ${ready ? "bg-emerald-400 animate-pulse" : "bg-amber-400"}`} />
            <span className={`font-mono text-[10px] ${ready ? "text-emerald-400" : "text-amber-400"}`}>
              {ready ? "LIVE" : "INIT"}
            </span>
          </div>
        </div>
      </header>

      {/* Ticker tape */}
      <TickerTape />

      <div className="flex min-h-0 flex-1">
        {/* Sidebar */}
        <aside className="flex w-52 shrink-0 flex-col border-r border-surface-700/30 bg-surface-900/50">
          <nav className="mt-3 flex-1 space-y-0.5 px-2">
            {NAV.map(({ to, label, icon: Icon }) => {
              const active = to === "/" ? location.pathname === "/" : location.pathname.startsWith(to);
              return (
                <NavLink
                  key={to}
                  to={to}
                  className={`group flex items-center gap-2.5 rounded-md px-3 py-[7px] text-[13px] font-medium transition-all duration-150 ${
                    active
                      ? "bg-surface-800 text-accent shadow-glow"
                      : "text-slate-500 hover:bg-surface-850 hover:text-slate-300"
                  }`}
                >
                  <Icon size={15} strokeWidth={active ? 2.2 : 1.7} className={active ? "text-accent" : "text-slate-600 group-hover:text-slate-400"} />
                  {label}
                  {active && <span className="ml-auto h-3 w-0.5 rounded-full bg-accent" />}
                </NavLink>
              );
            })}
          </nav>
          <div className="border-t border-surface-700/30 px-4 py-3">
            <div className="flex items-center gap-2">
              {health?.components.rebalancer_module && (
                <span className="pill bg-gain/10 text-gain">MOD-A</span>
              )}
              {health?.components.stress_testing_module && (
                <span className="pill bg-gain/10 text-gain">MOD-B</span>
              )}
            </div>
            <div className="mt-2 font-mono text-[9px] text-slate-700">v{health?.version ?? "0.0.0"}</div>
          </div>
        </aside>

        {/* Main */}
        <main className="min-h-0 flex-1 overflow-y-auto bg-surface-950">
          <div className="mx-auto max-w-7xl px-5 py-5">{children}</div>
        </main>
      </div>
    </div>
  );
}
