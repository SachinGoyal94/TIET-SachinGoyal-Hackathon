from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from src.engine.ingest.service import ingest_many


@pytest.fixture(scope="module")
def client():
    # keep tests hermetic: no model loads, no backfill, no scheduler
    from src.engine import main as engine_main

    mp = pytest.MonkeyPatch()

    def fake_bootstrap():
        engine_main._flags.update({
            "ready": True, "models_loaded": True,
            "rebalancer_ready": True, "stress_ready": True,
        })

    mp.setattr(engine_main, "_startup_bootstrap", fake_bootstrap)
    try:
        with TestClient(engine_main.app) as c:
            yield c
    finally:
        mp.undo()


@pytest.fixture(scope="module")
def seeded_db():
    now = datetime.now(timezone.utc)
    items = []
    for k in range(6):
        items.append({
            "text": f"Apple guidance update number {k} for the quarter",
            "source": "test", "published_at": now - timedelta(hours=k),
            "event_hint": "Macroeconomic", "use_model": False,
        })
    ingest_many(items)
    return None


def test_health(client):
    res = client.get("/api/health")
    assert res.status_code == 200
    body = res.json()
    assert body["status"] == "ok"
    assert body["components"]["rebalancer_module"] is True


def test_analyze_route(client, monkeypatch):
    from src.engine.nlp.pipeline import RiskSignal
    from src.engine.nlp.impact import score_impact

    def fake_analyze(text, event_hint=None, use_model=True):
        return RiskSignal(
            text=text, text_hash="x", sentiment_score=-0.5,
            event_label="Geopolitical", event_confidence=0.8,
            impact_score=score_impact("Geopolitical", -0.5).score,
            impact_breakdown=score_impact("Geopolitical", -0.5),
            entities=[], model_versions={"impact": "test"},
        )

    monkeypatch.setattr("src.engine.ingest.service.analyze_text", fake_analyze)
    res = client.post("/api/analyze", json={"text": "sanctions hit global trade"})
    assert res.status_code == 200
    body = res.json()
    assert body["event_label"] == "Geopolitical"
    assert body["impact_score"] >= 8.0


def test_signals_route(client, seeded_db):
    res = client.get("/api/signals?limit=10")
    assert res.status_code == 200
    assert res.json()["count"] > 0


def test_events_route(client, seeded_db):
    res = client.get("/api/events?active_only=true")
    assert res.status_code == 200
    assert res.json()["count"] > 0


def test_universe_route(client):
    res = client.get("/api/universe")
    assert res.status_code == 200
    assert len(res.json()["tickers"]) == 14


def test_portfolio_route(client):
    res = client.get("/api/portfolio")
    assert res.status_code == 200
    body = res.json()
    assert body["total_notional"] > 1e9
    assert {"loan", "bond", "derivative", "equity"} <= set(body["by_asset_class"])


def test_stress_flow(client, seeded_db):
    res = client.post("/api/stress/run", json={})
    assert res.status_code == 200
    body = res.json()
    assert body["value_before"] > 0
    assert body["pnl"] < 0

    latest = client.get("/api/stress/latest").json()["run"]
    assert latest is not None
    assert latest["details"]["monte_carlo"]["var95"] > 0

    runs = client.get("/api/stress/runs").json()
    assert runs["count"] >= 1


def test_rebalance_endpoints(client, seeded_db):
    # no weights stored yet -> empty snapshot, history empty
    snap = client.get("/api/rebalance/weights")
    assert snap.status_code == 200
    hist = client.get("/api/rebalance/history")
    assert hist.status_code == 200
