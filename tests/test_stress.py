import pytest

from src.engine.modules.stress import band_multiplier, run_stress, shocks_for

MINI = {
    "positions": [
        {"id": "EQ1", "asset_class": "equity", "sub_type": "strategic",
         "name": "Stock", "value": 1000000, "notional": 1000000},
        {"id": "BD1", "asset_class": "bond", "sub_type": "corporate",
         "name": "Corp Bond", "notional": 1000000, "duration": 5.0,
         "convexity": 25.0, "rating": "BBB", "spread_bps": 150},
        {"id": "LN1", "asset_class": "loan", "sub_type": "corporate",
         "name": "Loan", "notional": 1000000, "rating": "BB", "spread_bps": 400,
         "pd": 0.02, "lgd": 0.6},
        {"id": "SW1", "asset_class": "derivative", "sub_type": "interest_rate_swap",
         "name": "Pay Fixed", "notional": 10000000, "dv01_bps": 480, "position": "payer"},
    ]
}


def test_band_multiplier_ladder():
    assert band_multiplier(9.0) == 1.0
    assert band_multiplier(7.0) == 0.7
    assert band_multiplier(5.0) == 0.4
    assert band_multiplier(2.0) == 0.15


def test_shocks_scale_with_impact():
    high = shocks_for("Geopolitical", 9.0)
    low = shocks_for("Geopolitical", 5.0)
    assert abs(high["equity_pct"]) > abs(low["equity_pct"])


def test_bond_duration_math():
    from src.engine.modules.stress import _price_position

    pos = {"asset_class": "bond", "sub_type": "corporate", "notional": 1000000,
           "duration": 5.0, "convexity": 0.0}
    shocks = {"equity_pct": 0.0, "rates_bps": 100, "spread_bps": 0, "fx_pct": 0.0}
    pnl = _price_position(pos, shocks)
    assert pnl == pytest.approx(-50000.0)  # -D * dy * value = -5 * 0.01 * 1M


def test_equity_shock_math():
    from src.engine.modules.stress import _price_position

    pos = {"asset_class": "equity", "notional": 1000000, "value": 1000000}
    shocks = {"equity_pct": -0.10, "rates_bps": 0, "spread_bps": 0, "fx_pct": 0.0}
    assert _price_position(pos, shocks) == pytest.approx(-100000.0)


def test_swap_payer_gains_when_rates_rise():
    from src.engine.modules.stress import _price_position

    pos = {"asset_class": "derivative", "sub_type": "interest_rate_swap",
           "notional": 10000000, "dv01_bps": 480, "position": "payer"}
    shocks = {"equity_pct": 0.0, "rates_bps": 100, "spread_bps": 0, "fx_pct": 0.0}
    assert _price_position(pos, shocks) == pytest.approx(48000.0)


def test_run_stress_shape_and_consistency():
    result = run_stress(MINI, "Geopolitical", 9.0)
    assert result["pnl"] == pytest.approx(result["value_after"] - result["value_before"])
    classes = result["by_asset_class"]
    assert sum(c["pnl"] for c in classes.values()) == pytest.approx(result["pnl"], abs=1.0)
    assert result["top_losers"][0]["pnl"] <= result["top_losers"][-1]["pnl"]
    mc = result["monte_carlo"]
    assert mc["draws"] == 1000
    assert mc["var95"] >= mc["median_pnl"] * -1


def test_product_launch_is_mild():
    result = run_stress(MINI, "Product Launch", 4.0)
    assert abs(result["pnl_pct"]) < 1.0


def test_credit_event_hits_spreads_harder_than_rates():
    credit = run_stress(MINI, "Credit Event", 9.0)
    assert credit["by_asset_class"]["loan"]["pnl"] < 0
