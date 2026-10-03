# Demo Video Shot-List (10 minutes)

Record at 1080p. Keep a notepad of the live engine URL (http://localhost:8000) and
pre-open the dashboard tabs. Unlisted YouTube upload, link goes in the README.

## 1. Intro (~30s)
- One-liner: "This platform turns raw news and social text into structured risk signals,
  and acts on them: rebalancing an index in real time and stress-testing a banking book
  when a crisis hits."
- Show the three required outputs on screen: sentiment, event class, impact.

## 2. Setup / Run (~30s)
- Terminal: `docker compose up --build` (or the local venv path if recording before
  Docker is set up: `pip install -r requirements.txt` + `python -m src.scripts.backfill`
  + `uvicorn src.engine.main:app`).
- Point out: zero API keys, one command, dashboard at :8000.

## 3. Risk Engine walkthrough (~2 min)
- Overview tab: KPIs and the active event feed.
- Risk Engine tab: live signal table; event-type distribution.
- Live analyzer: paste a fresh headline (prepare 3: bullish, credit event, geopolitical)
  and show the structured output landing in the feed.

## 4. Module A — Index Rebalancer (~2 min)
- Explain the mechanism in one breath: market-cap anchor + inverse-vol sentiment tilt,
  20% cap, 2% turnover.
- Show weights over time; highlight a ticker that moved against its anchor and read its
  sentiment from the table.

## 5. Module B — Stress Testing (~2.5 min)
- Portfolio composition donut; note loans/bonds/derivatives mix.
- Pick the geopolitical impact-9 event, run the stress test.
- Walk: before/after values, P&L by asset class, top losers, VaR/ES from the Monte Carlo,
  risk indicators (duration, spread duration, expected loss).
- Mention the auto-trigger rule: Geopolitical impact > 7 fires without human input.

## 6. Architecture + evidence (~1.5 min)
- Architecture tab: the flow from sources to modules.
- Evidence pack: sentiment comparison on held-out data, impact-vs-realized-moves
  correlation, strategy backtest vs cap-weighted baseline.

## 7. Close (~1 min)
- Limitations (headline-only text, illustrative shock calibration, 3-week demo window).
- What productionizing would add (streaming ingest, richer entity linking, calibrated
  impact model).
- End on: "Everything runs from one command with no API keys."

## Recording checklist
- [ ] Backfill done before recording (charts populated)
- [ ] Close unrelated tabs/apps; browser zoom 100-110%
- [ ] Prepare 3 headlines for the live analyzer
- [ ] Don't read slides; narrate the running system
