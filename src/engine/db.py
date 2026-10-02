"""SQLite persistence layer (SQLAlchemy 2.0).

Five tables cover the whole platform:

- ``articles``   raw ingested text (news headlines, tweets, ad-hoc text)
- ``signals``    one structured risk signal per (article, entity) pair —
                 the output of the AI/NLP Risk Engine
- ``events``     lightweight event clusters built from related signals;
                 what Module B subscribes to (event type + impact score)
- ``weights``    Module A rebalance history, one row per ticker per tick
- ``stress_runs`` Module B stress-test results, one row per triggered run
"""

from __future__ import annotations

import json
from datetime import datetime, timezone

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    create_engine,
    desc,
    event,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker

from src.engine.config import settings


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class Article(Base):
    __tablename__ = "articles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source: Mapped[str] = mapped_column(String(32))  # gdelt | seed_news | synthetic_news | synthetic_tweet | adhoc
    external_id: Mapped[str | None] = mapped_column(String(128), unique=True)
    title: Mapped[str] = mapped_column(Text)
    body: Mapped[str | None] = mapped_column(Text, nullable=True)
    url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    published_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    ingested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Signal(Base):
    __tablename__ = "signals"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    article_id: Mapped[int] = mapped_column(ForeignKey("articles.id"), index=True)
    scope: Mapped[str] = mapped_column(String(16))  # company | sector | market
    entity: Mapped[str] = mapped_column(String(64))  # ticker, sector name, or "MARKET"
    sentiment_score: Mapped[float] = mapped_column(Float)  # [-1, 1]
    event_label: Mapped[str] = mapped_column(String(32))
    event_confidence: Mapped[float] = mapped_column(Float)
    impact_score: Mapped[float] = mapped_column(Float)  # [1, 10]
    model_version: Mapped[str] = mapped_column(String(64))
    analyzed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)

    __table_args__ = (
        Index("ix_signals_entity_time", "entity", "analyzed_at"),
        Index("ix_signals_scope_entity_time", "scope", "entity", "analyzed_at"),
    )


class Event(Base):
    __tablename__ = "events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    event_label: Mapped[str] = mapped_column(String(32))
    headline: Mapped[str] = mapped_column(Text)
    first_entity: Mapped[str | None] = mapped_column(String(64), nullable=True)
    first_seen: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    last_seen: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    n_sources: Mapped[int] = mapped_column(Integer, default=1)
    avg_sentiment: Mapped[float] = mapped_column(Float, default=0.0)
    avg_impact: Mapped[float] = mapped_column(Float, default=0.0)
    max_impact: Mapped[float] = mapped_column(Float, default=0.0)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)


class Weight(Base):
    """Module A — portfolio weight of one ticker at one rebalance tick."""

    __tablename__ = "weights"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    ticker: Mapped[str] = mapped_column(String(8))
    weight: Mapped[float] = mapped_column(Float)
    anchor_weight: Mapped[float] = mapped_column(Float)
    sentiment_used: Mapped[float] = mapped_column(Float)


class StressRun(Base):
    """Module B — result of one stress test triggered by a high-impact event."""

    __tablename__ = "stress_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    event_id: Mapped[int | None] = mapped_column(ForeignKey("events.id"), nullable=True)
    event_label: Mapped[str] = mapped_column(String(32))
    event_headline: Mapped[str] = mapped_column(Text)
    impact_score: Mapped[float] = mapped_column(Float)
    triggered_by: Mapped[str] = mapped_column(String(16))  # auto | manual | backfill
    value_before: Mapped[float] = mapped_column(Float)
    value_after: Mapped[float] = mapped_column(Float)
    pnl: Mapped[float] = mapped_column(Float)
    pnl_pct: Mapped[float] = mapped_column(Float)
    details: Mapped[dict] = mapped_column(JSON)  # asset-class P&L, shocks, risk indicators


_engine = None
_session_factory = None


def get_engine():
    global _engine, _session_factory
    if _engine is None:
        settings.db_path.parent.mkdir(parents=True, exist_ok=True)
        _engine = create_engine(
            f"sqlite:///{settings.db_path}",
            connect_args={"check_same_thread": False},
        )
        # WAL mode: the dashboard reads while the scheduler writes.
        @event.listens_for(_engine, "connect")
        def _set_sqlite_pragma(dbapi_connection, _):
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()

        Base.metadata.create_all(_engine)
        _session_factory = sessionmaker(bind=_engine, expire_on_commit=False)
    return _engine


def get_session():
    get_engine()
    assert _session_factory is not None
    return _session_factory()


def dumps(obj) -> str:
    return json.dumps(obj, default=str)
