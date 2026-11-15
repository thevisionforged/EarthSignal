"""Temperature forecasting under a pre-registered test (DECISIONS D-026).

Two candidates are compared with damped anomaly persistence, the strongest D-016 baseline, using
the same chronological folds as `backtest.py`:

  A  anomaly_regression : per lead h, OLS of anomaly(t+h) on [anom(t), anom(t-1), anom(t-2),
                          7-day mean anomaly, 30-day mean anomaly, intercept]
  B  seasonal_damped    : climatology + phi_h[month of origin] * anom(t)

Development years choose A or B at each lead (lower pooled RMSE). Hold-out years judge the choice once.
A lead passes when the hold-out MSE improvement over the baseline is positive, with the 5th percentile
of a year-block bootstrap above zero. A forecast is shown only for the contiguous horizon 1..L where
every lead passes. Nothing here is tuned on the hold-out.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from earthsignal.analysis.backtest import Climatology, lag_autocorrelation

MAX_LEAD = 30
LEADS = tuple(range(1, MAX_LEAD + 1))
DEV_YEARS = (2002, 2013)
HOLDOUT_YEARS = (2014, 2025)
CANDIDATES = ("anomaly_regression", "seasonal_damped")
BASELINE = "damped_anomaly"
N_BOOT = 2000
SEED = 2026
MIN_TRAIN_YEARS = 20
FEATURES = ("a0", "a1", "a2", "m7", "m30")


def features(anom: pd.Series) -> pd.DataFrame:
    """Predictors known at each origin day. A missing day makes the features that use it NaN."""
    a = anom.asfreq("D")
    return pd.DataFrame({
        "a0": a,
        "a1": a.shift(1),
        "a2": a.shift(2),
        "m7": a.rolling(7, min_periods=7).mean(),
        "m30": a.rolling(30, min_periods=30).mean(),
    })


def _pairs(feat: pd.DataFrame, anom: pd.Series, h: int, last_target: pd.Timestamp) -> tuple[np.ndarray, np.ndarray, pd.DatetimeIndex]:
    """Training pairs (features at origin o, anomaly at o+h), with every target on or before last_target."""
    target = anom.asfreq("D").shift(-h)
    df = feat.assign(y=target)
    df = df[df.index + pd.Timedelta(days=h) <= last_target].dropna()
    return df[list(FEATURES)].to_numpy(), df["y"].to_numpy(), df.index


def fit_regression(feat: pd.DataFrame, anom: pd.Series, h: int, last_target: pd.Timestamp) -> np.ndarray:
    X, y, _ = _pairs(feat, anom, h, last_target)
    if len(y) < 365 * 3:
        raise ValueError("too few training pairs")
    coef, *_ = np.linalg.lstsq(np.column_stack([np.ones(len(y)), X]), y, rcond=None)
    return coef


def fit_monthly_phi(feat: pd.DataFrame, anom: pd.Series, h: int, last_target: pd.Timestamp) -> np.ndarray:
    """phi_h for each calendar month of the origin (index 1..12)."""
    X, y, idx = _pairs(feat, anom, h, last_target)
    phi = np.zeros(13)
    for m in range(1, 13):
        sel = idx.month == m
        if sel.sum() >= 30:
            phi[m] = float(np.corrcoef(X[sel, 0], y[sel])[0, 1])
    return phi


def forecast_fold(series: pd.Series, test_year: int, leads: tuple[int, ...] = LEADS) -> pd.DataFrame:
    """Baseline and both candidates for every day of test_year, evaluated on the SAME target set."""
    s = series.asfreq("D")
    train_end = pd.Timestamp(test_year, 1, 1) - pd.Timedelta(days=max(leads))  # exclusive, as in backtest.py
    train = s[s.index < train_end]
    if train.dropna().index.year.nunique() < MIN_TRAIN_YEARS:
        raise ValueError(f"fold {test_year}: fewer than {MIN_TRAIN_YEARS} training years")
    clim = Climatology.fit(train)
    anom = s - clim(s.index)
    train_anom = anom[anom.index < train_end]
    feat = features(anom)
    last_train_target = train_end - pd.Timedelta(days=1)
    targets = s[s.index.year == test_year].dropna()
    rows = []
    for h in leads:
        origins = targets.index - pd.Timedelta(days=h)
        f = feat.reindex(origins)
        ok = f.notna().all(axis=1).to_numpy()
        if not ok.any():
            continue
        f, tgt = f[ok], targets.index[ok]
        c_t = clim(tgt)
        phi = lag_autocorrelation(train_anom, h)
        coef = fit_regression(feat[feat.index < train_end], train_anom, h, last_train_target)
        mphi = fit_monthly_phi(feat[feat.index < train_end], train_anom, h, last_train_target)
        a0 = f["a0"].to_numpy()
        rows.append(pd.DataFrame({
            "fold": test_year, "lead": h, "target": tgt, "observed": targets.to_numpy()[ok],
            "climatology": c_t,
            "damped_anomaly": c_t + phi * a0,
            "anomaly_regression": c_t + coef[0] + f[list(FEATURES)].to_numpy() @ coef[1:],
            "seasonal_damped": c_t + mphi[f.index.month] * a0,
        }))
    return pd.concat(rows, ignore_index=True) if rows else pd.DataFrame()


def run_folds(series: pd.Series, first: int, last: int, leads: tuple[int, ...] = LEADS) -> pd.DataFrame:
    return pd.concat([forecast_fold(series, y, leads) for y in range(first, last + 1)], ignore_index=True)


def _mse(df: pd.DataFrame, col: str) -> float:
    return float(np.mean((df[col] - df["observed"]) ** 2))


def bootstrap_improvement(g: pd.DataFrame, method: str, n_boot: int = N_BOOT, seed: int = SEED) -> np.ndarray:
    """Year-block bootstrap of MSE(baseline) - MSE(method). Whole years are resampled to keep autocorrelation."""
    per = g.assign(se_b=(g[BASELINE] - g["observed"]) ** 2, se_m=(g[method] - g["observed"]) ** 2) \
           .groupby("fold").agg(sb=("se_b", "sum"), sm=("se_m", "sum"), n=("se_b", "size"))
    sb, sm, n = per["sb"].to_numpy(), per["sm"].to_numpy(), per["n"].to_numpy()
    rng = np.random.default_rng(seed)
    pick = rng.integers(0, len(per), size=(n_boot, len(per)))
    return (sb[pick].sum(1) - sm[pick].sum(1)) / n[pick].sum(1)


def evaluate(folds: pd.DataFrame, dev: tuple[int, int] = DEV_YEARS, holdout: tuple[int, int] = HOLDOUT_YEARS) -> dict:
    """Apply the pre-registered selection and pass rule (D-026) to fold forecasts."""
    d = folds[(folds["fold"] >= dev[0]) & (folds["fold"] <= dev[1])]
    t = folds[(folds["fold"] >= holdout[0]) & (folds["fold"] <= holdout[1])]
    if d.empty or t.empty:
        raise ValueError("development or hold-out period has no forecasts")
    per_lead = []
    for h in sorted(folds["lead"].unique()):
        dh, th = d[d["lead"] == h], t[t["lead"] == h]
        dev_rmse = {m: float(np.sqrt(_mse(dh, m))) for m in (*CANDIDATES, BASELINE)}
        chosen = min(CANDIDATES, key=lambda m: dev_rmse[m])
        boot = bootstrap_improvement(th, chosen)
        mse_b, mse_c, mse_clim = _mse(th, BASELINE), _mse(th, chosen), _mse(th, "climatology")
        err = (th["observed"] - th[chosen]).to_numpy()
        per_lead.append({
            "lead_days": int(h),
            "chosen": chosen,
            "dev_rmse": {k: round(v, 4) for k, v in dev_rmse.items()},
            "holdout": {
                "n": int(len(th)),
                "rmse": {"chosen": round(float(np.sqrt(mse_c)), 4), "baseline": round(float(np.sqrt(mse_b)), 4),
                         "climatology": round(float(np.sqrt(mse_clim)), 4)},
                "mae": {"chosen": round(float(np.mean(np.abs(err))), 4),
                        "baseline": round(float(np.mean(np.abs(th["observed"] - th[BASELINE]))), 4)},
                "bias_chosen": round(float(-np.mean(err)), 4),
                "skill_vs_baseline": round(1 - mse_c / mse_b, 4),
                "skill_vs_climatology": round(1 - mse_c / mse_clim, 4),
                "mse_improvement": round(mse_b - mse_c, 5),
                "mse_improvement_p05": round(float(np.percentile(boot, 5)), 5),
                "mse_improvement_p95": round(float(np.percentile(boot, 95)), 5),
                "error_p05": round(float(np.percentile(err, 5)), 3),
                "error_p95": round(float(np.percentile(err, 95)), 3),
            },
        })
        # Independent check of the band: how often did the dev-period truth fall inside the hold-out band?
        dev_err = (dh["observed"] - dh[chosen]).to_numpy()
        lo, hi = per_lead[-1]["holdout"]["error_p05"], per_lead[-1]["holdout"]["error_p95"]
        per_lead[-1]["band_coverage_dev"] = round(float(np.mean((dev_err >= lo) & (dev_err <= hi))), 3)
        per_lead[-1]["passes"] = per_lead[-1]["holdout"]["mse_improvement"] > 0 and per_lead[-1]["holdout"]["mse_improvement_p05"] > 0
    horizon = 0
    for r in per_lead:
        if r["lead_days"] == horizon + 1 and r["passes"]:
            horizon += 1
        else:
            break
    return {"per_lead": per_lead, "horizon_days": horizon, "n_passing": sum(r["passes"] for r in per_lead),
            "dev_years": list(dev), "holdout_years": list(holdout)}


def issue(series: pd.Series, evaluation: dict) -> dict | None:
    """Forecast from the last valid day, for leads 1..horizon only, each with its chosen method refitted on
    all data up to the origin, and a band from that lead's hold-out errors."""
    H = evaluation["horizon_days"]
    if H == 0:
        return None
    s = series.asfreq("D")
    origin = s.dropna().index.max()
    s = s[s.index <= origin]
    clim = Climatology.fit(s)
    anom = s - clim(s.index)
    feat = features(anom)
    f0 = feat.loc[origin]
    if f0.isna().any():
        return None  # a gap in the last 30 days: the regression cannot be applied
    out = []
    for r in evaluation["per_lead"][:H]:
        h = r["lead_days"]
        target = origin + pd.Timedelta(days=h)
        c = float(clim(pd.DatetimeIndex([target]))[0])
        if r["chosen"] == "anomaly_regression":
            coef = fit_regression(feat, anom, h, origin)
            val = float(c + coef[0] + float(f0[list(FEATURES)].to_numpy(dtype=float) @ coef[1:]))
        else:
            val = float(c + fit_monthly_phi(feat, anom, h, origin)[origin.month] * float(f0["a0"]))
        out.append({"date": target.date().isoformat(), "lead_days": h, "forecast": round(val, 2),
                    "low": round(val + r["holdout"]["error_p05"], 2), "high": round(val + r["holdout"]["error_p95"], 2),
                    "climatology": round(c, 2), "method": r["chosen"]})
    recent = s.loc[origin - pd.Timedelta(days=29):origin]
    return {"origin": origin.date().isoformat(), "origin_value": round(float(s.loc[origin]), 2), "days": out,
            "recent": {"dates": [d.date().isoformat() for d in recent.index],
                       "values": [None if pd.isna(v) else round(float(v), 2) for v in recent]}}
