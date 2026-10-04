"""Live rebalance state: aggregates recent signals into current weights.

Signal convention matches the validated walk-forward backtest: per-ticker
sentiment is the impact-weighted daily mean (decaying 0.6 toward neutral on
no-news days), z-scored over a trailing 60-session window as 70% level +
30% change. Shared by the scheduler tick and the /api/rebalance endpoints
so the API always reports exactly what the last tick stored.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from src.engine.db import Signal, Weight, get_session
from src.engine.market_data import daily_volatility, market_cap_weights
from src.engine.modules.rebalancer import compute_targets, zscore_level_and_change
from src.engine.universe import TICKERS

Z_WINDOW_DAYS = 60
NO_NEWS_DECAY = 0.6


def _anchor() -> dict[str, float]:
    caps = market_cap_weights() or {t: 1 / len(TICKERS) for t in TICKERS}
    anchor = {**{t: 1 / len(TICKERS) for t in TICKERS if t not in caps}, **caps}
    total = sum(anchor.values())
    return {t: w / total for t, w in anchor.items()}


def current_sentiments() -> tuple[dict[str, float], dict[str, float]]:
    """(z_scores, raw_scores) per ticker.

    Raw: impact-weighted daily mean of company signals, decaying toward
    neutral on no-news days (the backtest's convention). Z: that daily series
    z-scored over the trailing window as 70% level + 30% change.
    """
    since = datetime.now(timezone.utc) - timedelta(days=Z_WINDOW_DAYS + 7)
    with get_session() as s:
        rows = s.execute(
            select(Signal.entity, Signal.analyzed_at, Signal.sentiment_score,
                   Signal.impact_score)
            .where(Signal.scope == "company", Signal.entity.in_(TICKERS),
                   Signal.analyzed_at >= since)
        ).all()

    daily = {}
    for entity, analyzed, sentiment, impact in rows:
        day = analyzed.date()
        w = max(impact, 0.5)
        t, v = daily.setdefault((day, entity), (0.0, 0.0))
        daily[(day, entity)] = (t + w, v + sentiment * w)
    daily_mean = {k: v / w for k, (w, v) in daily.items()}

    today = datetime.now(timezone.utc).date()
    levels: dict[str, list[float]] = {t: [] for t in TICKERS}
    raw: dict[str, float] = {t: 0.0 for t in TICKERS}
    for offset in range(Z_WINDOW_DAYS, -1, -1):
        day = today - timedelta(days=offset)
        for t in TICKERS:
            if (day, t) in daily_mean:
                raw[t] = daily_mean[(day, t)]
            else:
                raw[t] *= NO_NEWS_DECAY
            levels[t].append(raw[t])

    z = zscore_level_and_change(levels, raw)
    return z, raw


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
    z_scores, raw = current_sentiments()
    vols = daily_volatility()
    prev = prev_weights()
    anchor = _anchor()
    targets = compute_targets(z_scores, anchor, vols, prev)

    now = datetime.now(timezone.utc)
    with get_session() as s:
        for t, w in targets.items():
            s.add(Weight(ts=now, ticker=t, weight=w,
                         anchor_weight=anchor[t],
                         sentiment_used=raw.get(t, 0.0)))
    return targets


def weights_snapshot() -> dict:
    """Current weights plus deltas and the raw sentiment behind them."""
    with get_session() as s:
        latest_ts = s.execute(
            select(Weight.ts).order_by(Weight.ts.desc()).limit(1)
        ).scalar_one_or_none()
        if latest_ts is None:
            return {"ts": None, "weights": []}
        rows = s.execute(select(Weight).where(Weight.ts == latest_ts)).scalars().all()
    _, raw = current_sentiments()
    return {
        "ts": latest_ts,
        "weights": [
            {
                "ticker": r.ticker,
                "weight": r.weight,
                "anchor_weight": r.anchor_weight,
                "delta": round(r.weight - r.anchor_weight, 5),
                "sentiment": raw.get(r.ticker, 0.0),
            }
            for r in sorted(rows, key=lambda r: r.weight, reverse=True)
        ],
    }
