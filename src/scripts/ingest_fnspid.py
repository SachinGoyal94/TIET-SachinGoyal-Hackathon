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

    # resume support: drop headlines already stored from a previous run
    from sqlalchemy import select

    from src.engine.db import Article, get_session

    with get_session() as s:
        stored_ids = set(s.execute(
            select(Article.external_id).where(Article.source == "fnspid")
        ).scalars().all())
    df["external_id"] = [
        f"fnspid-{hash((t, d)) & 0xFFFFFFFFFFFF}"
        for t, d in zip(df["title"], df["date"])
    ]
    before = len(df)
    df = df[~df["external_id"].isin(stored_ids)]
    log.info("resume: %d already stored, %d to process", before - len(df), len(df))
    if df.empty:
        log.info("nothing to do")
        return

    # chunked batches: each chunk is scored and persisted, so an interruption
    # only loses the current chunk
    CHUNK = 2000
    chunks = [df.iloc[i:i + CHUNK] for i in range(0, len(df), CHUNK)]
    total_stored = 0
    for n, chunk in enumerate(chunks, start=1):
        items = []
        for _, row in chunk.iterrows():
            items.append({
                "text": str(row["title"]),
                "source": "fnspid",
                "published_at": pd.to_datetime(row["date"], utc=True).to_pydatetime(),
                "url": None,
                "external_id": row["external_id"],
                "use_model": False,
                "extract_entities": False,
            })
        stored = [r for r in ingest_many(items) if r is not None]
        total_stored += len(stored)
        log.info("chunk %d/%d: %d stored (%d duplicates) | total %d",
                 n, len(chunks), len(stored), len(items) - len(stored), total_stored)
    log.info("done: %d new articles", total_stored)


if __name__ == "__main__":
    main()
