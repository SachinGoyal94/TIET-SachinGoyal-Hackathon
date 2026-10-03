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

    app_name: str = "Financial Risk Intelligence Platform"
    version: str = "1.0.0"
    log_level: str = "INFO"

    db_path: Path = REPO_ROOT / "data" / "db" / "risk.db"
    seed_dir: Path = REPO_ROOT / "data" / "seed"
    cache_dir: Path = REPO_ROOT / "data" / "cache"
    portfolio_path: Path = REPO_ROOT / "data" / "portfolio" / "portfolio.json"
    frontend_dist: Path = REPO_ROOT / "frontend" / "dist"

    models_dir: Path = REPO_ROOT / "models"

    sentiment_model: str = "ProsusAI/finbert"
    event_model: str = "typeform/distilbert-base-uncased-mnli"

    # fine-tuned weights produced by the Kaggle training kernel; used when present
    finetuned_dir: Path = REPO_ROOT / "models" / "finbert-ft"

    @property
    def active_sentiment_model(self) -> str:
        if (self.finetuned_dir / "config.json").is_file():
            return str(self.finetuned_dir)
        return self.sentiment_model

    gdelt_poll_minutes: int = 15
    synthetic_feed_minutes: int = 5
    rebalance_minutes: int = 5

    backfill_on_start: bool = True
    newsapi_key: str = ""


settings = Settings()

# shared HF cache for the engine, scripts and the Docker image
os.environ.setdefault("HF_HOME", str(settings.models_dir))
