import json
import logging
from datetime import datetime, timezone
from pathlib import Path

from src.engine.config import settings
from src.engine.universe import TICKERS

logger = logging.getLogger(__name__)

CACHE_TTL_HOURS = 12


def _cache_path(name: str) -> Path:
    settings.cache_dir.mkdir(parents=True, exist_ok=True)
    return settings.cache_dir / name


def _read_cache(name: str, ttl_hours: float) -> dict | None:
    path = _cache_path(name)
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        fetched = datetime.fromisoformat(payload["fetched_at"])
        age_h = (datetime.now(timezone.utc) - fetched).total_seconds() / 3600
        if age_h <= ttl_hours:
            return payload["data"]
    except (json.JSONDecodeError, KeyError, ValueError):
        pass
    return None


def _write_cache(name: str, data: dict) -> None:
    path = _cache_path(name)
    path.write_text(
        json.dumps({"fetched_at": datetime.now(timezone.utc).isoformat(), "data": data}),
        encoding="utf-8",
    )


def market_cap_weights() -> dict[str, float] | None:
    """Cap-weighted anchor for the universe, or None if yfinance is down."""
    cached = _read_cache("market_caps.json", CACHE_TTL_HOURS)
    if cached is None:
        try:
            import yfinance as yf

            caps: dict[str, float] = {}
            tickers = yf.Tickers(" ".join(TICKERS))
            for t in TICKERS:
                cap = (tickers.tickers[t].info or {}).get("marketCap")
                if cap:
                    caps[t] = float(cap)
            if len(caps) < len(TICKERS) * 0.8:
                logger.warning("market caps incomplete (%d/%d)", len(caps), len(TICKERS))
            total = sum(caps.values()) or 1.0
            cached = {t: round(c / total, 6) for t, c in caps.items()}
            _write_cache("market_caps.json", cached)
        except Exception as exc:
            logger.warning("yfinance market caps unavailable: %s", exc)
            return None
    return cached or None


def price_history(days: int = 60) -> dict[str, list[float]] | None:
    """Daily closes per ticker, disk-cached so demos survive offline."""
    name = f"prices_{days}d.json"
    cached = _read_cache(name, CACHE_TTL_HOURS)
    if cached is not None:
        return cached
    try:
        import yfinance as yf

        frame = yf.download(
            tickers=" ".join(TICKERS),
            period=f"{days}d",
            interval="1d",
            auto_adjust=True,
            progress=False,
        )
        closes = frame["Close"]
        data: dict[str, list[float]] = {}
        for t in TICKERS:
            if t in closes:
                series = closes[t].dropna()
                if len(series) > 5:
                    data[t] = [round(float(v), 4) for v in series.tolist()]
        if data:
            _write_cache(name, data)
            return data
    except Exception as exc:
        logger.warning("yfinance price history unavailable: %s", exc)
    return None


def daily_volatility(days: int = 60) -> dict[str, float] | None:
    """Annualized vol per ticker from cached history (for the rebalancer)."""
    data = price_history(days)
    if not data:
        return None
    vols: dict[str, float] = {}
    for ticker, closes in data.items():
        if len(closes) < 10:
            continue
        returns = [closes[i] / closes[i - 1] - 1.0 for i in range(1, len(closes))]
        mean = sum(returns) / len(returns)
        var = sum((r - mean) ** 2 for r in returns) / max(len(returns) - 1, 1)
        vols[ticker] = max((var ** 0.5) * (252 ** 0.5), 0.05)
    return vols or None


def vix_regime_lookup() -> float | None:
    """Latest VIX close for the impact regime factor; None if unavailable."""
    cached = _read_cache("vix_regime.json", 12)
    if cached is not None:
        return cached["vix"] if isinstance(cached, dict) else cached
    try:
        import yfinance as yf

        frame = yf.download("^VIX", period="5d", interval="1d",
                            progress=False, auto_adjust=False)
        close = frame["Close"].squeeze().dropna()
        if len(close):
            val = round(float(close.iloc[-1]), 2)
            _write_cache("vix_regime.json", val)
            return val
    except Exception as exc:
        logger.warning("VIX lookup unavailable: %s", exc)
    return None
