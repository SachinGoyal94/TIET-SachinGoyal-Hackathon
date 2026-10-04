"""Walk-forward backtest of Module A on real data.

Execution convention (no look-ahead): each trading day D, the decision uses
only signals published up to D's close (20:00 UTC proxy); positions are
entered at close(D) and realize close(D+1)/close(D).

Signal conditioning matches production: per-ticker sentiment is the
impact-weighted daily mean, z-scored over a trailing 60-session window
(70% level + 30% change), blended with the sector mean, tilted off the
cap-weight anchor with inverse-vol scaling, and constrained by cap,
sector band, no-trade band and turnover. Benchmarks: cap-weight anchor
and equal weight. Costs: 10bps per unit turnover. Also reports
per-ticker attribution and a 20%-vol-targeted variant.

    python -m src.scripts.backtest_real --start 2021-06-01 --end 2022-12-31
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
DECISION_CUTOFF = "20:00"  # UTC proxy for the 4pm ET close


def load_signal_rows() -> pd.DataFrame:
    """Per-signal rows: ticker, date, sentiment, impact."""
    with get_session() as s:
        rows = s.execute(
            select(Signal.entity, Signal.analyzed_at, Signal.sentiment_score,
                   Signal.impact_score)
            .where(Signal.scope == "company", Signal.entity.in_(TICKERS))
        ).all()
    df = pd.DataFrame([(r[0], r[1].date(), r[2], r[3]) for r in rows],
                      columns=["ticker", "date", "sentiment", "impact"])
    return df.drop_duplicates(subset=["ticker", "date", "sentiment", "impact"])


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
    return {"days": len(r), "total_return": round(total, 4),
            "annualized_return": round(ann_ret, 4), "annualized_vol": round(ann_vol, 4),
            "sharpe_net": round(sharpe, 3), "max_drawdown": round(mdd, 4),
            "avg_daily_turnover_pct": round(float(np.mean(turnover)) * 100, 3)}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--start", type=str, default="2021-06-01")
    parser.add_argument("--end", type=str, default="2022-12-31")
    parser.add_argument("--target-vol", type=float, default=0.20,
                        help="annualized vol target for the vol-managed variant")
    args = parser.parse_args()

    signals = load_signal_rows()
    log.info("signal rows: %d", len(signals))

    anchor_full = market_cap_weights() or {t: 1 / len(TICKERS) for t in TICKERS}
    anchor = {**{t: 1 / len(TICKERS) for t in TICKERS if t not in anchor_full}, **anchor_full}
    total = sum(anchor.values())
    anchor = {t: w / total for t, w in anchor.items()}
    vols = daily_volatility()

    prices = load_aligned_prices(0, args.start, args.end)
    calendar = prices[TICKERS[0]][0]  # trading calendar
    cal_dates = [datetime.strptime(d, "%Y-%m-%d").date() for d in calendar]
    idx_of = {d: i for i, d in enumerate(cal_dates)}

    # bucket signals by decision day: signals up to the close of day D decide
    # at close(D); later signals roll to the next session
    sig_by_day: dict[object, list] = {}
    for r in signals.itertuples():
        sig_by_day.setdefault(r.date, []).append(r)

    levels: dict[str, list[float]] = {t: [] for t in TICKERS}
    current: dict[str, float] = {t: 0.0 for t in TICKERS}
    prev_targets: dict[str, float] | None = None

    strat_rets, strat_gross, strat_turn = [], [], []
    strat_vt_rets = []
    anchor_rets, equal_rets = [], []
    dates_out = []
    attribution: dict[str, float] = {t: 0.0 for t in TICKERS}
    realized_vols: list[float] = []

    def sector_scores_now() -> dict[str, float]:
        out = {}
        for sec, members in SECTOR_MEMBERS.items():
            vals = [current[m] for m in members if m in current and current[m] != 0.0]
            out[sec] = sum(vals) / len(vals) if vals else 0.0
        return out

    warmup_end = (datetime.strptime(args.start, "%Y-%m-%d").date()
                  + timedelta(days=HISTORY_DAYS + 7))

    for i, day in enumerate(cal_dates):
        # fold today's signals into the running daily sentiment (impact-weighted)
        day_sigs = sig_by_day.get(day, [])
        for t in TICKERS:
            t_sigs = [r for r in day_sigs if r.ticker == t]
            if t_sigs:
                w_sum = sum(max(r.impact, 0.5) for r in t_sigs)
                current[t] = sum(r.sentiment * max(r.impact, 0.5) for r in t_sigs) / w_sum
            else:
                current[t] = 0.6 * current.get(t, 0.0)  # decay toward neutral
        # append to the calendar series (forward-fill on no-news days)
        for t in TICKERS:
            levels[t].append(current[t])

        if day < warmup_end or i + 1 >= len(cal_dates):
            continue

        scores = blend_ticker_scores(current, sector_scores_now())
        z = zscore_level_and_change(levels, current)
        targets = compute_targets(z, anchor, vols, prev_targets)
        equal = {t: 1 / len(TICKERS) for t in TICKERS}

        nxt = i + 1

        def session_return_w(weights: dict[str, float]) -> float:
            r = 0.0
            for t, w in weights.items():
                dts, closes = prices[t][0], prices[t][1]
                if nxt >= len(dts):
                    continue
                i_base = max((j for j, ds in enumerate(dts)
                              if datetime.strptime(ds, "%Y-%m-%d").date() <= day
                              and j < nxt), default=None)
                if i_base is None:
                    continue
                r += w * (closes[nxt] / closes[i_base] - 1.0)
            return r

        r_strat = session_return_w(targets)
        r_anchor = session_return_w(anchor)
        r_equal = session_return_w(equal)
        if all(v == 0.0 for v in (r_strat, r_anchor, r_equal)):
            continue

        turnover = sum(abs(targets[t] - (prev_targets or anchor).get(t, 0.0))
                       for t in TICKERS) / 2
        cost = turnover * COST_BPS / 1e4

        strat_rets.append(r_strat - cost)
        strat_gross.append(r_strat)
        strat_turn.append(turnover)
        anchor_rets.append(r_anchor)
        equal_rets.append(r_equal)
        for t in TICKERS:
            dts, closes = prices[t][0], prices[t][1]
            if nxt < len(dts):
                i_base = max((j for j, ds in enumerate(dts)
                              if datetime.strptime(ds, "%Y-%m-%d").date() <= day
                              and j < nxt), default=None)
                if i_base is not None:
                    tr = closes[nxt] / closes[i_base] - 1.0
                    attribution[t] += ((targets[t] - anchor[t]) * tr)

        # vol-managed variant: scale last-20d strategy vol to the target
        if len(strat_gross) >= 20:
            recent = np.array(strat_gross[-20:])
            realized = float(recent.std() * np.sqrt(252))
            realized_vols.append(realized)
            scale = min(1.5, args.target_vol / realized) if realized > 0 else 1.0
            strat_vt_rets.append(scale * (r_strat - cost))
        else:
            strat_vt_rets.append(r_strat - cost)

        prev_targets = targets
        dates_out.append(str(day))

    def vt_stats(r):
        r = np.array(r)
        if len(r) < 5:
            return {"days": len(r)}
        total = float((1 + r).prod() - 1)
        return {"days": len(r), "total_return": round(total, 4),
                "annualized_vol": round(float(r.std() * np.sqrt(252)), 4)}

    result = {
        "window": {"trading_days": len(dates_out),
                   "first": dates_out[0] if dates_out else None,
                   "last": dates_out[-1] if dates_out else None},
        "costs": "10bps per unit turnover",
        "execution": "decision at close(D) from signals through 20:00 UTC of D; "
                     "returns close(D)->close(D+1). No look-ahead.",
        "strategy_sentiment_tilt": stats(strat_rets, strat_gross, strat_turn),
        "strategy_vol_targeted_20pct": vt_stats(strat_vt_rets),
        "cap_weighted_baseline": stats(anchor_rets, anchor_rets, [0.0] * len(anchor_rets)),
        "equal_weighted_baseline": stats(equal_rets, equal_rets, [0.0] * len(equal_rets)),
        "attribution_active_vs_anchor": {t: round(v * 1e4, 1)
                                          for t, v in sorted(attribution.items(),
                                                             key=lambda kv: kv[1])},
        "note": "walk-forward, point-in-time signals; vol-managed variant rescales "
                "20d realized vol to the 20% target (capped at 1.5x gross).",
    }
    log.info("backtest: %s", json.dumps(result, indent=2))
    out = settings.cache_dir / "rebalance_backtest_real.json"
    out.write_text(json.dumps(result, indent=2), encoding="utf-8")
    log.info("saved to %s", out)


if __name__ == "__main__":
    main()
