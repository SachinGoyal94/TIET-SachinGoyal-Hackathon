"""Module A: tactical index rebalancer.

The market-cap portfolio is the anchor; a sentiment tilt (scaled by inverse
volatility, Black-Litterman style) moves weights away from it. Constraints:
fully invested, 20% per-name cap, 2% turnover per rebalance.
"""

from __future__ import annotations

import math

from src.engine.universe import SECTOR_MEMBERS, BY_TICKER

DEFAULT_PARAMS = {
    "alpha": 0.35,        # overall sentiment tilt strength
    "beta": 1.5,          # softmax sharpness on sentiment scores
    "sector_spill": 0.3,  # weight of sector signal in the ticker score
    "max_weight": 0.20,
    "max_turnover": 0.02,
    "default_vol": 0.25,  # assumption when vol data is missing
}


def blend_ticker_scores(company_scores: dict[str, float],
                        sector_scores: dict[str, float],
                        sector_spill: float = DEFAULT_PARAMS["sector_spill"]) -> dict[str, float]:
    """Mix company sentiment with the sentiment of the ticker's sector."""
    merged: dict[str, float] = {}
    for ticker, company in company_scores.items():
        sector = sector_scores.get(BY_TICKER[ticker].sector, 0.0)
        merged[ticker] = (1 - sector_spill) * company + sector_spill * sector
    return merged


def decayed_sentiment(signals: list[tuple[float, float]], half_life_hours: float = 6.0) -> float:
    """Time-decayed mean over (age_hours, score) pairs. Empty -> 0."""
    if not signals:
        return 0.0
    num = den = 0.0
    for age, score in signals:
        w = 0.5 ** (age / half_life_hours)
        num += w * score
        den += w
    return num / den if den else 0.0


def _softmax(scores: dict[str, float], beta: float) -> dict[str, float]:
    exps = {t: math.exp(beta * s) for t, s in scores.items()}
    total = sum(exps.values()) or 1.0
    return {t: e / total for t, e in exps.items()}


def _renormalize_with_cap(weights: dict[str, float], cap: float) -> dict[str, float]:
    w = dict(weights)
    for _ in range(50):
        excess = sum(v - cap for v in w.values() if v > cap)
        if excess <= 1e-9:
            break
        w = {t: min(v, cap) for t, v in w.items()}
        free_idx = [t for t, v in w.items() if v < cap - 1e-12]
        free_total = sum(w[t] for t in free_idx)
        if not free_idx or free_total <= 0:
            break
        for t in free_idx:
            w[t] = min(cap, w[t] * (free_total + excess) / free_total)
    total = sum(w.values())
    return {t: v / total for t, v in w.items()}


def compute_targets(
    ticker_sentiments: dict[str, float],
    anchor: dict[str, float],
    vols: dict[str, float] | None,
    prev_weights: dict[str, float] | None = None,
    params: dict | None = None,
) -> dict[str, float]:
    """Target weights: cap-weight anchor blended with a vol-scaled sentiment
    tilt, then constrained by cap and turnover."""
    p = {**DEFAULT_PARAMS, **(params or {})}
    tickers = list(anchor.keys())
    n = len(tickers)

    tilted = _softmax(ticker_sentiments, p["beta"])

    inv_vol = {t: 1.0 / max((vols or {}).get(t, p["default_vol"]), 0.05) for t in tickers}
    inv_mean = sum(inv_vol.values()) / n
    vol_scale = {t: inv_vol[t] / inv_mean for t in tickers}

    # equal weight + vol-scaled deviation from equal weight, renormalized
    tilted_adj = {t: (1.0 + (tilted[t] * n - 1.0) * vol_scale[t]) / n for t in tickers}
    adj_total = sum(tilted_adj.values())
    tilted_adj = {t: v / adj_total for t, v in tilted_adj.items()}

    raw = {
        t: (1 - p["alpha"]) * anchor.get(t, 1.0 / n) + p["alpha"] * tilted_adj[t]
        for t in tickers
    }

    if prev_weights:
        prev = {t: prev_weights.get(t, 0.0) for t in tickers}
        for _ in range(20):
            raw = _renormalize_with_cap(raw, p["max_weight"])
            violated = False
            for t in tickers:
                drift = raw[t] - prev[t]
                if abs(drift) > p["max_turnover"] + 1e-9:
                    raw[t] = prev[t] + math.copysign(p["max_turnover"], drift)
                    violated = True
            if not violated:
                break
        raw = _renormalize_with_cap(raw, p["max_weight"])
    else:
        raw = _renormalize_with_cap(raw, p["max_weight"])

    return raw
