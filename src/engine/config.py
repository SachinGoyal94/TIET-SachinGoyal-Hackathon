"""Central application configuration.

All knobs are environment-overridable with the ``RISK_`` prefix (e.g.
``RISK_GDELT_POLL_MINUTES=10``) or via a ``.env`` file at the repo root.
The platform is designed to run with **no API keys** — every integration
used on the default path (GDELT, yfinance, local HuggingFace models) is
keyless; an optional NewsAPI key can be set for an extra live source.
"""

from __future__ import annotations

import os
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=REPO_ROOT / ".env",
        env_prefix="RISK_",
        extra="ignore",
    )

    # --- Identity ---------------------------------------------------------
    app_name: str = "Financial Risk Intelligence Platform"
    version: str = "1.0.0"
    log_level: str = "INFO"

    # --- Filesystem -------------------------------------------------------
    db_path: Path = REPO_ROOT / "data" / "db" / "risk.db"
    seed_dir: Path = REPO_ROOT / "data" / "seed"
    cache_dir: Path = REPO_ROOT / "data" / "cache"
    portfolio_path: Path = REPO_ROOT / "data" / "portfolio" / "portfolio.json"
    frontend_dist: Path = REPO_ROOT / "frontend" / "dist"

    # HuggingFace model cache — pre-baked into the Docker image at build
    # time so the jury's first run never downloads model weights.
    models_dir: Path = REPO_ROOT / "models"

    # --- Models -----------------------------------------------------------
    sentiment_model: str = "ProsusAI/finbert"
    event_model: str = "typeform/distilbert-base-uncased-mnli"

    # --- Scheduler cadence (minutes) ---------------------------------------
    gdelt_poll_minutes: int = 15
    synthetic_feed_minutes: int = 5
    rebalance_minutes: int = 5

    # --- Behaviour ----------------------------------------------------------
    backfill_on_start: bool = True

    # --- Optional extra source (off by default; platform is keyless) -------
    newsapi_key: str = ""


settings = Settings()

# Make the local model cache the default HuggingFace home for every process
# (engine, backfill script) before transformers is imported anywhere.
os.environ.setdefault("HF_HOME", str(settings.models_dir))
