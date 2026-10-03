"""Credit risk engine: rating migration, stressed PD, and spread mapping.

Sources of record:
- Transition matrix: approximate long-run global one-year averages from
  S&P's "Default, Transition, and Recovery: 2024 Annual Global Corporate
  Default and Rating Transition Study" (spglobal.com/ratings, free).
- Stressed PD: Basel IRB Vasicek/ASRF conditional PD with the supervisory
  asset-correlation function.
- LGD: Basel Foundation IRB anchors (45% senior unsecured, 75% subordinated).
- Spreads by rating: Damodaran's default-spread table (pages.stern.nyu.edu).
"""

from __future__ import annotations

import math

# rating order must be descending credit quality
RATING_ORDER = ["AAA", "AA", "A", "BBB", "BB", "B", "CCC", "D"]

# long-run one-year transition matrix (rows sum to 1; NR folded into stay)
TRANSITION: dict[str, dict[str, float]] = {
    "AAA": {"AAA": 0.900, "AA": 0.080, "A": 0.010, "BBB": 0.002, "BB": 0.001, "B": 0.000, "CCC": 0.000, "D": 0.000},
    "AA":  {"AAA": 0.020, "AA": 0.880, "A": 0.085, "BBB": 0.010, "BB": 0.003, "B": 0.001, "CCC": 0.000, "D": 0.000},
    "A":   {"AAA": 0.001, "AA": 0.030, "A": 0.910, "BBB": 0.048, "BB": 0.008, "B": 0.002, "CCC": 0.000, "D": 0.000},
    "BBB": {"AAA": 0.000, "AA": 0.003, "A": 0.055, "BBB": 0.880, "BB": 0.048, "B": 0.010, "CCC": 0.002, "D": 0.002},
    "BB":  {"AAA": 0.000, "AA": 0.001, "A": 0.005, "BBB": 0.070, "BB": 0.820, "B": 0.090, "CCC": 0.009, "D": 0.005},
    "B":   {"AAA": 0.000, "AA": 0.000, "A": 0.002, "BBB": 0.005, "BB": 0.045, "B": 0.830, "CCC": 0.085, "D": 0.033},
    "CCC": {"AAA": 0.000, "AA": 0.000, "A": 0.000, "BBB": 0.010, "BB": 0.020, "B": 0.150, "CCC": 0.590, "D": 0.230},
    "D":   {"AAA": 0.000, "AA": 0.000, "A": 0.000, "BBB": 0.000, "BB": 0.000, "B": 0.000, "CCC": 0.000, "D": 1.000},
}

# Damodaran default spread by rating (Jan 2026 table), in basis points
SPREAD_BY_RATING_BPS: dict[str, float] = {
    "AAA": 40, "AA": 55, "A": 80, "BBB": 111, "BB": 184, "B": 509, "CCC": 885, "D": 1100,
}

BASEL_CORR_CAP = 0.24


def matrix_power(years: int) -> dict[str, dict[str, float]]:
    """Multi-year transition matrix via Markov powers."""
    def matmul(a, b):
        return {r1: {c1: sum(a[r1][r2] * b[r2][c1] for r2 in RATING_ORDER)
                     for c1 in RATING_ORDER} for r1 in RATING_ORDER}
    m = TRANSITION
    for _ in range(years - 1):
        m = matmul(m, TRANSITION)
    return m


def migrate(rating: str, years: int = 1) -> dict[str, float]:
    """Probability distribution over ratings after ``years``."""
    rating = base_rating(rating)
    m = matrix_power(years)
    return m[rating]


def expected_rating(rating: str, years: int = 1) -> float:
    """Expected notch position (index into RATING_ORDER); +1 = one notch worse."""
    dist = migrate(rating, years)
    start = RATING_ORDER.index(rating) if rating in RATING_ORDER else 3
    return sum((RATING_ORDER.index(r) - start) * p for r, p in dist.items())


def vasicek_pd(pd: float, z: float = 2.33) -> float:
    """Basel IRB conditional default probability.

    PD_stressed = Phi[(Phi^-1(PD) + sqrt(R)*Z) / sqrt(1-R)] with the Basel
    corporate asset correlation R = 0.12*(1-e^-50PD)/(1-e^-50) +
    0.24*[1-(1-e^-50PD)/(1-e^-50)]; Z is the stress quantile (2.33 ~ 99th).
    """
    pd = min(max(pd, 1e-6), 0.9999)
    w = (1 - math.exp(-50 * pd)) / (1 - math.exp(-50))
    r = 0.12 * w + BASEL_CORR_CAP * (1 - w)
    return min(1.0, norm_cdf((norm_ppf(pd) + math.sqrt(r) * z) / math.sqrt(1 - r)))


def norm_ppf(p: float) -> float:
    """Inverse standard normal CDF (Acklam-free rational approximation is
    overkill; use statistics.NormalDist)."""
    from statistics import NormalDist

    return NormalDist().inv_cdf(p)


def norm_cdf(x: float) -> float:
    from statistics import NormalDist

    return NormalDist().cdf(x)


def stressed_pd(pd: float, band_scale: float, z: float = 2.33) -> float:
    """Scenario-scaled conditional PD: the Vasicek stress quantile scales with
    the scenario band so high-impact events push deeper into the tail."""
    return vasicek_pd(pd, z=min(3.5, 1.5 + 1.2 * band_scale * (z / 2.33)))


def base_rating(rating: str) -> str:
    """Fold modifier notches (BBB+, BB-) onto the coarse matrix ratings."""
    rating = (rating or "BBB").strip().upper()
    if rating in TRANSITION:
        return rating
    for notch in ("+", "-"):
        if rating.endswith(notch) and rating[:-1] in TRANSITION:
            return rating[:-1]
    return "BBB"


def spread_widening_bps(rating: str, notches_down: float) -> float:
    """Spread widening from an expected downgrade, via the rating-spread table."""
    rating = base_rating(rating)
    start = RATING_ORDER.index(rating)
    new_idx = min(len(RATING_ORDER) - 2, start + notches_down)  # cap at CCC
    new_rating = RATING_ORDER[round(new_idx)]
    widening = SPREAD_BY_RATING_BPS[new_rating] - SPREAD_BY_RATING_BPS[rating]
    return max(0.0, float(widening))


def expected_loss(notional: float, pd: float, lgd: float) -> float:
    return notional * pd * lgd
