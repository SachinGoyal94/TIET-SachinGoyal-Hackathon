"""Persist the Kaggle-scored stock tweets into the platform database.

Fast local part only: entity matching (cashtags), signal rows, event
clustering. No models. Usage:

    python -m src.scripts.persist_tweets [--limit N]
"""

from __future__ import annotations

import argparse
import logging

import pandas as pd

from src.engine.config import settings
from src.engine.ingest.service import ingest_item
from src.engine.nlp import entities, impact as impact_mod
from src.engine.nlp.pipeline import RiskSignal

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)-7s %(name)s | %(message)s")
log = logging.getLogger("persist-tweets")

CSV_PATH = settings.cache_dir / "tweets_score_out" / "tweets_scored.csv"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=None)
    args = parser.parse_args()

    df = pd.read_csv(CSV_PATH)
    log.info("scored rows: %d", len(df))

    stored = 0
    for i, row in df.iterrows():
        text = str(row["tweet"])
        matches = entities.match_entities(text)
        ticker = str(row["ticker"])
        if ticker not in {m.ticker for m in matches} and ticker in entities.BY_TICKER:
            c = entities.BY_TICKER[ticker]
            matches = list(matches) + [entities.EntityMatch(
                ticker=ticker, sector=c.sector, name=ticker)]
        signal = RiskSignal(
            text=text,
            text_hash=str(row["external_id"]).replace("tweet-", ""),
            sentiment_score=float(row["sentiment"]),
            event_label=str(row["event_label"]),
            event_confidence=float(row["event_confidence"]),
            impact_score=float(row["impact"]),
            impact_breakdown=impact_mod.ImpactBreakdown(
                score=float(row["impact"]), base_severity=0.0,
                conviction_factor=0.0, corroboration_factor=0.0),
            entities=matches,
            model_versions={"sentiment": "finbert-v0", "events": "lexicon-v0",
                            "impact": "composite-v0"},
        )
        result = ingest_item(
            text=text,
            source="kaggle_tweets",
            published_at=pd.to_datetime(row["date"], utc=True).to_pydatetime(),
            external_id=str(row["external_id"]),
            signal=signal,
        )
        stored += 1 if result is not None else 0
        if (i + 1) % 4000 == 0:
            log.info("%d/%d processed (%d stored)", i + 1, len(df), stored)

    log.info("done: %d stored", stored)


if __name__ == "__main__":
    main()
