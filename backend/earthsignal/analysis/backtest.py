"""Chronological backtesting of simple baselines (no models, nothing shown as a forecast in the UI).

Purpose: set the bar any future forecasting method must beat, using strictly past data
(CLAUDE.md integrity rules 4 and 5; DECISIONS D-016).

Baselines, for target day d and lead h (days):
  * climatology:     C(d), a 3-harmonic seasonal cycle fitted on the training data only
  * persistence:     x(d - h), the last value known at the forecast origin
  * damped_anomaly:  C(d) + phi_h * (x(d - h) - C(d - h)), with phi_h the lag-h autocorrelation of
                     training anomalies (the AR(1)-style optimal damping for a stationary anomaly)

Evaluation: rolling origin with yearly folds. For test year Y, the training data is every day
before (Jan 1 of Y - max_lead days), so no training day falls after any forecast origin in the fold.
Targets are every day of Y with a valid observation and a valid origin value.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

import numpy as np
import pandas as pd

LEADS = (1, 3, 7, 14, 30)
N_HARMONICS = 3
BASELINES = ("climatology", "persistence", "damped_anomaly")
MIN_TRAIN_YEARS = 20


def _design(index: pd.DatetimeIndex, n_harmonics: int = N_HARMONICS) -> np.ndarray:
    days_in_year = np.where(index.is_leap_year, 366.0, 365.0)
    phase = 2 * np.pi * (index.day_of_year.to_numpy() - 1) / days_in_year
    cols = [np.ones(len(index))]
    for k in range(1, n_harmonics + 1):
        cols += [np.cos(k * phase), np.sin(k * phase)]
    return np.column_stack(cols)


@dataclass
class Climatology:
    coef: np.ndarray
    n_harmonics: int = N_HARMONICS

    @classmethod
    def fit(cls, train: pd.Series, n_harmonics: int = N_HARMONICS) -> "Climatology":
        t = train.dropna()
        if len(t) < 365 * 3:
            raise ValueError("need at least 3 years of valid training data for climatology")
        coef, *_ = np.linalg.lstsq(_design(t.index, n_harmonics), t.to_numpy(), rcond=None)
        return cls(coef=coef, n_harmonics=n_harmonics)

    def __call__(self, index: pd.DatetimeIndex) -> np.ndarray:
        return _design(index, self.n_harmonics) @ self.coef


def lag_autocorrelation(anom: pd.Series, lag: int) -> float:
    """Autocorrelation at `lag` days on a regular daily index (pairs with NaN are dropped)."""
    a = anom.asfreq("D")
    x, y = a.to_numpy()[:-lag], a.to_numpy()[lag:]
    ok = ~(np.isnan(x) | np.isnan(y))
    if ok.sum() < 30:
        return 0.0
    return float(np.corrcoef(x[ok], y[ok])[0, 1])


def forecast_fold(series: pd.Series, test_year: int, leads: tuple[int, ...] = LEADS) -> pd.DataFrame:
    """Forecasts for every day of `test_year`, for each lead and baseline.

    Uses only training data before (Jan 1 test_year - max(leads)) for fitted quantities, and the
    single observation at the origin (target - lead) for persistence-type baselines."""
    s = series.asfreq("D")
    test_start = pd.Timestamp(test_year, 1, 1)
    train_end = test_start - pd.Timedelta(days=max(leads))  # exclusive
    train = s[s.index < train_end]
    if train.dropna().index.year.nunique() < MIN_TRAIN_YEARS:
        raise ValueError(f"fold {test_year}: fewer than {MIN_TRAIN_YEARS} training years")
    clim = Climatology.fit(train)
    train_anom = train - clim(train.index)

    targets = s[(s.index.year == test_year)].dropna()
    rows = []
    for h in leads:
        origins = targets.index - pd.Timedelta(days=h)
        x_origin = s.reindex(origins).to_numpy()
        ok = ~np.isnan(x_origin)
        if not ok.any():
            continue
        tgt_idx = targets.index[ok]
        org_idx = origins[ok]
        c_t = clim(tgt_idx)
        c_o = clim(org_idx)
        phi = lag_autocorrelation(train_anom, h)
        obs = targets.to_numpy()[ok]
        xo = x_origin[ok]
        rows.append(
            pd.DataFrame(
                {
                    "target": tgt_idx,
                    "origin": org_idx,
                    "lead": h,
                    "observed": obs,
                    "climatology": c_t,
                    "persistence": xo,
                    "damped_anomaly": c_t + phi * (xo - c_o),
                    "phi": phi,
                    "fold": test_year,
                }
            )
        )
    return pd.concat(rows, ignore_index=True) if rows else pd.DataFrame()


def _metrics(df: pd.DataFrame) -> dict:
    out = {}
    mse_clim = float(np.mean((df["climatology"] - df["observed"]) ** 2))
    for b in BASELINES:
        err = df[b] - df["observed"]
        mse = float(np.mean(err**2))
        out[b] = {
            "mae": float(np.mean(np.abs(err))),
            "rmse": float(np.sqrt(mse)),
            "bias": float(np.mean(err)),
            "skill_vs_climatology": (1.0 - mse / mse_clim) if mse_clim > 0 else None,
        }
    return out


def run_backtest(
    series: pd.Series, first_test_year: int, last_test_year: int, leads: tuple[int, ...] = LEADS
) -> dict:
    folds = [forecast_fold(series, y, leads) for y in range(first_test_year, last_test_year + 1)]
    allf = pd.concat([f for f in folds if not f.empty], ignore_index=True)
    by_lead = []
    for h, g in allf.groupby("lead"):
        per_fold = g.groupby("fold").apply(_metrics, include_groups=False)
        skills = {
            b: [m[b]["skill_vs_climatology"] for m in per_fold] for b in ("persistence", "damped_anomaly")
        }
        pooled = _metrics(g)
        best = min(BASELINES, key=lambda b: pooled[b]["rmse"])
        by_lead.append(
            {
                "lead_days": int(h),
                "n_forecasts": int(len(g)),
                "pooled": pooled,
                "best_baseline": best,
                "phi_range": [float(g["phi"].min()), float(g["phi"].max())],
                "fold_skill": {
                    b: {
                        "median": float(np.median(v)),
                        "min": float(np.min(v)),
                        "max": float(np.max(v)),
                        "n_folds_positive": int(sum(x > 0 for x in v)),
                    }
                    for b, v in skills.items()
                },
            }
        )
    return {
        "test_years": [first_test_year, last_test_year],
        "n_folds": len(folds),
        "leads": list(leads),
        "by_lead": by_lead,
        "design": {
            "folds": "expanding window; one fold per calendar test year",
            "training_cutoff": "training data ends max(lead) days before the test year starts",
            "climatology": f"{N_HARMONICS}-harmonic seasonal cycle fitted by least squares on training data",
            "persistence": "value at the forecast origin (target - lead)",
            "damped_anomaly": "climatology + lag-autocorrelation(training anomalies) * origin anomaly",
            "skill_vs_climatology": "1 - MSE(baseline) / MSE(climatology); > 0 means better than climatology",
        },
    }


def test_year_range(series: pd.Series, cutoff: date, min_train_years: int = MIN_TRAIN_YEARS) -> tuple[int, int]:
    """First test year leaves >= min_train_years of training. Last is the last calendar year that both
    ends on or before the cutoff and is covered by the data through Dec 31."""
    valid = series.dropna()
    first_data_year = int(valid.index.year.min())
    first = first_data_year + min_train_years + 1  # +1 because training stops max(lead) days early
    last_by_cutoff = cutoff.year - 1 if cutoff < date(cutoff.year, 12, 31) else cutoff.year
    last_day = valid.index.max()
    last_by_data = last_day.year if (last_day.month, last_day.day) == (12, 31) else last_day.year - 1
    last = min(last_by_cutoff, last_by_data)
    if last < first:
        raise ValueError("not enough data for a backtest")
    return first, last
