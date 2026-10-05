"""One-time demo data bootstrap.

Builds ~3 weeks of history so every dashboard has content on first run:
handmade seed corpus, the vendored Kaggle headlines, a synthetic news/tweet
backlog, a day-by-day rebalance replay, and a few historical stress runs.

Usage: python -m src.scripts.backfill [--force] [--days 21]
"""

from __future__ import annotations

import argparse
import json
import logging
import random
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select

from src.engine.config import settings
from src.engine.db import Article, Event, StressRun, Weight, get_session
from src.engine.ingest.service import ingest_item, ingest_many
from src.engine.ingest.seed import load_handmade, load_kaggle
from src.engine.ingest.synthetic import generate_history
from src.engine.market_data import daily_volatility, market_cap_weights
from src.engine.modules.rebalancer import (
    blend_ticker_scores,
    compute_targets,
    decayed_sentiment,
)
from src.engine.modules.stress import run_stress
from src.engine.universe import SECTOR_MEMBERS, TICKERS

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)-7s %(name)s | %(message)s")
log = logging.getLogger("backfill")


def has_data() -> bool:
    with get_session() as s:
        return (s.execute(select(func.count(Article.id))).scalar() or 0) > 0


def build_items(days: int, per_day: int, rng: random.Random) -> list[dict]:
    now = datetime.now(timezone.utc)
    window_start = now - timedelta(days=days)
    items: list[dict] = []

    def ts_between(lo: datetime, hi: datetime) -> datetime:
        span = (hi - lo).total_seconds()
        return lo + timedelta(seconds=rng.random() * span)

    for row in load_handmade():
        items.append({
            "text": row["text"], "source": "seed_news",
            "published_at": ts_between(window_start, now),
            "event_hint": row["event_label"], "use_model": False,
        })

    for row in load_kaggle():
        items.append({
            "text": row["text"], "source": "kaggle_news",
            "published_at": ts_between(window_start, now),
            "use_model": False,
        })

    for gen in generate_history(rng, days, per_day):
        items.append({
            "text": gen.text, "source": gen.source,
            "published_at": gen.published_at,
            "event_hint": gen.event_label, "use_model": False,
        })

    items.sort(key=lambda i: i["published_at"])
    return items


def force_event(items: list[dict], when: datetime, variants: list[str]) -> None:
    """Inject corroborating geopolitical coverage so a stress trigger exists."""
    for k, text in enumerate(variants):
        items.append({
            "text": text, "source": "synthetic_news",
            "published_at": when + timedelta(minutes=90 * k),
            "event_hint": "Geopolitical", "use_model": False,
        })
    items.sort(key=lambda i: i["published_at"])


def replay_rebalances(now: datetime, days: int) -> None:
    anchor_full = market_cap_weights() or {t: 1 / len(TICKERS) for t in TICKERS}
    missing = [t for t in TICKERS if t not in anchor_full]
    anchor = {**{t: 1 / len(TICKERS) for t in missing}, **anchor_full}
    total = sum(anchor.values())
    anchor = {t: w / total for t, w in anchor.items()}
    vols = daily_volatility() or None

    from src.engine.db import Signal

    with get_session() as s:
        rows = s.execute(select(Signal)).scalars().all()

    # group signals by scope/entity once; decay is computed per tick
    by_key: dict[tuple[str, str], list[tuple[datetime, float]]] = {}
    for sig in rows:
        by_key.setdefault((sig.scope, sig.entity), []).append(
            (sig.analyzed_at, sig.sentiment_score))
    for entries in by_key.values():
        entries.sort(key=lambda e: e[0])

    def score_at(scope: str, entity: str, tick: datetime) -> float:
        pairs = []
        for ts, score in by_key.get((scope, entity), []):
            if ts <= tick and (tick - ts) <= timedelta(hours=48):
                age = (tick - ts).total_seconds() / 3600
                pairs.append((age, score))
        return decayed_sentiment(pairs)

    prev: dict[str, float] | None = None
    for d in range(days, -1, -1):
        tick = (now - timedelta(days=d)).replace(hour=16, minute=0, second=0, microsecond=0)
        if tick > now:
            tick = now

        company_scores = {t: score_at("company", t, tick) for t in TICKERS}
        sector_scores = {sec: score_at("sector", sec, tick) for sec in SECTOR_MEMBERS}
        scores = blend_ticker_scores(company_scores, sector_scores)

        targets = compute_targets(scores, anchor, vols, prev)
        with get_session() as s:
            for t, w in targets.items():
                s.add(Weight(ts=tick, ticker=t, weight=w,
                             anchor_weight=anchor[t],
                             sentiment_used=company_scores.get(t, 0.0)))
        prev = targets
    log.info("rebalance replay done (%d ticks)", days + 1)


