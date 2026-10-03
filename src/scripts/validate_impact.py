"""Event study: do Impact Scores line up with realized market moves?

For each clustered event with a matched company, we measure the ticker's
absolute 1-day price move following the event headline and correlate it with
the event's Impact Score. The platform predicts severity; the market grades it.

Usage:
    python -m src.scripts.validate_impact [--days 120]
"""

from __future__ import annotations

import argparse
import json
import logging
from datetime import datetime, timedelta, timezone

import numpy as np
from sqlalchemy import select

from src.engine.config import settings
from src.engine.db import Event, get_session
from src.engine.universe import BY_TICKER

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)-7s %(name)s | %(message)s")
log = logging.getLogger("validate")


def load_closes(days: int) -> dict[str, tuple[list[str], list[float]]]:
    """Daily closes per ticker with dates, disk-cached."""
    import yfinance as yf

    cache = settings.cache_dir / f"prices_{days}d_dated.json"
    if cache.exists():
        payload = json.loads(cache.read_text(encoding="utf-8"))
        return {t: (d, c) for t, (d, c) in payload["data"].items()}

    from src.engine.universe import TICKERS

    frame = yf.download(tickers=" ".join(TICKERS), period=f"{days}d",
                        interval="1d", auto_adjust=True, progress=False)
    closes = frame["Close"]
    data: dict[str, tuple[list[str], list[float]]] = {}
    for t in TICKERS:
        if t not in closes:
            continue
        series = closes[t].dropna()
        if len(series) > 10:
            data[t] = ([str(i.date()) for i in series.index],
                       [round(float(v), 4) for v in series.tolist()])
    cache.parent.mkdir(parents=True, exist_ok=True)
    cache.write_text(json.dumps({"data": data}), encoding="utf-8")
    return data


def next_move(dates: list[str], closes: list[float], after_utc: datetime) -> float | None:
    """Absolute return from the first close strictly after the event."""
    for i, d in enumerate(dates):
        day = datetime.fromisoformat(d).replace(tzinfo=timezone.utc)
        if day >= after_utc and i + 1 < len(closes):
            return abs(closes[i + 1] / closes[i] - 1.0)
    return None


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--days", type=int, default=120)
    parser.add_argument("--source", type=str, default=None,
                        help="restrict to one article source, e.g. 'gdelt' for live news")
    args = parser.parse_args()

    closes = load_closes(args.days)

    with get_session() as s:
        stmt = select(Event).order_by(Event.first_seen)
        if args.source:
            stmt = stmt.where(Event.first_source == args.source)
        events = s.execute(stmt).scalars().all()

    pairs: list[tuple[float, float]] = []
    for ev in events:
        ticker = ev.first_entity
        if not ticker or ticker not in BY_TICKER or ticker not in closes:
            continue
        dates, series = closes[ticker]
        # event windows use naive UTC ticks in the past; anchor at last_seen
        move = next_move(dates, series, ev.last_seen)
        if move is None:
            continue
        pairs.append((ev.max_impact, move))

    if len(pairs) < 20:
        log.warning("only %d matched events, not enough for a robust estimate", len(pairs))

    impacts = np.array([p[0] for p in pairs])
    moves = np.array([p[1] for p in pairs])

    def pearson(a, b):
        if len(a) < 3 or a.std() == 0 or b.std() == 0:
            return float("nan")
        return float(np.corrcoef(a, b)[0, 1])

    def spearman(a, b):
        ra = np.argsort(np.argsort(a)).astype(float)
        rb = np.argsort(np.argsort(b)).astype(float)
        return pearson(ra, rb)

    result = {
        "source_filter": args.source or "all",
        "events_matched": len(pairs),
        "pearson": round(pearson(impacts, moves), 3),
        "spearman": round(spearman(impacts, moves), 3),
        "mean_move_by_band": {
            band: round(float(moves[(impacts >= lo) & (impacts < hi)].mean()), 4)
            for band, lo, hi in [("1-4", 1, 4), ("4-6", 4, 6), ("6-8", 6, 8), ("8-10", 8, 10.01)]
            if ((impacts >= lo) & (impacts < hi)).any()
        },
    }
    log.info("impact validation: %s", json.dumps(result, indent=2))

    out = settings.cache_dir / "impact_validation.json"
    out.write_text(json.dumps(result, indent=2), encoding="utf-8")
    log.info("saved to %s", out)


if __name__ == "__main__":
    main()
