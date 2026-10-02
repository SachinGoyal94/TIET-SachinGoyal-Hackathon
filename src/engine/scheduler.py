import logging
from datetime import datetime, timedelta, timezone

from apscheduler.schedulers.background import BackgroundScheduler
from sqlalchemy import select, update

from src.engine.config import settings
from src.engine.db import Event, get_session
from src.engine.ingest.gdelt import poll_and_ingest
from src.engine.ingest.synthetic import generate_item
from src.engine.ingest.service import ingest_item
from src.engine.modules.rebalance_service import rebalance_tick

logger = logging.getLogger(__name__)

_scheduler: BackgroundScheduler | None = None


def _auto_stress() -> None:
    try:
        from src.engine.api.routes import auto_stress_check

        result = auto_stress_check()
        if result:
            logger.warning("AUTO STRESS TRIGGERED: %s impact %.1f -> pnl %.1f%%",
                           result["event_label"], result["impact_score"],
                           result["pnl_pct"])
    except Exception:
        logger.exception("auto stress check failed")


def _gdelt_job() -> None:
    try:
        stored = poll_and_ingest()
        logger.info("gdelt poll: %d new items", stored)
        _auto_stress()
    except Exception:
        logger.exception("gdelt poll failed")


def _synthetic_job() -> None:
    try:
        rng = __import__("random").Random()
        item = generate_item(rng)
        ingest_item(text=item.text, source=item.source,
                    published_at=item.published_at,
                    event_hint=item.event_label)
        _auto_stress()
    except Exception:
        logger.exception("synthetic feed failed")


def _rebalance_job() -> None:
    try:
        weights = rebalance_tick()
        top = sorted(weights.items(), key=lambda kv: kv[1], reverse=True)[:3]
        logger.info("rebalance tick done, top: %s", top)
    except Exception:
        logger.exception("rebalance tick failed")


def _deactivate_events_job() -> None:
    try:
        cutoff = datetime.now(timezone.utc) - timedelta(hours=48)
        with get_session() as s:
            s.execute(update(Event).where(Event.last_seen < cutoff)
                      .values(is_active=False))
    except Exception:
        logger.exception("event deactivation failed")


def start() -> BackgroundScheduler:
    global _scheduler
    if _scheduler is not None:
        return _scheduler
    _scheduler = BackgroundScheduler(timezone="UTC")
    _scheduler.add_job(_gdelt_job, "interval",
                       minutes=settings.gdelt_poll_minutes, id="gdelt_poll",
                       next_run_time=datetime.now(timezone.utc))
    _scheduler.add_job(_synthetic_job, "interval",
                       minutes=settings.synthetic_feed_minutes, id="synthetic_feed",
                       next_run_time=datetime.now(timezone.utc))
    _scheduler.add_job(_rebalance_job, "interval",
                       minutes=settings.rebalance_minutes, id="rebalance_tick",
                       next_run_time=datetime.now(timezone.utc))
    _scheduler.add_job(_deactivate_events_job, "interval", minutes=30, id="event_expiry")
    _scheduler.start()
    logger.info("scheduler started (gdelt %dmin, synthetic %dmin, rebalance %dmin)",
                settings.gdelt_poll_minutes, settings.synthetic_feed_minutes,
                settings.rebalance_minutes)
    return _scheduler


def stop() -> None:
    global _scheduler
    if _scheduler is not None:
        _scheduler.shutdown(wait=False)
        _scheduler = None
