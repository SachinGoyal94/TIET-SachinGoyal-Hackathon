"""Module B: event-driven stress testing on a synthetic wholesale banking book.

A high-impact event selects a shock vector from the matrix below (scaled by
the impact band). Positions reprice with simple, documented instruments
math: duration/convexity for bonds, spread duration for loans, linear greeks
for derivatives. A Monte Carlo overlay perturbs the shock vector to produce
a P&L distribution with VaR/ES instead of a single point estimate.
"""

from __future__ import annotations

import random

# base shocks at the high band (impact >= 8)
SHOCK_MATRIX: dict[str, dict] = {
    "Geopolitical":       {"equity_pct": -0.10, "rates_bps": 200, "spread_bps": 150, "fx_pct": 0.02},
    "Credit Event":       {"equity_pct": -0.08, "rates_bps": -50, "spread_bps": 250, "fx_pct": 0.0},
    "Macroeconomic":      {"equity_pct": -0.06, "rates_bps": 100, "spread_bps": 100, "fx_pct": 0.0},
    "Merger/Acquisition": {"equity_pct": -0.02, "rates_bps": 0,   "spread_bps": 25,  "fx_pct": 0.0},
    "Product Launch":     {"equity_pct": 0.01,  "rates_bps": 0,   "spread_bps": 0,   "fx_pct": 0.0},
    "Other":              {"equity_pct": -0.03, "rates_bps": 0,   "spread_bps": 50,  "fx_pct": 0.0},
}

DEFAULT_SHOCKS = SHOCK_MATRIX["Other"]
LOAN_SPREAD_DURATION = 4.0
MC_DRAWS = 1000
MC_DISPERSION = 0.25


def band_multiplier(impact: float) -> float:
    if impact >= 8:
        return 1.0
    if impact >= 6:
        return 0.7
    if impact >= 4:
        return 0.4
    return 0.15


def shocks_for(event_label: str, impact: float) -> dict:
    base = SHOCK_MATRIX.get(event_label, DEFAULT_SHOCKS)
    scale = band_multiplier(impact)
    return {
        "equity_pct": round(base["equity_pct"] * scale, 5),
        "rates_bps": round(base["rates_bps"] * scale, 1),
        "spread_bps": round(base["spread_bps"] * scale, 1),
        "fx_pct": round(base["fx_pct"] * scale, 5),
        "band_scale": scale,
    }


def _price_position(pos: dict, shocks: dict) -> float:
    """P&L in currency units for one position under the shock vector."""
    notional = float(pos.get("notional") or pos.get("value") or 0.0)
    kind = pos["asset_class"]

    if kind == "equity":
        return notional * shocks["equity_pct"]

    if kind == "bond":
        dy = shocks["rates_bps"] / 1e4
        if pos.get("sub_type") == "corporate":
            dy += shocks["spread_bps"] / 1e4
        duration = pos.get("duration", 0.0)
        convexity = pos.get("convexity", 0.0)
        dp = -duration * dy + 0.5 * convexity * dy * dy
        return notional * dp

    if kind == "loan":
        # loans reprice with spread duration; widening is a valuation hit
        return -notional * (shocks["spread_bps"] / 1e4) * LOAN_SPREAD_DURATION

    if kind == "derivative":
        sub = pos.get("sub_type")
        if sub == "interest_rate_swap":
            sign = 1.0 if pos.get("position") == "payer" else -1.0
            return sign * pos["dv01_bps"] * shocks["rates_bps"]
        if sub == "equity_option":
            return pos["delta"] * notional * shocks["equity_pct"]
        if sub == "fx_forward":
            return pos["direction"] * notional * shocks["fx_pct"]
    return 0.0


