"""FastAPI application factory: mounts the versioned API and, when a built
frontend bundle is present, serves the React SPA from the same process so the
whole platform runs as a single service (one port, one container)."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from src.engine import __version__
from src.engine.api.routes import api_router, health_snapshot
from src.engine.config import settings

logging.basicConfig(
    level=getattr(logging, settings.log_level.upper(), logging.INFO),
    format="%(asctime)s %(levelname)-7s %(name)s | %(message)s",
)
logger = logging.getLogger("engine")


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting %s v%s", settings.app_name, settings.version)
    settings.db_path.parent.mkdir(parents=True, exist_ok=True)
    settings.cache_dir.mkdir(parents=True, exist_ok=True)
    app.state.ready = False
    # Data seeding, model warm-up and scheduler startup are wired in later
    # milestones; M1 only guarantees a green API surface.
    app.state.ready = True
    yield
    logger.info("Engine shut down")


app = FastAPI(title=settings.app_name, version=__version__, lifespan=lifespan)

# CORS is only needed for the Vite dev server (http://localhost:5173) during
# development; in production the SPA is served from this same origin.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health", include_in_schema=False, tags=["ops"])
def health() -> dict:
    """Plain ops healthcheck (used by Docker healthchecks / uptime probes)."""
    return {"status": "ok", "version": __version__}


app.include_router(api_router, prefix="/api")


# --- Single-page app serving -------------------------------------------------
# The React bundle (frontend/dist) is produced either by the Docker
# multi-stage build or a local `npm run build`; when present, the engine
# serves it so the jury reaches both UI and API on one port.
_dist = settings.frontend_dist
if (_dist / "assets").is_dir() and (_dist / "index.html").is_file():
    app.mount("/assets", StaticFiles(directory=_dist / "assets"), name="assets")

    @app.get("/{full_path:path}", include_in_schema=False)
    async def spa(full_path: str) -> FileResponse:
        candidate = (_dist / full_path).resolve()
        if full_path and candidate.is_file() and candidate.is_relative_to(_dist.resolve()):
            return FileResponse(candidate)
        return FileResponse(_dist / "index.html")

    logger.info("Serving frontend bundle from %s", _dist)
else:
    logger.info("No frontend bundle found — API-only mode")


def build_health_snapshot() -> dict:
    return health_snapshot()
