"""Backtest Module A: sentiment-tilted weights vs the cap-weighted anchor.

Walks the stored rebalance history (produced by the backfill) forward with
real daily closes: each tick's weights are held for one day of returns.
Reports annualized return/vol, Sharpe, and max drawdown for both the
sentiment strategy and the anchor baseline.

Usage:
    python -m src.scripts.backtest_rebalancer
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone

import numpy as np
from sqlalchemy import select

from src.engine.config import settings
from src.engine.db import Weight, get_session
from src.engine.universe import TICKERS

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)-7s %(name)s | %(message)s")
log = logging.getLogger("backtest")

TRADING_DAYS = 252


def load_closes(days: int = 120) -> dict[str, tuple[list[str], list[float]]]:
    from src.scripts.validate_impact import load_closes as _load

    return _load(days)


def index_returns(weights_by_day: list[tuple[str, dict[str, float]]],
                  closes: dict[str, tuple[list[str], list[float]]]) -> list[float]:
    """One-day portfolio returns following each weight tick."""
    rets: list[float] = []
    for i in range(len(weights_by_day) - 1):
        day, weights = weights_by_day[i]
        nxt = weights_by_day[i + 1][0]
        day_ret = 0.0
        for ticker, w in weights.items():
            if ticker not in closes:
                continue
            dates, series = closes[ticker]
            # find close on/after this tick and close on/after next tick
            idx_now = next((j for j, d in enumerate(dates)
                            if datetime.fromisoformat(d).date() >= day), None)
            idx_nxt = next((j for j, d in enumerate(dates)
                            if datetime.fromisoformat(d).date() >= nxt), None)
            if idx_now is None or idx_nxt is None or idx_nxt <= idx_now:
                continue
            day_ret += w * (series[idx_nxt] / series[idx_now] - 1.0)
        rets.append(day_ret)
    return rets


def stats(rets: list[float]) -> dict:
    r = np.array(rets)
    if len(r) < 2:
        return {"days": len(r)}
    total = float((1 + r).prod() - 1)
    ann_ret = float((1 + total) ** (TRADING_DAYS / len(r)) - 1)
    ann_vol = float(r.std() * np.sqrt(TRADING_DAYS))
    sharpe = float(r.mean() / r.std() * np.sqrt(TRADING_DAYS)) if r.std() > 0 else 0.0
    curve = np.cumprod(1 + r)
    peak = np.maximum.accumulate(curve)
    max_dd = float(((curve - peak) / peak).min())
    return {"days": len(r), "total_return": round(total, 4),
            "annualized_return": round(ann_ret, 4), "annualized_vol": round(ann_vol, 4),
            "sharpe": round(sharpe, 3), "max_drawdown": round(max_dd, 4)}


def main() -> None:
    closes = load_closes()

    with get_session() as s:
        rows = s.execute(select(Weight).order_by(Weight.ts)).scalars().all()

    by_ts: dict[datetime, dict[str, float]] = {}
    anchor_by_ts: dict[datetime, dict[str, float]] = {}
    for r in rows:
        by_ts.setdefault(r.ts, {})[r.ticker] = r.weight
        anchor_by_ts.setdefault(r.ts, {})[r.ticker] = r.anchor_weight

    # ticks are daily; align them to dates
    def dated(by_ts: dict) -> list[tuple, dict]:  # type: ignore[valid-type]
        return sorted(((ts.date(), w) for ts, w in by_ts.items()), key=lambda x: x[0])

    strat = index_returns(dated(by_ts), closes)
    anchor = index_returns(dated(anchor_by_ts), closes)

    result = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "strategy": stats(strat),
        "cap_weighted_baseline": stats(anchor),
        "note": ("short demo window over seeded history; treat as illustrative, "
                 "not as production evidence"),
    }
    log.info("backtest: %s", json.dumps(result, indent=2))

    out = settings.cache_dir / "rebalance_backtest.json"
    out.write_text(json.dumps(result, indent=2), encoding="utf-8")
    log.info("saved to %s", out)


if __name__ == "__main__":
    main()
