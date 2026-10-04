"""Module B: event-driven stress testing on a synthetic wholesale banking book.

A high-impact event selects a shock vector from the matrix below (scaled by
the impact band). Positions reprice with simple, documented instruments
math: duration/convexity for bonds, spread duration for loans, linear greeks
for derivatives. A Monte Carlo overlay perturbs the shock vector to produce
a P&L distribution with VaR/ES instead of a single point estimate.
"""

from __future__ import annotations

import random

from src.engine.modules import credit
from src.engine.modules.scenarios import SCENARIOS, get_scenario

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


def _price_position(pos: dict, shocks: dict, band_scale: float = 1.0) -> float:
    """P&L in currency units for one position under the shock vector."""
    notional = float(pos.get("notional") or pos.get("value") or 0.0)
    kind = pos["asset_class"]

    if kind == "equity":
        return notional * shocks["equity_pct"]

    if kind == "bond":
        dy = shocks["rates_bps"] / 1e4
        if pos.get("sub_type") == "corporate":
            widening = shocks["spread_bps"]
            # credit engine: expected downgrade under stress widens spreads further
            rating = pos.get("rating", "BBB")
            widening += credit.spread_widening_bps(rating, credit.expected_rating(rating))
            dy += widening / 1e4
        duration = pos.get("duration", 0.0)
        convexity = pos.get("convexity", 0.0)
        dp = -duration * dy + 0.5 * convexity * dy * dy
        return notional * dp

    if kind == "loan":
        # valuation hit via spread duration, plus a stressed provision from
        # the credit engine (Vasicek conditional PD vs the rating's base PD)
        widening = shocks["spread_bps"]
        rating = pos.get("rating", "BBB")
        widening += credit.spread_widening_bps(rating, credit.expected_rating(rating))
        valuation = -notional * (widening / 1e4) * LOAN_SPREAD_DURATION
        base_pd = float(pos.get("pd", 0.02) or 0.02)
        lgd = float(pos.get("lgd", 0.6) or 0.6)
        stressed = credit.stressed_pd(base_pd, band_scale)
        provision = -notional * max(0.0, stressed - base_pd) * lgd
        return valuation + provision

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


def spread_regime_factor(oas: float | None) -> float:
    """Credit-conditions multiplier: tight HY spreads mean compressed risk
    premia and a book positioned for calm - shocks hit harder. Wide spreads
    mean stress is already partially realized (oas in %, e.g. 3.2 = 320bps)."""
    if oas is None:
        return 1.0
    if oas < 3.5:
        return 1.10
    if oas > 6.0:
        return 0.90
    return 1.0


def run_stress(portfolio: dict, event_label: str, impact: float,
               scenario: str | None = None,
               spread_oas: float | None = None) -> dict:
    """Deterministic shock scenario plus a Monte Carlo P&L distribution.

    Either triggered by an event (event_label + impact -> shock matrix) or by
    a named scenario from the library (scenario name overrides the shocks).
    """
    positions = portfolio["positions"]
    if scenario:
        lib = get_scenario(scenario)
        shocks = {**lib["shocks"], "band_scale": 1.0}
        shocks["equity_pct"] = round(shocks["equity_pct"], 5)
    else:
        shocks = shocks_for(event_label, impact)
    band_scale = shocks.get("band_scale", 1.0)

    value_before = 0.0
    value_after = 0.0
    by_class: dict[str, dict] = {}
    rows: list[dict] = []

    for pos in positions:
        notional = float(pos.get("notional") or pos.get("value") or 0.0)
        pnl = _price_position(pos, shocks, band_scale)
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

    regime = spread_regime_factor(spread_oas)
    if regime != 1.0:
        shocks = {k: round(v * regime, 5) if isinstance(v, float) else v
                  for k, v in shocks.items()}

    mc = _monte_carlo_positions(positions, shocks)

    result = {
        "event_label": scenario or event_label,
        "impact_score": impact,
        "scenario": scenario,
        "shocks": shocks,
        "spread_oas": spread_oas,
        "spread_regime_factor": regime,
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
    if portfolio.get("capital"):
        result["capital"] = _capital_view(portfolio["capital"], result)
    return result


def _monte_carlo_positions(positions: list[dict], base_shocks: dict) -> dict:
    """MC around a named scenario's shock vector."""
    pnls: list[float] = []
    rng = random.Random(42)
    for _ in range(MC_DRAWS):
        shocks = {}
        for key in ("equity_pct", "rates_bps", "spread_bps", "fx_pct"):
            z = rng.gauss(0, 1) * 0.7 + rng.gauss(0, 1) * 0.3
            shocks[key] = base_shocks[key] * max(1.0 + MC_DISPERSION * z, 0.0)
        pnls.append(sum(_price_position(p, shocks, base_shocks.get("band_scale", 1.0))
                        for p in positions))
    return _mc_stats(pnls)


def _mc_stats(pnls: list[float]) -> dict:
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


def _capital_view(capital: dict, result: dict) -> dict:
    """Regulatory-style CET1 flow: start capital + retained earnings change.

    CET1_end = CET1_start + PPNR (annual, scaled by scenario) + total P&L;
    RWA held flat (Fed practice). Depletion in bps is the headline number.
    """
    start_cet1 = float(capital["cet1_capital"])
    rwa = float(capital["rwa"])
    ppnr = float(capital.get("annual_ppnr", 0.0)) * float(capital.get("horizon_years", 1.0))
    end_cet1 = start_cet1 + ppnr + result["pnl"]
    return {
        "cet1_start": round(start_cet1, 0),
        "ppnr": round(ppnr, 0),
        "total_losses": round(result["pnl"], 0),
        "cet1_end": round(end_cet1, 0),
        "ratio_start_pct": round(start_cet1 / rwa * 100, 2),
        "ratio_end_pct": round(max(end_cet1, 0.0) / rwa * 100, 2),
        "depletion_bps": round((start_cet1 - end_cet1) / rwa * 10000, 0),
        "breach": end_cet1 / rwa < capital.get("min_ratio", 0.07),
    }


def reverse_stress(portfolio: dict, scenario: str, lo: float = 0.0,
                   hi: float = 8.0, tol: float = 0.01) -> dict:
    """Solve for the shock multiplier at which CET1 breaches its minimum.

    Binary search over a scalar scaling of the scenario's shocks; returns the
    breach multiple and the CET1 ratio there.
    """
    capital = portfolio.get("capital")
    positions = portfolio["positions"]
    if not capital:
        raise ValueError("portfolio has no capital block")

    def breach_at(scale: float) -> tuple[bool, float]:
        lib = get_scenario(scenario)
        shocks = {k: v * scale for k, v in lib["shocks"].items()}
        pnl = sum(_price_position(p, shocks, 1.0) for p in positions)
        end = float(capital["cet1_capital"]) + float(capital.get("annual_ppnr", 0.0)) + pnl
        ratio = end / float(capital["rwa"])
        return ratio < capital.get("min_ratio", 0.07), ratio

    if not breach_at(hi)[0]:
        return {"scenario": scenario, "breach_multiple": None,
                "note": "scenario does not breach even at %.1fx" % hi}
    while hi - lo > tol:
        mid = (lo + hi) / 2
        if breach_at(mid)[0]:
            hi = mid
        else:
            lo = mid
    breached, ratio = breach_at(hi)
    return {"scenario": scenario, "breach_multiple": round(hi, 2),
            "cet1_ratio_at_breach_pct": round(ratio * 100, 2)}


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
