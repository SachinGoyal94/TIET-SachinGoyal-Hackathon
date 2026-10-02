import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import select

from src.engine.db import Article, Event, Signal, get_session
from src.engine.nlp import impact as impact_mod
from src.engine.nlp.pipeline import RiskSignal, analyze_text

logger = logging.getLogger(__name__)

CLUSTER_WINDOW = timedelta(hours=24)


class IngestResult(dict):
    def __getattr__(self, name):
        try:
            return self[name]
        except KeyError as exc:
            raise AttributeError(name) from exc


def _ensure_utc(ts: datetime) -> datetime:
    if ts.tzinfo is None:
        return ts.replace(tzinfo=timezone.utc)
    return ts.astimezone(timezone.utc)


def _find_cluster(session, label: str, entity: str, published_at: datetime) -> Event | None:
    stmt = (
        select(Event)
        .where(
            Event.event_label == label,
            Event.first_entity == entity,
            Event.is_active.is_(True),
            Event.last_seen >= published_at - CLUSTER_WINDOW,
            Event.first_seen <= published_at + CLUSTER_WINDOW,
        )
        .order_by(Event.last_seen.desc())
        .limit(1)
    )
    return session.execute(stmt).scalar_one_or_none()


def _cluster_impact(label: str, avg_sentiment: float, n_sources: int) -> float:
    return impact_mod.score_impact(label, avg_sentiment, n_sources=n_sources).score


def ingest_item(
    text: str,
    source: str,
    published_at: datetime,
    *,
    url: str | None = None,
    external_id: str | None = None,
    event_hint: str | None = None,
    use_model: bool = True,
    signal: RiskSignal | None = None,
) -> dict[str, Any] | None:
    """Analyze and persist one item. Returns None for duplicates."""
    text = (text or "").strip()
    if not text:
        return None

    if signal is None:
        signal = analyze_text(text, event_hint=event_hint, use_model=use_model)
    ext_id = external_id or f"hash-{signal.text_hash}"

    with get_session() as session:
        return _persist(session, text, source, published_at, url, ext_id, signal)


def ingest_many(items: list[dict]) -> list[dict[str, Any] | None]:
    """Bulk ingestion (backfill). One batched NLP pass, one session.

    Each item: {text, source, published_at, url?, external_id?, event_hint?, use_model?}.
    """
    from src.engine.nlp.pipeline import analyze_batch

    texts = [(i.get("text") or "").strip() for i in items]
    signals = analyze_batch([
        {"text": t, "event_hint": i.get("event_hint"),
         "use_model": bool(i.get("use_model", False))}
        for t, i in zip(texts, items)
    ])
    results: list[dict[str, Any] | None] = []
    with get_session() as session:
        for item, text, signal in zip(items, texts, signals):
            if not text:
                results.append(None)
                continue
            ext_id = item.get("external_id") or f"hash-{signal.text_hash}"
            results.append(_persist(
                session, text, item["source"], item["published_at"],
                item.get("url"), ext_id, signal,
            ))
    return results


def _persist(session, text: str, source: str, published_at: datetime,
             url: str | None, ext_id: str, signal: RiskSignal) -> dict[str, Any] | None:
    dup = session.execute(
        select(Article).where(Article.external_id == ext_id)
    ).scalar_one_or_none()
    if dup is not None:
        return None

    article = Article(
        source=source,
        external_id=ext_id,
        title=text[:512],
        url=url,
        published_at=_ensure_utc(published_at),
    )
    session.add(article)
    session.flush()

    for scope, entity in signal.scope_entity_pairs():
        session.add(Signal(
            article_id=article.id,
            scope=scope,
            entity=entity,
            sentiment_score=signal.sentiment_score,
            event_label=signal.event_label,
            event_confidence=signal.event_confidence,
            impact_score=signal.impact_score,
            model_version=signal.model_versions.get("impact", "unknown"),
            analyzed_at=_ensure_utc(published_at),
        ))

    # items about the same entity and event type within 24h join one cluster;
    # market-scoped text clusters globally under MARKET
    primary = signal.primary_ticker or "MARKET"
    published_at_utc = _ensure_utc(published_at)
    event = _find_cluster(session, signal.event_label, primary, published_at_utc)

    if event is None:
        event = Event(
            event_label=signal.event_label,
            headline=text[:256],
            first_entity=primary,
            first_seen=published_at_utc,
            last_seen=published_at_utc,
            n_sources=1,
            avg_sentiment=signal.sentiment_score,
            avg_impact=signal.impact_score,
            max_impact=signal.impact_score,
        )
        session.add(event)
        session.flush()
        cluster_action = "created"
    else:
        n = event.n_sources + 1
        event.n_sources = n
        event.avg_sentiment = round(
            (event.avg_sentiment * (n - 1) + signal.sentiment_score) / n, 4)
        event.avg_impact = round(
            (event.avg_impact * (n - 1) + signal.impact_score) / n, 4)
        # sqlite returns naive datetimes; normalize before comparing
        event.last_seen = max(_ensure_utc(event.last_seen), published_at_utc)
        corroborated = _cluster_impact(
            event.event_label, event.avg_sentiment, event.n_sources)
        event.max_impact = round(
            max(event.max_impact, signal.impact_score, corroborated), 1)
        cluster_action = "merged"

    return IngestResult(
        article_id=article.id,
        event_id=event.id,
        cluster_action=cluster_action,
        n_sources=event.n_sources,
        sentiment_score=signal.sentiment_score,
        event_label=signal.event_label,
        impact_score=signal.impact_score,
        cluster_max_impact=event.max_impact,
        entities=[e.name for e in signal.entities],
    )