def seed_stress_runs(now: datetime, days: int) -> None:
    pf = json.loads(settings.portfolio_path.read_text(encoding="utf-8"))
    scenarios = [
        ("Geopolitical", days - 4),
        ("Credit Event", max(days - 10, 2)),
        ("Geopolitical", max(days - 16, 1)),
    ]
    with get_session() as s:
        n_events = (s.execute(select(func.count(Event.id))).scalar() or 0)
    if n_events == 0:
        log.warning("no events found for stress seeding")
        return

    for label, offset in scenarios:
        when = now - timedelta(days=offset)
        with get_session() as s:
            ev = s.execute(
                select(Event)
                .where(Event.event_label == label, Event.max_impact >= 6.0)
                .order_by(Event.max_impact.desc())
                .limit(1)
            ).scalar_one_or_none()
            if ev is None:
                continue
            impact = min(ev.max_impact, 9.6)
            result = run_stress(pf, ev.event_label, impact)
            s.add(StressRun(
                ts=when, event_id=ev.id, event_label=ev.event_label,
                event_headline=ev.headline, impact_score=impact,
                triggered_by="backfill",
                value_before=result["value_before"], value_after=result["value_after"],
                pnl=result["pnl"], pnl_pct=result["pnl_pct"], details=result,
            ))
    log.info("stress scenarios seeded")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--force", action="store_true", help="rebuild even if data exists")
    parser.add_argument("--days", type=int, default=21)
    parser.add_argument("--per-day", type=int, default=9)
    args = parser.parse_args(args=None if __name__ == "__main__" else [])

    if args.force:
        for suffix in ("", "-wal", "-shm"):
            settings.db_path.with_name(settings.db_path.name + suffix).unlink(missing_ok=True)
    elif has_data():
        log.info("database already has data, skipping backfill (use --force)")
        return

    rng = random.Random(2026)
    now = datetime.now(timezone.utc)

    log.info("building %d days of history...", args.days)
    items = build_items(args.days, args.per_day, rng)

    # guarantee two stressable high-impact geopolitical windows
    force_event(items, now - timedelta(days=3), [
        "Major Middle East supply route blocked as conflict escalates, insurance costs surge",
        "Tanker traffic halts through key strait after missile attacks on shipping",
        "Energy importers scramble as regional conflict enters second week",
    ])
    force_event(items, now - timedelta(days=13), [
        "Sanctions package hits major exporter, supply chains brace for disruption",
        "Retaliatory measures tighten chokepoint trade flows further",
        "Commodity routes rerouted as standoff escalates",
    ])

    log.info("analyzing %d items with the NLP pipeline...", len(items))
    stored = [r for r in ingest_many(items) if r is not None]
    log.info("stored %d articles (%d duplicates skipped)",
             len(stored), len(items) - len(stored))

    log.info("replaying rebalances...")
    replay_rebalances(now, args.days)

    log.info("seeding stress scenarios...")
    seed_stress_runs(now, args.days)

    with get_session() as s:
        for table in (Article, Event, Weight, StressRun):
            n = s.execute(select(func.count(table.id))).scalar() or 0
            log.info("%-12s %d rows", table.__tablename__, n)
    log.info("backfill complete")


if __name__ == "__main__":
    main()
