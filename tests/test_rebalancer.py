from src.engine.modules.rebalancer import (
    blend_ticker_scores,
    compute_targets,
    decayed_sentiment,
    _renormalize_with_cap,
)

TICKERS = [f"T{i}" for i in range(10)]
ANCHOR = {t: 0.1 for t in TICKERS}
VOLS = {t: 0.2 for t in TICKERS}


def _params(**over):
    base = {"max_turnover": 1.0}
    base.update(over)
    return base


def test_decayed_sentiment_recency_wins():
    recent = decayed_sentiment([(1.0, 0.8), (1.0, -0.2)])
    old = decayed_sentiment([(72.0, 0.8), (1.0, -0.2)])
    assert recent > old


def test_decayed_sentiment_empty():
    assert decayed_sentiment([]) == 0.0


def test_weights_sum_to_one():
    scores = {t: 0.3 for t in TICKERS}
    w = compute_targets(scores, ANCHOR, VOLS, params=_params())
    assert abs(sum(w.values()) - 1.0) < 1e-6


def test_positive_sentiment_gets_more_weight():
    scores = {t: 0.0 for t in TICKERS}
    scores["T0"] = 0.8
    w = compute_targets(scores, ANCHOR, VOLS, params=_params())
    assert w["T0"] > w["T5"]


def test_cap_respected():
    scores = {t: 0.0 for t in TICKERS}
    scores["T0"] = 2.0
    w = compute_targets(scores, ANCHOR, VOLS, params=_params())
    assert all(v <= 0.2 + 1e-9 for v in w.values())


def test_turnover_capped():
    scores = {t: 0.0 for t in TICKERS}
    scores["T0"] = 0.9
    prev = {t: 0.1 for t in TICKERS}
    w = compute_targets(scores, ANCHOR, VOLS, prev_weights=prev,
                        params=_params(max_turnover=0.02))
    for t in TICKERS:
        assert abs(w[t] - prev[t]) <= 0.02 + 1e-6, (t, w[t], prev[t])


def test_low_vol_name_moves_more():
    vols = {t: 0.4 for t in TICKERS}
    vols["T1"] = 0.1
    scores = {t: 0.0 for t in TICKERS}
    scores["T0"] = scores["T1"] = 0.6
    w = compute_targets(scores, ANCHOR, vols, params=_params())
    assert w["T1"] - 0.1 > w["T0"] - 0.1


def test_sector_spillover():
    scores_flat = {t: 0.0 for t in TICKERS}
    w_none = compute_targets(scores_flat, ANCHOR, VOLS, params=_params())

    from unittest.mock import patch
    fake = {t: type("C", (), {"sector": "Tech" if t == "T0" else "Utility"})()
            for t in TICKERS}
    with patch("src.engine.modules.rebalancer.BY_TICKER", fake):
        blended = blend_ticker_scores({t: 0.0 for t in TICKERS}, {"Tech": 0.7})
    assert blended["T0"] > blended["T1"]
    w = compute_targets(blended, ANCHOR, VOLS, params=_params())
    assert w["T0"] > w_none["T0"]


def test_renormalize_with_cap_handles_extreme_input():
    raw = {"A": 0.9, "B": 0.05, "C": 0.05}
    w = _renormalize_with_cap(raw, cap=0.5)
    assert abs(sum(w.values()) - 1.0) < 1e-6
    assert all(v <= 0.5 + 1e-9 for v in w.values())
