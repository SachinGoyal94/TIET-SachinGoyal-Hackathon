from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select

from src.engine.db import Article, Signal, get_session
from src.engine.ingest.service import ingest_item, ingest_many


def _counts(model) -> int:
    with get_session() as s:
        return s.execute(select(func.count(model.id))).scalar() or 0


def test_ingest_many_stores_articles_and_signals():
    items = [
        {"text": "Apple announces record buyback program", "source": "test",
         "published_at": datetime.now(timezone.utc), "use_model": False},
        {"text": "$JPM refinances debt at tighter spreads", "source": "test",
         "published_at": datetime.now(timezone.utc), "use_model": False},
    ]
    results = [r for r in ingest_many(items) if r]
    assert len(results) == 2
    assert all(r["event_label"] for r in results)


def test_duplicates_are_skipped():
    text = "Unique headline about Coca-Cola raising guidance"
    ts = datetime.now(timezone.utc)
    first = ingest_item(text, "test", ts, event_hint="Macroeconomic",
                        use_model=False)
    second = ingest_item(text, "test", ts + timedelta(minutes=5),
                         event_hint="Macroeconomic", use_model=False)
    assert first is not None
    assert second is None


def test_cluster_merges_within_window():
    now = datetime.now(timezone.utc)
    items = []
    for k, text in enumerate([
        "War escalation disrupts shipping lanes for Boeing suppliers",
        "Missile attacks halt tanker traffic hitting Boeing routes",
        "Conflict near key chokepoint sends Boeing supply costs higher",
    ]):
        # chronological order: clusters only absorb items at or after first_seen
        items.append({"text": text, "source": "test",
                      "published_at": now - timedelta(hours=2 - k),
                      "event_hint": "Geopolitical", "use_model": False})
    results = [r for r in ingest_many(items) if r]
    assert len(results) == 3
    assert len({r["event_id"] for r in results}) == 1
    assert results[-1]["n_sources"] == 3
    impacts = [r["cluster_max_impact"] for r in results]
    assert impacts[-1] >= impacts[0]


def test_signal_rows_per_scope():
    before = _counts(Signal)
    ingest_item("Apple and Microsoft both raise guidance", "test",
                datetime.now(timezone.utc), event_hint="Macroeconomic",
                use_model=False)
    added = _counts(Signal) - before
    assert added >= 3  # two company rows + at least one sector row


def test_article_count_grows():
    before = _counts(Article)
    ingest_item("Boeing secures record aircraft orders at airshow", "test",
                datetime.now(timezone.utc), event_hint="Product Launch",
                use_model=False)
    assert _counts(Article) == before + 1
