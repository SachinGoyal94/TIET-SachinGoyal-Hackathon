import logging
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import desc, func, select

from src.engine import __version__
from src.engine.config import settings
from src.engine.db import Article, Event, Signal, StressRun, Weight, get_session
from src.engine.ingest.service import ingest_item
from src.engine.modules.rebalance_service import weights_snapshot
from src.engine.modules.stress import run_stress
from src.engine.universe import SECTORS, TICKERS, UNIVERSE

logger = logging.getLogger(__name__)

api_router = APIRouter()


@api_router.get("/health", tags=["ops"])
def health(request: Request) -> dict:
    flags = getattr(request.app.state, "flags", {})
    ready = bool(flags.get("ready"))
    return {
        "status": "ok" if ready else "initializing",
        "version": __version__,
        "ready": ready,
        "models_loaded": bool(flags.get("models_loaded")),
        "components": {
            "risk_engine": ready,
            "rebalancer_module": bool(flags.get("rebalancer_ready")),
            "stress_testing_module": bool(flags.get("stress_ready")),
        },
    }


# --- Risk engine --------------------------------------------------------------

class AnalyzeRequest(BaseModel):
    text: str = Field(min_length=3, max_length=5000)


@api_router.post("/analyze", tags=["risk-engine"])
def analyze(req: AnalyzeRequest) -> dict:
    """Text in, structured risk signal out. Also stored in the feed."""
    result = ingest_item(
        text=req.text, source="adhoc", published_at=datetime.now(timezone.utc))
    if result is None:
        raise HTTPException(status_code=409, detail="duplicate text ignored")
    return result


@api_router.get("/signals", tags=["risk-engine"])
def signals(limit: int = 100, entity: str | None = None,
            scope: str | None = None) -> dict:
    stmt = select(Signal).order_by(desc(Signal.analyzed_at)).limit(min(limit, 500))
    if entity:
        stmt = stmt.where(Signal.entity == entity)
    if scope:
        stmt = stmt.where(Signal.scope == scope)
    with get_session() as s:
        rows = s.execute(stmt).scalars().all()
        return {
            "count": len(rows),
            "signals": [
                {
                    "id": r.id, "scope": r.scope, "entity": r.entity,
                    "sentiment_score": r.sentiment_score,
                    "event_label": r.event_label,
                    "event_confidence": r.event_confidence,
                    "impact_score": r.impact_score,
                    "analyzed_at": r.analyzed_at,
                } for r in rows
            ],
        }


@api_router.get("/events", tags=["risk-engine"])
def events(active_only: bool = True, limit: int = 50) -> dict:
    stmt = select(Event).order_by(desc(Event.last_seen)).limit(min(limit, 200))
    if active_only:
        stmt = stmt.where(Event.is_active)
    with get_session() as s:
        rows = s.execute(stmt).scalars().all()
        return {
            "count": len(rows),
            "events": [
                {
                    "id": r.id, "event_label": r.event_label,
                    "headline": r.headline, "first_entity": r.first_entity,
                    "first_seen": r.first_seen, "last_seen": r.last_seen,
                    "n_sources": r.n_sources,
                    "avg_sentiment": r.avg_sentiment,
                    "avg_impact": r.avg_impact,
                    "max_impact": r.max_impact,
                    "is_active": r.is_active,
                } for r in rows
            ],
        }


@api_router.get("/universe", tags=["risk-engine"])
def universe() -> dict:
    return {
        "tickers": [
            {"ticker": c.ticker, "name": c.name, "sector": c.sector}
            for c in UNIVERSE
        ],
        "sectors": list(SECTORS),
    }


@api_router.get("/stats", tags=["risk-engine"])
def stats() -> dict:
    with get_session() as s:
        day_ago = datetime.now(timezone.utc) - timedelta(hours=24)
        return {
            "articles": s.execute(select(func.count(Article.id))).scalar() or 0,
            "signals": s.execute(select(func.count(Signal.id))).scalar() or 0,
            "active_events": s.execute(
                select(func.count(Event.id)).where(Event.is_active)).scalar() or 0,
            "articles_24h": s.execute(
                select(func.count(Article.id)).where(Article.published_at >= day_ago)).scalar() or 0,
            "stress_runs": s.execute(select(func.count(StressRun.id))).scalar() or 0,
        }


# --- Module A -------------------------------------------------------------------

@api_router.get("/rebalance/weights", tags=["module-a"])
def rebalance_weights() -> dict:
    return weights_snapshot()


@api_router.get("/rebalance/history", tags=["module-a"])
def rebalance_history(hours: int = 168) -> dict:
    cutoff = datetime.now(timezone.utc) - timedelta(hours=min(hours, 24 * 90))
    with get_session() as s:
        rows = s.execute(
            select(Weight).where(Weight.ts >= cutoff).order_by(Weight.ts)
        ).scalars().all()
    by_ts: dict[datetime, dict] = {}
    for r in rows:
        by_ts.setdefault(r.ts, {"ts": r.ts, "weights": {}})
        by_ts[r.ts]["weights"][r.ticker] = round(r.weight, 5)
    return {"ticks": list(by_ts.values())}


# --- Module B -------------------------------------------------------------------

class StressRequest(BaseModel):
    event_id: int | None = None
    scenario: str | None = None


AUTO_TRIGGER_LABEL = "Geopolitical"
AUTO_TRIGGER_IMPACT = 7.0


