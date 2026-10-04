"""Ingest the Kaggle stock-tweets corpus (real social-media source).

Filters stock_tweets.csv (80k+ tweets, Sep 2021 - Sep 2022, minute-level
timestamps) to the index universe and feeds them through the pipeline with
source 'kaggle_tweets'. Usage:

    python -m src.scripts.ingest_tweets [--limit N]
"""

from __future__ import annotations

import argparse
import logging

import pandas as pd

from src.engine.config import settings
from src.engine.ingest.service import ingest_many
from src.engine.universe import TICKERS

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)-7s %(name)s | %(message)s")
log = logging.getLogger("tweets")

CSV_PATH = settings.cache_dir / "tweets" / "stock_tweets.csv"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=None)
    args = parser.parse_args()

    if not CSV_PATH.exists():
        raise SystemExit(f"corpus missing: {CSV_PATH}")

    log.info("reading %s...", CSV_PATH.name)
    df = pd.read_csv(CSV_PATH, usecols=["Date", "Tweet", "Stock Name"])
    df = df[df["Stock Name"].isin(TICKERS)].copy()
    df["Date"] = pd.to_datetime(df["Date"], format="mixed", errors="coerce", utc=True)
    df = df.dropna(subset=["Date"])
    df = df[df["Tweet"].astype(str).str.len() > 15]
    log.info("universe tweets: %d (%s)", len(df),
             dict(df["Stock Name"].value_counts().head(14)))
    log.info("range: %s -> %s", df["Date"].min(), df["Date"].max())

    if args.dry_run if hasattr(args, "dry_run") else False:
        return

    items = []
    for _, row in df.iterrows():
        items.append({
            "text": str(row["Tweet"])[:1000],
            "source": "kaggle_tweets",
            "published_at": row["Date"].to_pydatetime(),
            "url": None,
            "external_id": f"tweet-{hash((row['Tweet'], str(row['Date']))) & 0xFFFFFFFFFFFF}",
            "use_model": False,
            "extract_entities": False,
        })
        if args.limit and len(items) >= args.limit:
            break

    log.info("analyzing %d tweets...", len(items))
    stored = [r for r in ingest_many(items) if r is not None]
    log.info("stored %d articles (%d duplicates skipped)",
             len(stored), len(items) - len(stored))
    log.info("done")


if __name__ == "__main__":
    main()
