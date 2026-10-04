"""Ingest the Kaggle 'Daily Financial News for 6000+ Stocks' corpus.

Filters raw_partner_headlines.csv to the index universe and feeds every
headline through the standard pipeline with its real publication timestamp
(source 'kaggle_hist'). Usage:

    python -m src.scripts.ingest_newsdb [--limit N] [--dry-run]
"""

from __future__ import annotations

import argparse
import logging
from datetime import datetime, timezone

import pandas as pd

from src.engine.config import settings
from src.engine.ingest.service import ingest_many
from src.engine.universe import TICKERS

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)-7s %(name)s | %(message)s")
log = logging.getLogger("newsdb")

CSV_PATH = settings.cache_dir / "newsdb" / "analyst_ratings_processed.csv"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=None, help="max rows per ticker")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    if not CSV_PATH.exists():
        raise SystemExit(f"corpus missing: {CSV_PATH}")

    log.info("reading %s...", CSV_PATH.name)
    df = pd.read_csv(CSV_PATH, usecols=["title", "date", "stock"])
    df = df[df["stock"].isin(TICKERS)].copy()
    df["date"] = pd.to_datetime(df["date"], format="mixed", errors="coerce", utc=True)
    df = df.dropna(subset=["date"])
    df = df[df["title"].astype(str).str.len() > 10]
    log.info("universe rows: %d (%s)", len(df),
             dict(df["stock"].value_counts().head(14)))
    log.info("date range: %s -> %s", df["date"].min(), df["date"].max())

    if args.dry_run:
        return

    items = []
    for ticker, group in df.groupby("stock"):
        if args.limit:
            group = group.head(args.limit)
        for _, row in group.iterrows():
            items.append({
                "text": str(row["title"]),
                "source": "kaggle_hist",
                "published_at": row["date"].to_pydatetime(),
                "url": None,
                "external_id": f"newsdb-{hash((row['title'], str(row['date']))) & 0xFFFFFFFFFFFF}",
                "use_model": False,
                "extract_entities": False,
            })

    log.info("analyzing %d headlines with the pipeline...", len(items))
    stored = [r for r in ingest_many(items) if r is not None]
    log.info("stored %d articles (%d duplicates skipped)",
             len(stored), len(items) - len(stored))
    log.info("done")


if __name__ == "__main__":
    main()
