from dataclasses import dataclass

# v2: empirically calibrated per-name severities. Derived from 19,872 real
# news events (FNSPID 2009-2023): mean |sector-adjusted CAR| per event label,
# anchored to 8.5 for Credit Event (the highest-moving class). Note: these
# are per-NAME severities - market-wide channels (geopolitical, macro) act
# mainly through the index factor, which the sector adjustment removes; that
# channel is covered separately by the Module B scenario library.
BASE_SEVERITY: dict[str, float] = {
    "Credit Event": 8.5,
    "Product Launch": 7.0,
    "Merger/Acquisition": 6.5,
    "Macroeconomic": 6.0,
    "Other": 6.0,
    "Geopolitical": 5.5,
}

MIN_IMPACT, MAX_IMPACT = 1.0, 10.0
MAX_CORROBORATING_SOURCES = 3


@dataclass(frozen=True)
class ImpactBreakdown:
    score: float
    base_severity: float
    conviction_factor: float
    corroboration_factor: float


def vix_regime_factor(vix: float) -> float:
    """Crisis-context multiplier: the same headline scores higher in stressed
    markets (ablated on 19,872 real events: IC 0.082 -> 0.098, z ~ 2.3)."""
    if vix >= 40:
        return 1.25
    if vix >= 30:
        return 1.15
    if vix >= 25:
        return 1.08
    if vix < 15:
        return 0.92
    return 1.0


def score_impact(event_label: str, sentiment_score: float,
                 n_sources: int = 1, vix: float | None = None) -> ImpactBreakdown:
    """base severity x conviction(|sentiment|) x corroboration(source count)
    x VIX regime factor, clipped to [1, 10]."""
    base = BASE_SEVERITY.get(event_label, BASE_SEVERITY["Other"])
    extremity = abs(max(-1.0, min(1.0, sentiment_score)))
    conviction = 0.75 + 0.5 * extremity
    corroborating = max(0, min(n_sources - 1, 3))
    corroboration = 1.0 + 0.1 * corroborating
    regime = vix_regime_factor(vix) if vix is not None else 1.0

    raw = base * conviction * corroboration * regime
    score = round(max(MIN_IMPACT, min(MAX_IMPACT, raw)), 1)
    return ImpactBreakdown(score=score, base_severity=base,
                           conviction_factor=round(conviction, 4),
                           corroboration_factor=round(corroboration, 4))
