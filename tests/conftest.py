import os
import tempfile

# config.settings reads the environment at import time, so this must run
# before any src.engine import
os.environ.setdefault("RISK_DB_PATH", os.path.join(tempfile.mkdtemp(), "test.db"))
os.environ.setdefault("RISK_BACKFILL_ON_START", "false")

import pytest  # noqa: E402


@pytest.fixture(autouse=True)
def _stub_sentiment(monkeypatch):
    """Unit tests never load real models; accuracy is measured separately
    by the fine-tuning script's eval."""
    import src.engine.nlp.sentiment as sentiment

    monkeypatch.setattr(sentiment, "score_batch",
                        lambda texts, batch_size=64: [0.0] * len(texts))
    monkeypatch.setattr(sentiment, "score_sentiment", lambda text: 0.0)
