# Kaggle CPU kernel: fetches ~90 days of GDELT headlines for the 14-ticker
# universe and writes a CSV for local ingestion. Runs on Kaggle's IP, avoiding
# the local DOC-API throttle. No GPU needed.
#
# Output: /kaggle/working/gdelt_headlines.csv
#         columns: text, ticker, published_at (UTC ISO), url

import glob
import json
import time
from datetime import datetime, timedelta, timezone

import httpx

DOC_URL = "https://api.gdeltproject.org/api/v2/doc/doc"
THROTTLE_MSG = "Please limit requests to one every 5 seconds"

UNIVERSE = {
    "AAPL": ('"Apple" OR "AAPL" OR "iPhone"', "Technology"),
    "MSFT": ('"Microsoft"', "Technology"),
    "NVDA": ('"NVIDIA" OR "Nvidia"', "Technology"),
    "GOOGL": ('"Alphabet" OR "Google"', "Technology"),
    "META": ('"Meta" OR "Facebook"', "Technology"),
    "JPM": ('"JPMorgan" OR "JP Morgan"', "Financials"),
    "BAC": ('"Bank of America"', "Financials"),
    "GS": ('"Goldman Sachs"', "Financials"),
    "XOM": ('"Exxon" OR "ExxonMobil"', "Energy"),
    "CVX": ('"Chevron"', "Energy"),
    "WMT": ('"Walmart"', "Consumer"),
    "KO": ('"Coca-Cola" OR "Coke"', "Consumer"),
    "BA": ('"Boeing"', "Industrials"),
}

DAYS = 90


def fetch_day(client: httpx.Client, ticker: str, query: str, day: datetime) -> list[dict]:
    start = day.strftime("%Y%m%d") + "000000"
    end = day.strftime("%Y%m%d") + "235959"
    for attempt in range(6):
        try:
            resp = client.get(
                DOC_URL,
                params={
                    "query": f"{query} sourcelang:english",
                    "mode": "ArtList",
                    "maxrecords": "250",
                    "format": "json",
                    "startdatetime": start,
                    "enddatetime": end,
                    "sort": "datedesc",
                },
                timeout=30.0,
            )
            body = resp.text
            if THROTTLE_MSG in body or resp.status_code == 429:
                time.sleep(30)
                continue
            resp.raise_for_status()
            payload = json.loads(body)
        except (httpx.HTTPError, ValueError) as exc:
            print(f"fetch failed {ticker} {day.date()}: {exc}", flush=True)
            return []

        items = []
        for art in payload.get("articles", []):
            title = (art.get("title") or "").strip()
            url = art.get("url")
            if not title or not url:
                continue
            seen = art.get("seendate", "")
            try:
                published = datetime.strptime(seen, "%Y%m%dT%H%M%SZ").replace(
                    tzinfo=timezone.utc).isoformat()
            except ValueError:
                published = day.replace(hour=12, tzinfo=timezone.utc).isoformat()
            items.append({"text": title, "ticker": ticker,
                          "published_at": published, "url": url})
        return items
    return []


def main():
    import csv

    out_path = "/kaggle/working/gdelt_headlines.csv"
    end_day = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    days = [end_day - timedelta(days=d) for d in range(DAYS, 0, -1)]

    rows = []
    t0 = time.time()
    with httpx.Client() as client:
        for ticker, (query, _sector) in UNIVERSE.items():
            count = 0
            for day in days:
                rows.extend(fetch_day(client, ticker, query, day))
                count += 1
                time.sleep(5.5)
            print(f"{ticker}: {len(rows)} cumulative rows ({count} days, "
                  f"{time.time() - t0:.0f}s elapsed)", flush=True)

    # dedupe by url, keep first
    seen = set()
    unique = []
    for r in rows:
        if r["url"] in seen:
            continue
        seen.add(r["url"])
        unique.append(r)

    with open(out_path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["text", "ticker", "published_at", "url"])
        w.writeheader()
        w.writerows(unique)
    print(f"done: {len(unique)} unique headlines -> {out_path}", flush=True)


if __name__ == "__main__":
    main()
