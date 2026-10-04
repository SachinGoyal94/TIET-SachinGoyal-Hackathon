"""Walk-forward backtest of Module A on real data.

Walks trading days forward: each day's target weights come only from signals
available at that day (news + tweets through the previous session), applied to
the NEXT session's returns. Benchmarks: cap-weight anchor and equal weight.
Costs: 10bps per unit turnover. Usage:

    python -m src.scripts.backtest_real --start 2021-09-30
"""

from __future__ import annotations

import argparse
import json
import logging
from datetime import datetime, timedelta, timezone

import numpy as np
import pandas as pd
from sqlalchemy import select

from src.engine.config import settings
from src.engine.db import Signal, get_session
from src.engine.market_data import daily_volatility, market_cap_weights
from src.engine.modules.rebalancer import (
    blend_ticker_scores,
    compute_targets,
    zscore_level_and_change,
)
from src.scripts.event_study import load_aligned_prices
from src.engine.universe import SECTOR_MEMBERS, TICKERS

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)-7s %(name)s | %(message)s")
log = logging.getLogger("backtest-real")

COST_BPS = 10.0
HISTORY_DAYS = 60


def load_daily_sentiment() -> pd.DataFrame:
    """Daily mean company sentiment per ticker (point-in-time signals)."""
    with get_session() as s:
        rows = s.execute(
            select(Signal.entity, Signal.analyzed_at, Signal.sentiment_score)
            .where(Signal.scope == "company", Signal.entity.in_(TICKERS))
        ).all()
    df = pd.DataFrame([(r[0], r[1].date(), r[2]) for r in rows],
                      columns=["ticker", "date", "sentiment"])
    df = df.drop_duplicates(subset=["ticker", "date", "sentiment"])
    daily = df.groupby(["date", "ticker"])["sentiment"].mean().reset_index()
    return daily


def stats(net_returns: list[float], gross: list[float], turnover: list[float]) -> dict:
    r = np.array(net_returns)
    if len(r) < 5:
        return {"days": len(r)}
    total = float((1 + r).prod() - 1)
    ann_ret = float((1 + total) ** (252 / len(r)) - 1)
    ann_vol = float(r.std() * np.sqrt(252))
    sharpe = float(r.mean() / r.std() * np.sqrt(252)) if r.std() > 0 else 0.0
    curve = np.cumprod(1 + r)
    peak = np.maximum.accumulate(curve)
    mdd = float(((curve - peak) / peak).min())
    gross_r = np.array(gross)
    ir = float((r - gross_r).mean() / (r - gross_r).std() * np.sqrt(252)) \
        if len(r) > 5 and (r - gross_r).std() > 0 else 0.0
    return {"days": len(r), "total_return": round(total, 4),
            "annualized_return": round(ann_ret, 4), "annualized_vol": round(ann_vol, 4),
            "sharpe_net": round(sharpe, 3), "max_drawdown": round(mdd, 4),
            "avg_daily_turnover_pct": round(float(np.mean(turnover)) * 100, 3)}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--start", type=str, default="2021-06-01",
                        help="history warm-up start (trading begins after 60d)")
    parser.add_argument("--end", type=str, default="2022-12-31")
    args = parser.parse_args()

    daily = load_daily_sentiment()
    log.info("signal days: %d", len(daily))

    levels: dict[str, list[float]] = {t: [] for t in TICKERS}
    current: dict[str, float] = {}
    prev_targets: dict[str, float] | None = None
    prev_equal: dict[str, float] | None = None

    anchor_full = market_cap_weights() or {t: 1 / len(TICKERS) for t in TICKERS}
    anchor = {**{t: 1 / len(TICKERS) for t in TICKERS if t not in anchor_full}, **anchor_full}
    total = sum(anchor.values())
    anchor = {t: w / total for t, w in anchor.items()}
    vols = daily_volatility()

    prices = load_aligned_prices(0, args.start, args.end)

    strat_rets, strat_gross, strat_turn = [], [], []
    anchor_rets, equal_rets = [], []
    dates_out = []

    all_days = sorted(daily["date"].unique())
    warmup_end = (datetime.strptime(args.start, "%Y-%m-%d").date()
                  + timedelta(days=HISTORY_DAYS + 7))

    sent_by_day = {d: dict(zip(g["ticker"], g["sentiment"]))
                   for d, g in daily.groupby("date")}

    for day in all_days:
        # update history with this day's realised sentiment (point in time)
        for t, v in sent_by_day.get(day, {}).items():
            levels.setdefault(t, []).append(v)
            current[t] = v
        hist_day = datetime.strptime(str(day), "%Y-%m-%d").date()
        if hist_day < warmup_end:
            continue
        if any(t not in prices for t in TICKERS):
            continue
        dates_p, _ = prices[TICKERS[0]]
        # the next trading session after this signal day
        nxt = [d for d in dates_p if datetime.strptime(d, "%Y-%m-%d").date() > hist_day]
        if not nxt:
            continue
        next_day = datetime.strptime(nxt[0], "%Y-%m-%d").date()
        prev_idx = [i for i, d in enumerate(dates_p)
                    if datetime.strptime(d, "%Y-%m-%d").date() < hist_day]
        if not prev_idx:
            continue
        base_idx = prev_idx[-1]
        nxt_idx = dates_p.index(nxt[0])

        sector_scores = {sec: 0.0 for sec in SECTOR_MEMBERS}
        scores = blend_ticker_scores(current, sector_scores)
        z = zscore_level_and_change(levels, current)
        targets = compute_targets(z, anchor, vols, prev_targets)
        equal = {t: 1 / len(TICKERS) for t in TICKERS}

        def port_ret(weights: dict[str, float]) -> float:
            r = 0.0
            for t, w in weights.items():
                dts, closes = prices[t][0], prices[t][1]
                i_next = dts.index(str(next_day)) if str(next_day) in dts else None
                if i_next is None or i_next <= base_idx:
                    continue
                r += w * (closes[i_next] / closes[base_idx] - 1.0)
            return r

        strat_rets.append(port_ret(targets))
        anchor_rets.append(port_ret(anchor))
        equal_rets.append(port_ret(equal))
        turnover = sum(abs(targets[t] - (prev_targets or {}).get(t, anchor.get(t, 0.0)))
                       for t in TICKERS) / 2
        strat_turn.append(turnover)
        strat_gross.append(strat_rets[-1])
        # net of costs
        strat_rets[-1] -= turnover * COST_BPS / 1e4
        prev_targets = targets
        prev_equal = equal
        dates_out.append(str(day))

    result = {
        "window": {"first_signal_day": str(all_days[0]), "trading_days": len(dates_out),
                   "first": dates_out[0] if dates_out else None,
                   "last": dates_out[-1] if dates_out else None},
        "costs": "10bps per unit turnover",
        "strategy_sentiment_tilt": stats(strat_rets, strat_gross, strat_turn),
        "cap_weighted_baseline": stats(anchor_rets, anchor_rets, [0.0] * len(anchor_rets)),
        "equal_weighted_baseline": stats(equal_rets, equal_rets, [0.0] * len(equal_rets)),
        "note": "walk-forward: each day's weights use only signals available that day; "
                "returns realized over the following session. 60d warm-up excluded.",
    }
    log.info("backtest: %s", json.dumps(result, indent=2))
    out = settings.cache_dir / "rebalance_backtest_real.json"
    out.write_text(json.dumps(result, indent=2), encoding="utf-8")
    log.info("saved to %s", out)


if __name__ == "__main__":
    main()
