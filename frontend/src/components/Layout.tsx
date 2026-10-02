import { NavLink, useLocation } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import {
  Activity,
  GitCompareArrows,
  Landmark,
  Network,
  ShieldAlert,
} from "lucide-react";
import { api } from "../api/client";

const NAV = [
  { to: "/", label: "Overview", icon: Landmark },
  { to: "/risk-engine", label: "Risk Engine", icon: Network },
  { to: "/rebalancer", label: "Index Rebalancer", icon: GitCompareArrows },
  { to: "/stress-testing", label: "Stress Testing", icon: ShieldAlert },
  { to: "/architecture", label: "Architecture", icon: Activity },
];

export default function Layout({ children }: { children: React.ReactNode }) {
  const location = useLocation();
  const { data: health } = useQuery({
    queryKey: ["health"],
    queryFn: api.health,
    refetchInterval: 30_000,
  });

  return (
    <div className="flex h-full">
      {/* Sidebar */}
      <aside className="flex w-60 shrink-0 flex-col border-r border-surface-700/60 bg-surface-900">
        <div className="px-5 py-5">
          <div className="text-sm font-semibold tracking-wide text-slate-100">
            Risk Intelligence
          </div>
          <div className="mt-0.5 text-xs text-slate-500">
            S&amp;P Global &amp; Crisil Hackathon
          </div>
        </div>
        <nav className="mt-2 flex-1 space-y-1 px-3">
          {NAV.map(({ to, label, icon: Icon }) => {
            const active =
              to === "/" ? location.pathname === "/" : location.pathname.startsWith(to);
            return (
              <NavLink
                key={to}
                to={to}
                className={`flex items-center gap-3 rounded-lg px-3 py-2 text-sm transition-colors ${
                  active
                    ? "bg-surface-800 font-medium text-accent"
                    : "text-slate-400 hover:bg-surface-850 hover:text-slate-200"
                }`}
              >
                <Icon size={17} strokeWidth={active ? 2.2 : 1.8} />
                {label}
              </NavLink>
            );
          })}
        </nav>
        <div className="border-t border-surface-700/60 px-5 py-4">
          <div className="flex items-center gap-2 text-xs">
            <span
              className={`h-2 w-2 rounded-full ${
                health?.ready ? "bg-emerald-400" : "bg-amber-400 animate-pulse"
              }`}
            />
            <span className="text-slate-400">
              Engine {health?.status ?? "connecting…"}
            </span>
          </div>
          <div className="mt-1 text-[11px] text-slate-600">v{health?.version ?? "—"}</div>
        </div>
      </aside>

      {/* Main content */}
      <main className="flex-1 overflow-y-auto bg-surface-950">
        <div className="mx-auto max-w-7xl px-6 py-6">{children}</div>
      </main>
    </div>
  );
}
