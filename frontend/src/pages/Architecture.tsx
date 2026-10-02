export default function Architecture() {
  return (
    <div className="space-y-6">
      <header>
        <h1 className="text-xl font-semibold text-slate-100">Architecture</h1>
        <p className="mt-1 text-sm text-slate-500">
          How unstructured text becomes a structured risk signal, and how the two downstream
          modules consume it.
        </p>
      </header>

      <div className="card p-6">
        <div className="space-y-3 font-mono text-xs leading-6 text-slate-400">
          <div className="text-slate-300">INGESTION</div>
          <div>
            GDELT DOC 2.0 (live news, 15 min, keyless) &nbsp;·&nbsp; Kaggle Financial News corpus
            (vendored, labeled) &nbsp;·&nbsp; synthetic generator (demo volume + offline fallback)
          </div>
          <div className="text-accent">└─▶ normalized items (source, text, published_at)</div>

          <div className="pt-2 text-slate-300">AI/NLP RISK ENGINE</div>
          <div>entity matcher (aliases + cashtags) → FinBERT sentiment [-1..1] → event classifier
            (zero-shot NLI + lexicon) → impact = severity × conviction × corroboration [1..10]</div>
          <div className="text-accent">└─▶ signals + 24h event clusters (SQLite, WAL)</div>

          <div className="pt-2 text-slate-300">DOWNSTREAM</div>
          <div>Module A: decayed sentiment → inverse-vol tilt → weights (cap 20%, turnover 2%)</div>
          <div>Module B: event trigger (e.g. Geopolitical &gt; 7) → shock matrix → repricing →
            Monte Carlo VaR/ES</div>
          <div className="text-accent">└─▶ FastAPI on :8000, serving both the API and the React dashboard</div>
        </div>
      </div>

      <div className="grid gap-4 md:grid-cols-2">
        <div className="card p-5">
          <div className="card-title px-0 pt-0">Design principles</div>
          <ul className="list-disc space-y-2 pl-5 text-sm text-slate-400">
            <li>Keyless by default: every live integration (GDELT, yfinance) works without credentials.</li>
            <li>Explainable scores: every impact number decomposes into severity, conviction and corroboration.</li>
            <li>Degraded-but-alive: if GDELT or yfinance fail, the demo continues on cached and synthetic data.</li>
            <li>One port: the React bundle is served by the same FastAPI process that exposes the API.</li>
          </ul>
        </div>
        <div className="card p-5">
          <div className="card-title px-0 pt-0">Tech stack</div>
          <ul className="list-disc space-y-2 pl-5 text-sm text-slate-400">
            <li>Engine: Python 3.11, FastAPI, SQLAlchemy + SQLite (WAL), APScheduler</li>
            <li>Models: ProsusAI/finbert, distilbert-base-uncased-mnli (zero-shot), fine-tunable via the shipped training script</li>
            <li>Frontend: React 18, TypeScript, Tailwind, ECharts, TanStack Query</li>
            <li>Delivery: Docker multi-stage build (Node build stage, Python runtime stage)</li>
          </ul>
        </div>
      </div>
    </div>
  );
}
