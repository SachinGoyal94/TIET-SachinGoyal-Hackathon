import logging
from datetime import datetime, timezone

import httpx

from src.engine.ingest.service import ingest_item

logger = logging.getLogger(__name__)

DOC_URL = "https://api.gdeltproject.org/api/v2/doc/doc"
_QUERY = '("stocks" OR "market" OR "economy" OR "banking" OR "merger") sourcelang:english'


def fetch_headlines(client: httpx.Client, *, timespan: str = "15min",
                    max_records: int = 75) -> list[dict]:
    """Recent English business headlines from GDELT DOC 2.0 (keyless)."""
    try:
        resp = client.get(
            DOC_URL,
            params={
                "query": _QUERY,
                "mode": "ArtList",
                "maxrecords": str(max_records),
                "format": "json",
                "timespan": timespan,
                "sort": "datedesc",
            },
            timeout=20.0,
            headers={"User-Agent": "risk-intel-platform/1.0 (hackathon)"},
        )
        resp.raise_for_status()
        payload = resp.json()
    except (httpx.HTTPError, ValueError) as exc:
        logger.warning("GDELT fetch failed (%s), skipping this cycle", exc)
        return []

    items: list[dict] = []
    for art in payload.get("articles", []):
        title = (art.get("title") or "").strip()
        url = art.get("url")
        if not title or not url:
            continue
        items.append({
            "text": title,
            "url": url,
            "external_id": f"gdelt-{url}",
            "published_at": _parse_seen(art.get("seendate")),
        })
    logger.info("GDELT returned %d headlines", len(items))
    return items


def poll_and_ingest(client: httpx.Client | None = None) -> int:
    own = client is None
    if own:
        client = httpx.Client()
    try:
        stored = 0
        for item in fetch_headlines(client):
            if ingest_item(
                text=item["text"],
                source="gdelt",
                published_at=item["published_at"],
                url=item["url"],
                external_id=item["external_id"],
            ) is not None:
                stored += 1
        return stored
    finally:
        if own:
            client.close()


def _parse_seen(seen: str | None) -> datetime:
    # GDELT format: 20260303T121500Z
    if seen:
        try:
            return datetime.strptime(seen, "%Y%m%dT%H%M%SZ").replace(tzinfo=timezone.utc)
        except ValueError:
            pass
    return datetime.now(timezone.utc)
