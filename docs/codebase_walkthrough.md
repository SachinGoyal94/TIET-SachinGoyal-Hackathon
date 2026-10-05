# Codebase Walkthrough & Self-Assessment — Read Me First

This document maps every component of the platform to what it does, why it
exists, what has been measured, and where the remaining weaknesses are. It
exists so the team can find improvements systematically rather than by
accident. Read it alongside docs/architecture.png.

## 1. The stack at a glance

~5,000 lines of Python across 45 modules, 3 Kaggle GPU/CPU kernels, a React
dashboard (TypeScript), and 47 tests. No LLM API keys anywhere. One Docker
command runs everything.

## 2. Data flow (end to end)

```
SOURCES                ENGINE                     MODULES
------                 ------                     --------
GDELT (15min)  ----+   entities (alias/cashtag)   Module A:
FNSPID 78k     ----+-> FinBERT sentiment  ----+->  z-scored tilt on
Kaggle tweets  ----+   Qwen3-4B per-entity      |    cap-weight anchor
synthetic (demo)   |   event classifier        |    caps/bands/turnover
                   |   impact formula          |
                   |   event clustering        Module B:
                   +--------------------------->  scenario shocks,
                                                  credit migration,
                                                  Vasicek PD, CET1 flow
OUTPUTS: REST API (14 endpoints) + React dashboard + SQLite (WAL)
```

## 3. Component-by-component

### 3.1 Ingestion (ingest/, scheduler.py)

| File | Role | Measured/state |
|---|---|---|
| gdelt.py | Live news poll (15 min, keyless) | working, graceful degradation |
| seed.py | Corpus loaders (labeled eval set) | working |
| synthetic.py | Demo/offline generator | working |
| service.py | Dedupe, NLP dispatch, event clustering | 78k+ headlines processed |

Weakness: GDELT historical backfill was abandoned (cloud-IP throttling);
the FNSPID Kaggle dataset replaced it. If live GDELT throttles again, the
fallback is the synthetic feed - degraded but alive.

### 3.2 NLP pipeline (nlp/)

| File | Role | Measured |
|---|---|---|
| sentiment.py | FinBERT scorer | 89.4% held-out (best of 5) |
| entity_sentiment.py | Qwen3-4B per-entity JSON | 72.4% vs 59.8% shared-score (SEntFiN) |
| events.py | LLM-led hybrid event classifier | pipeline baseline 59.2% vs hand-gold |
| impact.py | Composite severity | IC 0.098 with VIX factor |
| pipeline.py | Orchestrator: LLM-primary, FinBERT conviction | live-verified |

Known trade-off: the LLM path costs ~5s/headline. It runs on the live path
only; backfill uses the lexicon/NLI fallback. If throughput ever matters,
the distilled SetFit model (58.2%, 20ms) is a drop-in replacement.

### 3.3 Module A: Tactical rebalancer (modules/rebalancer.py, rebalance_service.py)

Signal chain: impact-weighted daily sentiment -> 60d z-score (70% level +
30% change) -> linear tilt on cap-weight anchor (inverse-vol scaled,
clipped 0.5-2.0x) -> sector neutrality band -> 20% cap (water-filling
solver) -> no-trade band -> 2% turnover cap.

Backtested walk-forward, look-ahead-free, 352 days of the 2022 bear:
- vs cap-weight: +0.9pt net of 10bps costs
- vol-targeted variant (20%): -10.4% vs -22.6% benchmark
- per-ticker attribution: NVDA +148bps, MSFT -150bps

Weaknesses (documented, deliberate):
- trailed equal-weight in the bear (small-cap skew)
- anchor uses current market caps (documented approximation)
- one 2022 window only; no multi-regime evidence yet

### 3.4 Module B: Stress testing (modules/stress.py, credit.py, scenarios.py)

Signal chain: event (label, impact) -> VIX regime + spread regime factors ->
scenario shock vector (DFAST/EBA + 5 historical replays) -> instrument
repricing (duration/convexity, spread duration, linear greeks) -> credit
migration (S&P-style matrix, Vasicek PD) -> Monte Carlo VaR/ES -> CET1 flow
-> reverse stress (bisection for breach multiple).

Verified by functional battery: bond repricing matches duration+convexity
exactly; Vasicek monotonic; reverse stress boundary correct (COVID breaches
at 0.25x, was misreported at 0.51x before the floor fix); swap DV01s
corrected to notional x duration x 0.0001.

### 3.5 Serving (main.py, api/routes.py, scheduler.py, dashboard/)

14 REST endpoints, React dashboard (5 pages), APScheduler (3 jobs),
SQLite WAL. Keyless end to end. Tests: 47 passing.

## 4. Evidence pack (docs/evidence/, 14 artifacts)

| Claim | Number | Artifact |
|---|---|---|
| Sentiment accuracy | 89.4% | bake-off, 5 models |
| Per-entity attribution | 72.4% vs 59.8% | SEntFiN human labels |
| Directional hit rate (strong) | 55.6% | real prices, 3,605 events |
| Credit-event reaction | +25.2bps, t=3.01 | 850 events |
| Impact validity | IC 0.098 | 19,872 events |
| Event classifier baseline | 59.2% vs gold | 380 hand-labeled |
| Loan-book calibration | real LC data | 1.35M loans |
| Rebalancer vs benchmark | +0.9pt net | 352-day walk-forward |
| Vol management | -10.4% @ 20.7% vol | same window |

## 5. Where improvements remain (ranked by expected value)

1. Intraday impact windows - the biggest scientific upgrade; needs
   accumulation of live minute-bar data (weeks).
2. Embedding-based event clustering - rejected by pre-measurement
   (0.3% mis-split rate) but revisit if the corpus grows 10x.
3. SetFit event classifier - staged locally, needs a stable run
   (Kaggle OOM killed it twice).
4. Multi-regime backtest evidence - extend past 2022 into 2023-24.
5. Frontend: evidence numbers on the Overview page; spread/VIX regime
   badges on the stress page.

## 6. Non-obvious operational notes

- Kaggle CLI-created datasets sometimes fail to mount in kernels;
  web-UI uploads always mounted. Prefer manual uploads for kernel inputs.
- The bakeoff-round-2 kernel silently kept old code after a push
  (slug/title conflict); always verify the pulled source matches.
- SetFit contrastive pairing grows quadratically - keep per_class <= 25
  on CPU.
- The event study's sector adjustment removes the index factor, so
  market-wide events (geopolitical) look small per-name; their channel
  is the index, covered by Module B scenarios instead.
