import { useQuery } from "@tanstack/react-query";
import { api } from "../api/client";

export default function Overview() {
  const { data: health, isError } = useQuery({
    queryKey: ["health"],
    queryFn: api.health,
  });

  return (
    <div className="space-y-6">
      <header>
        <h1 className="text-xl font-semibold text-slate-100">Overview</h1>
        <p className="mt-1 text-sm text-slate-500">
          Live risk signals from unstructured news &amp; social text, feeding a tactical
          index rebalancer and a strategic stress-testing engine.
        </p>
      </header>

      <div className="card p-5">
        <div className="card-title px-0 pt-0">Engine status</div>
        {isError ? (
          <p className="text-sm text-risk-high">
            Cannot reach the engine — is it running on port 8000?
          </p>
        ) : (
          <pre className="overflow-x-auto rounded-lg bg-surface-850 p-4 text-xs text-slate-300">
            {JSON.stringify(health ?? "loading…", null, 2)}
          </pre>
        )}
      </div>
    </div>
  );
}
