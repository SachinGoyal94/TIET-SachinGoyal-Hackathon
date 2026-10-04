"""Module A: tactical index rebalancer.

The market-cap portfolio is the anchor; a linear sentiment tilt moves weights
away from it. Signal conditioning per the sentiment-strategy literature:
z-scored level plus an EWMA change term (daily sentiment decays in 1-2 days,
so raw levels are noisy), sector deviations constrained, and a no-trade band
so small drifts don't consume alpha in costs.
"""

from __future__ import annotations

import math

from src.engine.universe import BY_TICKER

DEFAULT_PARAMS = {
    "k": 0.4,              # tilt strength on the z-score
    "tilt_min": 0.5,       # per-name multiplier floor (w = anchor * clip(...))
    "tilt_max": 2.0,       # per-name multiplier cap
    "level_weight": 0.7,   # blend of z-level vs z-change
    "sector_band": 0.03,   # max sector deviation from benchmark weight
    "max_weight": 0.20,
    "no_trade_band": 0.005,
    "max_turnover": 0.02,
    "default_vol": 0.25,   # assumption when vol data is missing
}


def blend_ticker_scores(company_scores: dict[str, float],
                        sector_scores: dict[str, float],
                        sector_spill: float = 0.3) -> dict[str, float]:
    """Mix company sentiment with the sentiment of the ticker's sector."""
    merged: dict[str, float] = {}
    for ticker, company in company_scores.items():
        sector = sector_scores.get(BY_TICKER[ticker].sector, 0.0)
        merged[ticker] = (1 - sector_spill) * company + sector_spill * sector
    return merged


def zscore_level_and_change(levels: dict[str, list[float]],
                            current: dict[str, float],
                            level_weight: float = DEFAULT_PARAMS["level_weight"]) -> dict[str, float]:
    """Blended signal per ticker: z-score of the 60-day level plus the
    z-score of the recent change (current minus 3-day mean)."""
    signal: dict[str, float] = {}
    for ticker, hist in levels.items():
        if len(hist) < 10:
            signal[ticker] = 0.0
            continue
        recent = hist[-60:]
        mean = sum(recent) / len(recent)
        var = sum((v - mean) ** 2 for v in recent) / max(len(recent) - 1, 1)
        std = math.sqrt(var) or 1e-9
        z_level = (current.get(ticker, mean) - mean) / std

        short = recent[-3:]
        short_mean = sum(short) / len(short)
        z_change = (current.get(ticker, short_mean) - short_mean) / (std or 1e-9)
        signal[ticker] = level_weight * z_level + (1 - level_weight) * z_change
    return signal


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


def _sector_neutralize(weights: dict[str, float], anchor: dict[str, float],
                       band: float, sector_map: dict[str, str]) -> dict[str, float]:
    """Cap each sector's total deviation from benchmark at +/- band."""
    sector_w: dict[str, float] = {}
    sector_a: dict[str, float] = {}
    for t, w in weights.items():
        sec = sector_map.get(t, "Other")
        sector_w[sec] = sector_w.get(sec, 0.0) + w
        sector_a[sec] = sector_a.get(sec, 0.0) + anchor.get(t, 0.0)
    adjustments: dict[str, float] = {}
    for sec in sector_w:
        dev = sector_w[sec] - sector_a.get(sec, 0.0)
        if abs(dev) > band:
            adjustments[sec] = dev - band * (1 if dev > 0 else -1)
    if not adjustments:
        return weights
    out = dict(weights)
    for t, w in out.items():
        sec = sector_map.get(t, "Other")
        adj = adjustments.get(sec, 0.0)
        if adj:
            out[t] = max(0.0, w - adj * (w / max(sector_w[sec], 1e-9)))
    return _renormalize_with_cap(out, 1.0)


def compute_targets(
    ticker_sentiments: dict[str, float],
    anchor: dict[str, float],
    vols: dict[str, float] | None,
    prev_weights: dict[str, float] | None = None,
    params: dict | None = None,
    sector_map: dict[str, str] | None = None,
) -> dict[str, float]:
    """Target weights: cap-weight anchor times a clipped linear sentiment
    tilt (inverse-vol scaled), sector-neutralized, then constrained by cap,
    no-trade band and turnover."""
    p = {**DEFAULT_PARAMS, **(params or {})}
    tickers = list(anchor.keys())
    if sector_map is None:
        sector_map = {t: BY_TICKER[t].sector for t in tickers if t in BY_TICKER}

    inv_vol = {t: 1.0 / max((vols or {}).get(t, p["default_vol"]), 0.05) for t in tickers}
    inv_mean = sum(inv_vol.values()) / len(tickers)
    vol_scale = {t: inv_vol[t] / inv_mean for t in tickers}

    raw = {}
    for t in tickers:
        anchor_w = anchor.get(t, 1.0 / len(tickers))
        z = ticker_sentiments.get(t, 0.0)
        tilt = 1.0 + p["k"] * z * vol_scale[t]
        tilt = min(max(tilt, p["tilt_min"]), p["tilt_max"])
        raw[t] = anchor_w * tilt
    raw = _renormalize_with_cap(raw, p["max_weight"])
    if sector_map:
        raw = _sector_neutralize(raw, anchor, p["sector_band"], sector_map)

    if prev_weights:
        prev = {t: prev_weights.get(t, 0.0) for t in tickers}
        for _ in range(20):
            # no-trade band: ignore moves below the threshold
            for t in tickers:
                if abs(raw[t] - prev[t]) < p["no_trade_band"]:
                    raw[t] = prev[t]
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

    return raw
