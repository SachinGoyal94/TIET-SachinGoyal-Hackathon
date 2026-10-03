"""Backfill real historical news from the GDELT DOC 2.0 API.

The DOC API supports explicit historical windows (startdatetime/enddatetime,
coverage from Jan 2017). We query per company per day so the 250-record cap
only truncates extraordinary news days, and feed every headline through the
standard ingestion pipeline (dedupe, NLP, event clustering) with source
'gdelt_hist'. The result is months of real news with real timestamps — the
input for the event study and impact calibration.

Usage: python -m src.scripts.backfill_gdelt_history --days 90 [--tickers AAPL,MSFT]
"""

from __future__ import annotations

import argparse
import logging
import time
from datetime import datetime, timedelta, timezone

import httpx

from src.engine.config import settings
from src.engine.ingest.service import ingest_many
from src.engine.universe import UNIVERSE

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)-7s %(name)s | %(message)s")
log = logging.getLogger("gdelt-hist")

DOC_URL = "https://api.gdeltproject.org/api/v2/doc/doc"
FETCH_SLEEP = 1.5  # informal GDELT throttling; be polite
MAX_RECORDS = 250


def fetch_day(client: httpx.Client, query: str, day: datetime) -> list[dict]:
    start = day.strftime("%Y%m%d") + "000000"
    end = day.strftime("%Y%m%d") + "235959"
    try:
        resp = client.get(
            DOC_URL,
            params={
                "query": f"{query} sourcelang:english",
                "mode": "ArtList",
                "maxrecords": str(MAX_RECORDS),
                "format": "json",
                "startdatetime": start,
                "enddatetime": end,
                "sort": "datedesc",
            },
            timeout=30.0,
        )
        if resp.status_code == 429:
            log.warning("rate limited, sleeping 30s")
            time.sleep(30)
            return fetch_day(client, query, day)
        resp.raise_for_status()
        payload = resp.json()
    except (httpx.HTTPError, ValueError) as exc:
        log.warning("fetch failed for %s %s: %s", query[:40], day.date(), exc)
        return []

    items = []
    for art in payload.get("articles", []):
        title = (art.get("title") or "").strip()
        url = art.get("url")
        if not title or not url:
            continue
        seen = art.get("seendate", "")
        try:
            published = datetime.strptime(seen, "%Y%m%dT%H%M%SZ").replace(tzinfo=timezone.utc)
        except ValueError:
            published = day.replace(hour=12, tzinfo=timezone.utc)
        items.append({
            "text": title,
            "source": "gdelt_hist",
            "published_at": published,
            "url": url,
            "external_id": f"gdelt-{url}",
            "use_model": False,
        })
    return items


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--days", type=int, default=90)
    parser.add_argument("--tickers", type=str, default="")
    parser.add_argument("--sleep", type=float, default=FETCH_SLEEP)
    args = parser.parse_args()

    from src.engine.db import Article, get_session
    from sqlalchemy import func, select

    with get_session() as s:
        existing = s.execute(select(func.count(Article.id))).scalar() or 0
    log.info("articles in db before: %d", existing)

    companies = [c for c in UNIVERSE
                 if not args.tickers or c.ticker in args.tickers.split(",")]

    # GDELT DOC: top-level OR of quoted phrases is fine; nesting is not
    end_day = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    days = [end_day - timedelta(days=d) for d in range(args.days, 0, -1)]

    total_stored = 0
    with httpx.Client() as client:
        for company in companies:
            query = " OR ".join(f'"{p}"' for p in
                                dict.fromkeys([company.name.split(" Inc")[0].split(" Corp")[0]
                                               .replace("The ", "").strip(), company.ticker]
                                              + list(company.aliases[:2])))
            company_stored = 0
            t0 = time.time()
            for day in days:
                items = fetch_day(client, query, day)
                if items:
                    results = ingest_many(items)
                    company_stored += sum(1 for r in results if r is not None)
                time.sleep(args.sleep)
            total_stored += company_stored
            log.info("%s: %d new articles (%d days, %.0fs)",
                     company.ticker, company_stored, len(days), time.time() - t0)

    log.info("backfill complete: %d new articles total", total_stored)


if __name__ == "__main__":
    main()
