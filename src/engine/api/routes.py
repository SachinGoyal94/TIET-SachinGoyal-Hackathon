"""API routes. Endpoints grow with each milestone; every response is JSON and
typed by the schemas in :mod:`src.engine.api.schemas`."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Request

from src.engine import __version__

logger = logging.getLogger(__name__)

api_router = APIRouter()


@api_router.get("/health", tags=["ops"])
def health(request: Request) -> dict:
    """Detailed readiness snapshot: models, database, ingestion state."""
    ready = bool(getattr(request.app.state, "ready", False))
    return {
        "status": "ok" if ready else "initializing",
        "version": __version__,
        "ready": ready,
        "models_loaded": bool(getattr(request.app.state, "models_loaded", False)),
        "components": {
            "risk_engine": ready,
            "rebalancer_module": bool(getattr(request.app.state, "rebalancer_ready", False)),
            "stress_testing_module": bool(getattr(request.app.state, "stress_ready", False)),
        },
    }


def health_snapshot() -> dict:  # pragma: no cover - used by main only
    return {"status": "ok", "version": __version__}
