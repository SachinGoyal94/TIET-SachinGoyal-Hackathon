"""Empirical calibration of the signal model (improvement #1).

Replaces hand-set constants with coefficients fitted on the event dataset
(FNSPID 2009-2023), with a temporal train/test split.

Two models:
  1. Impact: OLS of log(1 + |sector_ar| bps) on abs_sent, vix, label dummies
     -> the fitted label dummy coefficients ARE the calibrated severities
  2. Direction: LPM of (sector_ar > 0) on signed_sent, abs_sent, vix
     -> validates the tilt's directional signal

Temporal split: train <= 2021-06-30, test > 2021-06-30. HAC errors.

Usage: python -m src.scripts.calibrate_signal_model
"""

from __future__ import annotations

import json
import logging

import numpy as np
import pandas as pd
import statsmodels.api as sm

from src.engine.config import settings

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)-7s %(name)s | %(message)s")
log = logging.getLogger("calibrate")

LABELS = ("positive", "negative", "neutral")  # for the direction model check
EVENT_LABELS = ("Geopolitical", "Macroeconomic", "Credit Event",
                "Merger/Acquisition", "Product Launch", "Other")


def load_events() -> pd.DataFrame:
    df = pd.read_csv('data/cache/event_rows.csv')
    df['dt'] = pd.to_datetime(df['date'], utc=True).dt.date
    df['abs_ar'] = df['sector_ar'].abs()
    df['log_abs_ar'] = np.log1p(df['abs_ar'] * 1e4)
    df['abs_sent'] = df['sentiment'].abs()
    return df


def add_vix(df: pd.DataFrame) -> pd.DataFrame:
    import yfinance as yf
    vix = yf.download('^VIX', start='2009-01-01', end='2024-02-01',
                      progress=False, auto_adjust=False)
    vix_by_date = {i.date(): float(v) for i, v in vix['Close'].squeeze().items()}

    def vix_at(d):
        for back in range(0, 7):
            probe = d - pd.Timedelta(days=back)
            if probe in vix_by_date:
                return vix_by_date[probe]
        return 20.0

    df['vix'] = [vix_at(d) for d in df['dt']]
    return df


def macro_f1(y_true: np.ndarray, y_pred: np.ndarray, classes: tuple) -> float:
    f1s = []
    for c in classes:
        tp = np.sum((y_pred == c) & (y_true == c))
        fp = np.sum((y_pred == c) & (y_true != c))
        fn = np.sum((y_pred != c) & (y_true == c))
        p = tp / (tp + fp) if tp + fp else 0.0
        r = tp / (tp + fn) if tp + fn else 0.0
        f1s.append(2 * p * r / (p + r) if p + r else 0.0)
    return round(float(np.mean(f1s)), 4)


def fit_impact_ols(train: pd.DataFrame, test: pd.DataFrame) -> dict:
    """OLS of log(1+|CAR| bps) on abs_sent + label dummies + vix.
    Label dummy coefficients are the calibrated per-label severities."""
    d_tr = pd.get_dummies(train['label'], prefix='label').astype(float)
    d_te = pd.get_dummies(test['label'], prefix='label').astype(float)
    # align columns (some labels may be missing from one split)
    for col in [f'label_{l}' for l in EVENT_LABELS]:
        if col not in d_tr:
            d_tr[col] = 0.0
        if col not in d_te:
            d_te[col] = 0.0

    X_tr = sm.add_constant(pd.DataFrame({
        'abs_sent': train['abs_sent'].values,
        'vix_norm': (train['vix'] / 20.0).values,
        **{c: d_tr[c].values for c in d_tr.columns},
    }), has_constant='add')
    y_tr = train['log_abs_ar'].values
    model_tr = sm.OLS(y_tr, X_tr).fit(cov_type='HAC', cov_kwds={'maxlags': 5})

    X_te = sm.add_constant(pd.DataFrame({
        'abs_sent': test['abs_sent'].values,
        'vix_norm': (test['vix'] / 20.0).values,
        **{c: d_te[c].values for c in d_te.columns},
    }), has_constant='add')
    y_te = test['log_abs_ar'].values
    pred_log = model_tr.predict(X_te)

    ss_res = float(np.sum((y_te - pred_log) ** 2))
    ss_tot = float(np.sum((y_te - y_te.mean()) ** 2))
    r2_out = round(1 - ss_res / ss_tot, 4) if ss_tot > 0 else float('nan')

    return {
        "coefficients": {k: round(float(v), 4) for k, v in model_tr.params.items()},
        "pvalues": {k: round(float(v), 4) for k, v in model_tr.pvalues.items()},
        "r2_train": round(model_tr.rsquared, 4),
        "r2_test": r2_out,
    }


def fit_direction_lpm(train: pd.DataFrame, test: pd.DataFrame) -> dict:
    """LPM: P(sector_ar > 0) on signed_sent + abs_sent + vix."""
    X_tr = sm.add_constant(pd.DataFrame({
        'signed_sent': train['sentiment'].values,
        'abs_sent': train['abs_sent'].values,
        'vix_norm': (train['vix'] / 20.0).values,
    }), has_constant='add')
    y_tr = (train['sector_ar'] > 0).astype(float).values
    model = sm.OLS(y_tr, X_tr).fit(cov_type='HAC', cov_kwds={'maxlags': 5})

    X_te = sm.add_constant(pd.DataFrame({
        'signed_sent': test['sentiment'].values,
        'abs_sent': test['abs_sent'].values,
        'vix_norm': (test['vix'] / 20.0).values,
    }), has_constant='add')
    p_hat = model.predict(X_te)
    yhat_dir = np.where(p_hat > 0.5, 1, 0)
    y_true_dir = (test['sector_ar'] > 0).astype(int).values
    hit = round(float(np.mean(yhat_dir == y_true_dir)), 4)

    return {
        "coefficients": {k: round(float(v), 4) for k, v in model.params.items()},
        "pvalues": {k: round(float(v), 4) for k, v in model.pvalues.items()},
        "r2_train": round(model.rsquared, 4),
        "test_directional_hit_rate": hit,
    }


def main() -> None:
    df = add_vix(load_events())
    log.info("events with VIX: %d", len(df))

    split_date = pd.Timestamp('2021-06-30').date()
    train = df[df['dt'] <= split_date]
    test = df[df['dt'] > split_date]
    log.info("train: %d | test: %d", len(train), len(test))

    # ---- Model 1: impact level ----
    imp = fit_impact_ols(train, test)
    log.info("impact model: %s", json.dumps(imp, indent=2))

    # ---- Model 2: direction ----
    dr = fit_direction_lpm(train, test)
    log.info("direction model: %s", json.dumps(dr, indent=2))

    # ---- summary ----
    result = {
        "description": "Empirical calibration: two OLS models fitted on the training "
                       "window, evaluated on the held-out test window. HAC errors.",
        "train_n": len(train), "test_n": len(test),
        "impact_model": imp,
        "direction_model": dr,
        "honesty_notes": [
            "R2 is low by design: daily news-to-returns is 0.5-2% per the literature.",
            "Event labels come from our own classifier; some noise propagates.",
            "Functional form fixed before the test window; no stepwise selection.",
        ],
    }
    out = settings.cache_dir / "signal_model_calibration.json"
    out.write_text(json.dumps(result, indent=2), encoding="utf-8")
    log.info("saved to %s", out)


if __name__ == "__main__":
    main()
