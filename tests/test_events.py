from src.engine.nlp.events import EVENT_LABELS, classify, lexicon_votes


def test_labels_constant():
    assert len(EVENT_LABELS) == 6


def test_lexicon_votes_geopolitical():
    votes = lexicon_votes("Sanctions and tariff escalation push shipping lanes to a halt")
    assert votes.get("Geopolitical", 0) >= 2


def test_lexicon_only_classification():
    result = classify("Rating agencies downgrade the lender amid default fears",
                      use_model=False)
    assert result.label in EVENT_LABELS
    assert result.label == "Credit Event"


def test_hint_breaks_ties():
    result = classify("Company X acquires Company Y", event_hint="Merger/Acquisition",
                      use_model=False)
    assert result.label == "Merger/Acquisition"


def test_scores_sum_and_bounds():
    result = classify("Inflation spikes and the Federal Reserve hikes rates",
                      use_model=False)
    assert 0.0 <= result.confidence <= 0.99
    assert all(v >= 0.0 for v in result.scores.values())
