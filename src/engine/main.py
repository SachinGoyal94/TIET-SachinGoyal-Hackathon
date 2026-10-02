import logging
import threading
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from src.engine import __version__
from src.engine.api.routes import api_router, auto_stress_check
from src.engine.config import settings

logging.basicConfig(
    level=getattr(logging, settings.log_level.upper(), logging.INFO),
    format="%(asctime)s %(levelname)-7s %(name)s | %(message)s",
)
logger = logging.getLogger("engine")


def _startup_bootstrap() -> None:
    """Runs in a background thread so the API answers immediately."""
    try:
        from src.engine.db import get_session
        from src.engine.nlp import sentiment
        from src.engine.scheduler import start

        sentiment.load_model()
        _set_flag("models_loaded", True)

        if settings.backfill_on_start:
            from src.scripts.backfill import has_data, main as backfill_main

            if not has_data():
                logger.info("empty database, running backfill (first boot)...")
                backfill_main()
            else:
                logger.info("database already populated, skipping backfill")

        _set_flag("rebalancer_ready", True)
        _set_flag("stress_ready", True)
        _set_flag("ready", True)
        start()
        logger.info("engine ready")
    except Exception:
        logger.exception("startup bootstrap failed")


_flags: dict[str, bool] = {}


def _set_flag(name: str, value: bool) -> None:
    _flags[name] = value


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting %s v%s", settings.app_name, settings.version)
    settings.db_path.parent.mkdir(parents=True, exist_ok=True)
    settings.cache_dir.mkdir(parents=True, exist_ok=True)
    _flags.clear()
    _flags.update({"ready": False, "models_loaded": False,
                   "rebalancer_ready": False, "stress_ready": False})
    app.state.flags = _flags

    threading.Thread(target=_startup_bootstrap, name="bootstrap", daemon=True).start()
    yield
    from src.engine.scheduler import stop

    stop()
    logger.info("Engine shut down")


app = FastAPI(title=settings.app_name, version=__version__, lifespan=lifespan)

# CORS only matters for the Vite dev server; in prod the SPA shares this origin
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health", include_in_schema=False, tags=["ops"])
def health() -> dict:
    return {"status": "ok" if _flags.get("ready") else "initializing",
            "version": __version__}


app.include_router(api_router, prefix="/api")

# serve the built React bundle when present (single port for UI + API)
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
    logger.info("No frontend bundle found, API-only mode")