def run_stress(portfolio: dict, event_label: str, impact: float) -> dict:
    """Deterministic shock scenario plus a Monte Carlo P&L distribution."""
    positions = portfolio["positions"]
    shocks = shocks_for(event_label, impact)

    value_before = 0.0
    value_after = 0.0
    by_class: dict[str, dict] = {}
    rows: list[dict] = []

    for pos in positions:
        notional = float(pos.get("notional") or pos.get("value") or 0.0)
        pnl = _price_position(pos, shocks)
        # loans/derivatives enter the book at market value ~ notional for
        # reporting, but bonds/equities carry their own value field
        base_value = float(pos.get("value", notional))
        value_before += base_value
        value_after += base_value + pnl

        cls = pos["asset_class"]
        agg = by_class.setdefault(cls, {"value_before": 0.0, "pnl": 0.0})
        agg["value_before"] += base_value
        agg["pnl"] += pnl

        rows.append({
            "id": pos["id"],
            "name": pos.get("name", pos["id"]),
            "asset_class": cls,
            "value_before": round(base_value, 0),
            "pnl": round(pnl, 0),
        })

    pnl = value_after - value_before
    rows.sort(key=lambda r: r["pnl"])

    mc = _monte_carlo(positions, event_label, impact)

    return {
        "event_label": event_label,
        "impact_score": impact,
        "shocks": shocks,
        "value_before": round(value_before, 0),
        "value_after": round(value_after, 0),
        "pnl": round(pnl, 0),
        "pnl_pct": round(pnl / value_before * 100, 3) if value_before else 0.0,
        "by_asset_class": {
            cls: {"value_before": round(v["value_before"], 0),
                  "pnl": round(v["pnl"], 0),
                  "pnl_pct": round(v["pnl"] / v["value_before"] * 100, 3) if v["value_before"] else 0.0}
            for cls, v in by_class.items()
        },
        "top_losers": rows[:8],
        "risk_indicators": _risk_indicators(positions),
        "monte_carlo": mc,
    }


def _monte_carlo(positions: list[dict], event_label: str, impact: float) -> dict:
    """P&L distribution from perturbed shock vectors (common + idiosyncratic noise)."""
    base = SHOCK_MATRIX.get(event_label, DEFAULT_SHOCKS)
    scale = band_multiplier(impact)
    pnls: list[float] = []
    rng = random.Random(42)
    for _ in range(MC_DRAWS):
        shocks = {}
        for key, unit in (("equity_pct", "pct"), ("rates_bps", "bps"),
                          ("spread_bps", "bps"), ("fx_pct", "pct")):
            z = rng.gauss(0, 1) * 0.7 + rng.gauss(0, 1) * 0.3
            noise = 1.0 + MC_DISPERSION * z
            shocks[key] = base[key] * scale * max(noise, 0.0)
        pnls.append(sum(_price_position(p, shocks) for p in positions))
    pnls.sort()
    n = len(pnls)
    var95 = -pnls[int(0.05 * n)]
    tail = pnls[: max(int(0.05 * n), 1)]
    return {
        "draws": n,
        "var95": round(var95, 0),
        "es95": round(-sum(tail) / len(tail), 0),
        "p5_pnl": round(pnls[int(0.05 * n)], 0),
        "median_pnl": round(pnls[n // 2], 0),
        "p95_pnl": round(pnls[int(0.95 * n) - 1], 0),
    }


def _risk_indicators(positions: list[dict]) -> dict:
    total_bond = total_notional = 0.0
    dur_weighted = spread_weighted = 0.0
    delta_exposure = 0.0
    loan_notional = loan_el = 0.0

    for pos in positions:
        notional = float(pos.get("notional") or pos.get("value") or 0.0)
        total_notional += notional
        if pos["asset_class"] == "bond":
            total_bond += notional
            dur_weighted += notional * pos.get("duration", 0.0)
            spread_weighted += notional * (LOAN_SPREAD_DURATION if pos.get("sub_type") == "corporate" else 0.0)
        if pos["asset_class"] == "loan":
            loan_notional += notional
            loan_el += notional * pos.get("pd", 0.0) * pos.get("lgd", 0.6)
        if pos["asset_class"] == "derivative" and pos.get("sub_type") == "equity_option":
            delta_exposure += pos["delta"] * notional

    return {
        "portfolio_notional": round(total_notional, 0),
        "bond_duration": round(dur_weighted / total_bond, 2) if total_bond else 0.0,
        "spread_duration": round(spread_weighted / total_notional, 2) if total_notional else 0.0,
        "equity_delta_exposure": round(delta_exposure, 0),
        "loan_expected_loss": round(loan_el, 0),
        "loan_expected_loss_pct": round(loan_el / loan_notional * 100, 3) if loan_notional else 0.0,
    }
