"""Ingest the FNSPID universe subset (91k real headlines, 2009-2023).

Reads the Kaggle-filtered CSV (data/cache/fnspid_out/fnspid_universe.csv) and
feeds every headline through the standard pipeline with its real timestamp
(source 'fnspid'). Usage:

    python -m src.scripts.ingest_fnspid [--limit N]
"""

from __future__ import annotations

import argparse
import logging

import pandas as pd

from src.engine.config import settings
from src.engine.ingest.service import ingest_many
from src.engine.universe import TICKERS

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)-7s %(name)s | %(message)s")
log = logging.getLogger("fnspid")

CSV_PATH = settings.cache_dir / "fnspid_out" / "fnspid_universe.csv"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=None)
    args = parser.parse_args()

    if not CSV_PATH.exists():
        raise SystemExit(f"corpus missing: {CSV_PATH}")

    log.info("reading %s...", CSV_PATH.name)
    df = pd.read_csv(CSV_PATH)
    df = df[df["ticker"].isin(TICKERS)]
    log.info("rows: %d (%s)", len(df), dict(df["ticker"].value_counts()))

    items = []
    for _, row in df.iterrows():
        items.append({
            "text": str(row["title"]),
            "source": "fnspid",
            "published_at": pd.to_datetime(row["date"], utc=True).to_pydatetime(),
            "url": None,
            "external_id": f"fnspid-{hash((row['title'], row['date'])) & 0xFFFFFFFFFFFF}",
            "use_model": False,
            "extract_entities": False,
        })
        if args.limit and len(items) >= args.limit:
            break

    log.info("analyzing %d headlines...", len(items))
    stored = [r for r in ingest_many(items) if r is not None]
    log.info("stored %d articles (%d duplicates skipped)",
             len(stored), len(items) - len(stored))
    log.info("done")


if __name__ == "__main__":
    main()
