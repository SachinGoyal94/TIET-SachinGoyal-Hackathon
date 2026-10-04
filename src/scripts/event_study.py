"""Event-study engine: do our risk signals line up with realized market moves?

Methodology per the event-study literature:
- Timestamp alignment: news between prior close and today's open (pre-open /
  after-hours) maps to the first tradable day; intraday news maps to the
  same day's close-to-close return.
- Abnormal returns: market-adjusted (minus SPY) and sector-adjusted
  (minus the ticker's sector proxy) — no estimation window needed at this
  universe size.
- Windows: CAR over [0,0] and [0,+1] to catch slow diffusion.
- Statistics: cross-sectional t-test on mean CAR, nonparametric sign test,
  and directional hit rate against the 53-55% bar the literature considers
  meaningful at a daily horizon.
"""

from __future__ import annotations

import argparse
import json
import logging
import math
from datetime import datetime, time as dtime, timezone

import numpy as np
from sqlalchemy import select

from src.engine.config import settings
from src.engine.db import Event, get_session
from src.engine.market_data import _cache_path, _read_cache, _write_cache
from src.engine.universe import BY_TICKER, TICKERS

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)-7s %(name)s | %(message)s")
log = logging.getLogger("event-study")

SECTOR_ETF = {
    "Technology": "XLK", "Financials": "XLF", "Energy": "XLE",
    "Consumer": "XLP", "Industrials": "XLI",
}
MARKET_ETF = "SPY"


def load_aligned_prices(days: int = 120,
                        start: str | None = None,
                        end: str | None = None) -> dict[str, tuple[list[str], list[float]]]:
    """Daily closes (with dates) for the universe plus market/sector ETFs."""
    name = f"event_study_prices_{days}d_{start}_{end}.json"
    cached = _read_cache(name, 168)
    if cached:
        return {t: (d, c) for t, (d, c) in cached.items()}
    try:
        import yfinance as yf

        symbols = list(TICKERS) + [MARKET_ETF] + sorted(set(SECTOR_ETF.values()))
        kwargs = ({"period": f"{days}d"} if not start
                  else {"start": start, "end": end or "2021-12-31"})
        frame = yf.download(tickers=" ".join(symbols), interval="1d",
                            auto_adjust=True, progress=False, **kwargs)
        closes = frame["Close"]
        data: dict[str, tuple[list[str], list[float]]] = {}
        for sym in symbols:
            if sym not in closes:
                continue
            series = closes[sym].dropna()
            if len(series) > 10:
                data[sym] = ([str(i.date()) for i in series.index],
                             [round(float(v), 4) for v in series.tolist()])
        _write_cache(name, data)
        return data
    except Exception as exc:  # noqa: BLE001
        log.warning("price download unavailable: %s", exc)
        return {}


def first_tradable_day(dates: list[str], published_utc: datetime) -> int | None:
    """Index of the first trading day the news could be acted on.

    News before 20:25 UTC (4:25pm ET, just before close) acts on the same
    session; later news acts on the next session.
    """
    cutoff = dtime(20, 25)
    pub_date = published_utc.date()
    for i, d in enumerate(dates):
        day = datetime.fromisoformat(d).replace(tzinfo=timezone.utc)
        day = day.date()
        if day < pub_date:
            continue
        if day == pub_date and published_utc.time() < cutoff:
            return i
        return i + 1 if i + 1 < len(dates) else None
    return None


def car(events_close: list[float], etf_close: list[float],
        idx: int, window: int) -> float:
    """Market-adjusted cumulative abnormal return around the first tradable day.

    window=0 measures the first tradable session itself: close[idx] vs
    close[idx-1]. window=1 spans two sessions (the [0,+1] CAR).
    """
    base = idx - 1
    if base < 0 or idx + window >= len(events_close):
        return float("nan")
    r_stock = events_close[idx + window] / events_close[base] - 1.0
    j = min(idx + window, len(etf_close) - 1)
    r_etf = etf_close[j] / etf_close[base] - 1.0
    return r_stock - r_etf


def t_stat(xs: list[float]) -> float:
    a = np.array([x for x in xs if not math.isnan(x)])
    if len(a) < 5 or a.std(ddof=1) == 0:
        return float("nan")
    return float(a.mean() / (a.std(ddof=1) / math.sqrt(len(a))))


