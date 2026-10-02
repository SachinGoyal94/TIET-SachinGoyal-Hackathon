"""Live rebalance state: aggregates recent signals into current weights.

Shared by the scheduler tick and the /api/rebalance endpoints so the API
always reports exactly what the last tick stored.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from src.engine.db import Signal, Weight, get_session
from src.engine.market_data import daily_volatility, market_cap_weights
from src.engine.modules.rebalancer import (
    blend_ticker_scores,
    compute_targets,
    decayed_sentiment,
)
from src.engine.universe import SECTOR_MEMBERS, TICKERS

LOOKBACK_HOURS = 48


def _anchor() -> dict[str, float]:
    caps = market_cap_weights() or {t: 1 / len(TICKERS) for t in TICKERS}
    anchor = {**{t: 1 / len(TICKERS) for t in TICKERS if t not in caps}, **caps}
    total = sum(anchor.values())
    return {t: w / total for t, w in anchor.items()}


def current_sentiments() -> tuple[dict[str, float], dict[str, float]]:
    cutoff = datetime.now(timezone.utc) - timedelta(hours=LOOKBACK_HOURS)
    company: dict[str, list[tuple[float, float]]] = {t: [] for t in TICKERS}
    sector: dict[str, list[tuple[float, float]]] = {}

    with get_session() as s:
        rows = s.execute(
            select(Signal).where(
                Signal.analyzed_at >= cutoff,
                Signal.scope.in_(["company", "sector"]),
            )
        ).scalars().all()

    now = datetime.now(timezone.utc)
    for sig in rows:
        age = (now - sig.analyzed_at).total_seconds() / 3600
        if sig.scope == "company" and sig.entity in company:
            company[sig.entity].append((age, sig.sentiment_score))
        elif sig.scope == "sector":
            sector.setdefault(sig.entity, []).append((age, sig.sentiment_score))

    company_scores = {t: decayed_sentiment(v) for t, v in company.items()}
    sector_scores = {k: decayed_sentiment(v) for k, v in sector.items()}
    return company_scores, sector_scores


def prev_weights() -> dict[str, float] | None:
    with get_session() as s:
        latest = s.execute(
            select(Weight.ts).order_by(Weight.ts.desc()).limit(1)
        ).scalar_one_or_none()
        if latest is None:
            return None
        rows = s.execute(select(Weight).where(Weight.ts == latest)).scalars().all()
        return {r.ticker: r.weight for r in rows}


def rebalance_tick() -> dict[str, float]:
    """Compute and store one rebalance snapshot. Returns the new weights."""
    company_scores, sector_scores = current_sentiments()
    scores = blend_ticker_scores(company_scores, sector_scores)
    vols = daily_volatility()
    prev = prev_weights()
    anchor = _anchor()
    targets = compute_targets(scores, anchor, vols, prev)

    now = datetime.now(timezone.utc)
    with get_session() as s:
        for t, w in targets.items():
            s.add(Weight(ts=now, ticker=t, weight=w,
                         anchor_weight=anchor[t],
                         sentiment_used=company_scores.get(t, 0.0)))
    return targets


def weights_snapshot() -> dict:
    """Current weights plus deltas and the sentiment behind them."""
    with get_session() as s:
        latest_ts = s.execute(
            select(Weight.ts).order_by(Weight.ts.desc()).limit(1)
        ).scalar_one_or_none()
        if latest_ts is None:
            return {"ts": None, "weights": []}
        rows = s.execute(select(Weight).where(Weight.ts == latest_ts)).scalars().all()
    company_scores, _ = current_sentiments()
    return {
        "ts": latest_ts,
        "weights": [
            {
                "ticker": r.ticker,
                "weight": r.weight,
                "anchor_weight": r.anchor_weight,
                "delta": round(r.weight - r.anchor_weight, 5),
                "sentiment": company_scores.get(r.ticker, 0.0),
            }
            for r in sorted(rows, key=lambda r: r.weight, reverse=True)
        ],
    }
