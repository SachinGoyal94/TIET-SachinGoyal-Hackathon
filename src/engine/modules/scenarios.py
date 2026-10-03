"""Named stress scenario library with sourced magnitudes.

Two families:
- supervisory scenarios: Fed DFAST severely adverse and EBA adverse, with the
  published aggregate magnitudes;
- historical replays: realized market moves from five stress episodes
  (COVID Mar 2020, 2022 rate shock, SVB Mar 2023, taper tantrum 2013,
  China devaluation 2015-16).

Each scenario maps onto the same shock-vector shape the event-triggered
matrix uses, so one repricing engine serves both. Sources are noted per
scenario; magnitudes marked est. are interpolations, not published figures.
"""

from __future__ import annotations

SCENARIOS: dict[str, dict] = {
    "dfast_severely_adverse": {
        "family": "supervisory",
        "description": "Fed DFAST severely adverse (2025 round): unemployment +5.9pp to 10%, "
                       "equities -30%, house prices -33%, CRE -30%; flight-to-quality drops rates.",
        "source": "federalreserve.gov 2025 stress test scenarios and results",
        "shocks": {"equity_pct": -0.30, "rates_bps": -200, "spread_bps": 250, "fx_pct": 0.0},
    },
    "eba_adverse_2025": {
        "family": "supervisory",
        "description": "EBA 2025 EU-wide adverse: geopolitical escalation and trade "
                       "fragmentation, cumulative GDP -6.3% vs baseline, unemployment +6.1pp.",
        "source": "eba.europa.eu / esrb.europa.eu 2025 EU-wide stress test",
        "shocks": {"equity_pct": -0.30, "rates_bps": -100, "spread_bps": 200, "fx_pct": 0.0},
    },
    "covid_march_2020": {
        "family": "historical",
        "description": "COVID crash, Feb 19 - Mar 23 2020: S&P -34%, 10Y 1.92% -> 0.31%, "
                       "IG spreads 92 -> 244bps, HY OAS ~400 -> ~1,100bps.",
        "source": "Fed FEDS Notes; ICI; Treasury data",
        "shocks": {"equity_pct": -0.34, "rates_bps": -160, "spread_bps": 700, "fx_pct": 0.03},
    },
    "rates_2022": {
        "family": "historical",
        "description": "2022 rate shock: S&P -19.4%, Bloomberg US Agg -13% (worst bond year on "
                       "record), 10Y 1.5% -> 4.2%.",
        "source": "Morgan Stanley 60/40 study; Treasury data",
        "shocks": {"equity_pct": -0.194, "rates_bps": 270, "spread_bps": 30, "fx_pct": 0.0},
    },
    "svb_march_2023": {
        "family": "historical",
        "description": "SVB / regional bank stress, Mar 2023: $620bn unrealized securities losses "
                       "across US banks; regional bank index -20% YTD by Mar 17.",
        "source": "FDIC; Moody's; CRS report",
        "shocks": {"equity_pct": -0.20, "rates_bps": -100, "spread_bps": 120, "fx_pct": 0.0},
    },
    "taper_tantrum_2013": {
        "family": "historical",
        "description": "Taper tantrum, May-Sep 2013: 10Y 1.63% -> ~3.0% (~+140bps in 4 months); "
                       "HY roughly +100bps; broadest bond-fund losses in a quarter since 2008.",
        "source": "Treasury data; contemporaneous fund-flow reports",
        "shocks": {"equity_pct": -0.05, "rates_bps": 140, "spread_bps": 100, "fx_pct": 0.0},
    },
    "china_devaluation_2015": {
        "family": "historical",
        "description": "China devaluation Aug 2015 - Jan 2016: CNY ~-4% in days, Shanghai -18% "
                       "early Jan, circuit breakers tripped; HY energy spreads blew out.",
        "source": "Exchange and index data, Aug 2015 / Jan 2016",
        "shocks": {"equity_pct": -0.10, "rates_bps": -30, "spread_bps": 150, "fx_pct": -0.02},
    },
}


def get_scenario(name: str) -> dict:
    if name not in SCENARIOS:
        raise KeyError(f"unknown scenario '{name}'")
    return SCENARIOS[name]