def sign_test(xs: list[float]) -> float:
    """Two-sided binomial sign test p-value for median zero."""
    a = [x for x in xs if not math.isnan(x)]
    pos = sum(1 for x in a if x > 0)
    n = len(a)
    if n < 5:
        return float("nan")
    from math import comb

    p_two_sided = sum(comb(n, k) for k in range(min(pos, n - pos) + 1)) / 2 ** n * 2
    return min(1.0, p_two_sided)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--days", type=int, default=120)
    parser.add_argument("--start", type=str, default=None, help="price window start (YYYY-MM-DD)")
    parser.add_argument("--end", type=str, default=None, help="price window end")
    parser.add_argument("--source", type=str, default=None,
                        help="filter events by first_source, e.g. kaggle_hist")
    args = parser.parse_args()

    prices = load_aligned_prices(args.days, args.start, args.end)

    with get_session() as s:
        stmt = select(Event).where(Event.first_entity.in_(TICKERS))
        if args.source:
            stmt = stmt.where(Event.first_source == args.source)
        events = s.execute(stmt).scalars().all()

    rows = []
    for ev in events:
        ticker = ev.first_entity
        if ticker not in BY_TICKER or ticker not in prices:
            continue
        dates, closes = prices[ticker]
        etf = SECTOR_ETF.get(BY_TICKER[ticker].sector, MARKET_ETF)
        if etf not in prices or MARKET_ETF not in prices:
            continue
        idx = first_tradable_day(dates, ev.last_seen)
        if idx is None or idx < 1:
            continue
        sector_ar = car(closes, prices[etf][1], idx, 0)
        market_ar = car(closes, prices[MARKET_ETF][1], idx, 0)
        sector_car1 = car(closes, prices[etf][1], idx, 1)
        if any(math.isnan(v) for v in (sector_ar, market_ar, sector_car1)):
            continue
        signed_agree = 1 if (np.sign(ev.avg_sentiment) == np.sign(sector_ar)
                             and ev.avg_sentiment != 0) else 0
        rows.append({
            "ticker": ticker, "label": ev.event_label,
            "impact": ev.max_impact, "sentiment": ev.avg_sentiment,
            "sector_ar": sector_ar, "market_ar": market_ar, "car_01": sector_car1,
            "sign_agree": signed_agree,
        })

    if not rows:
        log.warning("no matched events with prices; rerun after the historical backfill")
        return

    def group_stats(key):
        out = {}
        for g in sorted({r[key] for r in rows}):
            subset = [r for r in rows if r[key] == g]
            out[str(g)] = {
                "n": len(subset),
                "mean_sector_ar_bps": round(float(np.mean([r["sector_ar"] for r in subset])) * 1e4, 1),
                "t_stat": round(t_stat([r["sector_ar"] for r in subset]), 2),
                "hit_rate": round(float(np.mean([r["sign_agree"] for r in subset])), 3),
            }
        return out

    all_sector_ar = [r["sector_ar"] for r in rows]
    sentiment_aligned = [r["sector_ar"] * np.sign(r["sentiment"]) for r in rows
                         if r["sentiment"] != 0]

    def conditional_hit(threshold: float) -> float | None:
        subset = [r for r in rows if abs(r["sentiment"]) >= threshold]
        if len(subset) < 20:
            return None
        return round(float(np.mean([r["sign_agree"] for r in subset])), 3)

    strong = [r for r in rows if abs(r["sentiment"]) >= 0.5]

    result = {
        "source_filter": args.source or "all",
        "events_matched": len(rows),
        "overall": {
            "mean_sector_ar_bps": round(float(np.mean(all_sector_ar)) * 1e4, 1),
            "t_stat_sector_ar": round(t_stat(all_sector_ar), 2),
            "sign_test_p": round(sign_test(all_sector_ar), 3),
            "sentiment_direction_hit_rate": round(
                float(np.mean([r["sign_agree"] for r in rows])), 3),
            "hit_rate_sentiment_gt_02": conditional_hit(0.2),
            "hit_rate_sentiment_gt_05": conditional_hit(0.5),
            "strong_sentiment_n": len(strong),
            "impact_signal_ic": round(float(np.corrcoef(
                [r["impact"] for r in rows],
                [abs(r["sector_ar"]) for r in rows])[0, 1]), 3)
            if len(rows) > 5 else None,
            "sentiment_scaled_ar_bps": round(float(np.mean(sentiment_aligned)) * 1e4, 1)
            if sentiment_aligned else None,
        },
        "by_event_label": group_stats("label"),
        "by_impact_band": group_stats("impact"),
        "bar": "literature bar for daily-horizon meaningfulness: 53-55% directional hit rate",
        "note": "synthetic-history rows carry random timestamps (no expected signal); "
                "filter with --source gdelt_hist (or gdelt) for the live read",
    }
    log.info("event study: %s", json.dumps(result, indent=2))
    out = settings.cache_dir / "event_study.json"
    out.write_text(json.dumps(result, indent=2), encoding="utf-8")
    log.info("saved to %s", out)


if __name__ == "__main__":
    main()