def _run_and_store(event_id: int | None, label: str, headline: str,
                   impact: float, triggered_by: str) -> dict:
    result = run_stress(load_portfolio(), label, impact)
    with get_session() as s:
        run = StressRun(
            ts=datetime.now(timezone.utc),
            event_id=event_id,
            event_label=label, event_headline=headline, impact_score=impact,
            triggered_by=triggered_by,
            value_before=result["value_before"], value_after=result["value_after"],
            pnl=result["pnl"], pnl_pct=result["pnl_pct"], details=result,
        )
        s.add(run)
        s.flush()
        result["run_id"] = run.id
        result["triggered_by"] = triggered_by
    return result


def load_portfolio() -> dict:
    import json

    return json.loads(settings.portfolio_path.read_text(encoding="utf-8"))


@api_router.get("/portfolio", tags=["module-b"])
def portfolio() -> dict:
    pf = load_portfolio()
    by_class: dict[str, dict] = {}
    for pos in pf["positions"]:
        notional = float(pos.get("notional") or pos.get("value") or 0.0)
        agg = by_class.setdefault(pos["asset_class"], {"count": 0, "notional": 0.0})
        agg["count"] += 1
        agg["notional"] += notional
    return {
        "portfolio_name": pf["portfolio_name"],
        "base_currency": pf["base_currency"],
        "total_notional": sum(a["notional"] for a in by_class.values()),
        "by_asset_class": by_class,
        "positions": pf["positions"],
    }


@api_router.post("/stress/run", tags=["module-b"])
def stress_run(req: StressRequest) -> dict:
    if req.scenario:
        from src.engine.modules.scenarios import SCENARIOS

        if req.scenario not in SCENARIOS:
            raise HTTPException(status_code=404, detail="unknown scenario")
        result = _run_and_store(None, req.scenario,
                                SCENARIOS[req.scenario]["description"],
                                10.0, "scenario")
        return result

    with get_session() as s:
        if req.event_id is not None:
            ev = s.get(Event, req.event_id)
            if ev is None:
                raise HTTPException(status_code=404, detail="event not found")
        else:
            ev = s.execute(
                select(Event)
                .where(Event.is_active)
                .order_by(desc(Event.max_impact))
                .limit(1)
            ).scalar_one_or_none()
            if ev is None:
                raise HTTPException(status_code=409, detail="no events to stress")
        ev_id, label, headline, impact = ev.id, ev.event_label, ev.headline, ev.max_impact
    return _run_and_store(ev_id, label, headline, impact, "manual")


@api_router.get("/stress/scenarios", tags=["module-b"])
def stress_scenarios() -> dict:
    from src.engine.modules.scenarios import SCENARIOS

    return {
        "count": len(SCENARIOS),
        "scenarios": [
            {"name": name, "family": s["family"], "description": s["description"],
             "source": s["source"], "shocks": s["shocks"]}
            for name, s in SCENARIOS.items()
        ],
    }


class ReverseStressRequest(BaseModel):
    scenario: str


@api_router.post("/stress/reverse", tags=["module-b"])
def stress_reverse(req: ReverseStressRequest) -> dict:
    from src.engine.modules.stress import reverse_stress

    try:
        return reverse_stress(load_portfolio(), req.scenario)
    except KeyError:
        raise HTTPException(status_code=404, detail="unknown scenario")


def auto_stress_check() -> dict | None:
    """Runs after ingestion cycles when the trigger rule fires
    (Geopolitical, impact > 7) and this event has not been stressed yet."""
    with get_session() as s:
        ev = s.execute(
            select(Event)
            .where(Event.is_active, Event.event_label == AUTO_TRIGGER_LABEL,
                   Event.max_impact > AUTO_TRIGGER_IMPACT)
            .order_by(desc(Event.max_impact))
            .limit(1)
        ).scalar_one_or_none()
        if ev is None:
            return None
        already = s.execute(
            select(func.count(StressRun.id)).where(
                StressRun.event_id == ev.id, StressRun.triggered_by == "auto")
        ).scalar() or 0
        if already:
            return None
        ev_id, label, headline, impact = ev.id, ev.event_label, ev.headline, ev.max_impact
    return _run_and_store(ev_id, label, headline, impact, "auto")


@api_router.get("/stress/runs", tags=["module-b"])
def stress_runs(limit: int = 20) -> dict:
    with get_session() as s:
        rows = s.execute(
            select(StressRun).order_by(desc(StressRun.ts)).limit(min(limit, 100))
        ).scalars().all()
        return {
            "count": len(rows),
            "runs": [
                {
                    "id": r.id, "ts": r.ts, "event_id": r.event_id,
                    "event_label": r.event_label, "event_headline": r.event_headline,
                    "impact_score": r.impact_score, "triggered_by": r.triggered_by,
                    "value_before": r.value_before, "value_after": r.value_after,
                    "pnl": r.pnl, "pnl_pct": r.pnl_pct,
                } for r in rows
            ],
        }


@api_router.get("/stress/latest", tags=["module-b"])
def stress_latest() -> dict:
    with get_session() as s:
        run = s.execute(
            select(StressRun).order_by(desc(StressRun.ts)).limit(1)
        ).scalar_one_or_none()
        if run is None:
            return {"run": None}
        return {
            "run": {
                "id": run.id, "ts": run.ts, "event_id": run.event_id,
                "event_label": run.event_label, "event_headline": run.event_headline,
                "impact_score": run.impact_score, "triggered_by": run.triggered_by,
                "value_before": run.value_before, "value_after": run.value_after,
                "pnl": run.pnl, "pnl_pct": run.pnl_pct,
                "details": run.details,
            }
        }


@api_router.get("/tickers", tags=["risk-engine"])
def tickers() -> dict:
    return {"tickers": list(TICKERS)}
