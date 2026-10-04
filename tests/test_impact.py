import pytest

from src.engine.nlp.impact import BASE_SEVERITY, score_impact


def test_score_within_bounds():
    for label in BASE_SEVERITY:
        for sent in (-1.0, -0.5, 0.0, 0.5, 1.0):
            for n in (1, 3, 10):
                result = score_impact(label, sent, n_sources=n)
                assert 1.0 <= result.score <= 10.0


def test_extremity_increases_impact():
    calm = score_impact("Geopolitical", 0.0).score
    loud = score_impact("Geopolitical", -0.9).score
    assert loud > calm


def test_unknown_label_uses_other_severity():
    assert score_impact("Weird", 0.0).base_severity == BASE_SEVERITY["Other"]


def test_high_severity_events_score_high():
    assert score_impact("Credit Event", -0.8).score >= 8.0
    assert score_impact("Product Launch", 0.3).score < 7.0


def test_breakdown_factors_consistent():
    r = score_impact("Macroeconomic", 0.6, n_sources=4)
    assert r.conviction_factor == pytest.approx(0.75 + 0.5 * 0.6)
    assert r.corroboration_factor == pytest.approx(1.3)
