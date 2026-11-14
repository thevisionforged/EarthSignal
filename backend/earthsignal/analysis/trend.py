"""Monotonic trend analysis on annual means.

Methods (see docs/DECISIONS.md D-007):

* Mann-Kendall test (Mann 1945; Kendall 1975), non-parametric, with the tie-corrected
  variance and a continuity correction.
* Modified Mann-Kendall, Yue & Wang (2004) variance correction for lag-1 serial correlation of
  the Sen-detrended series. Applied only when rho1 > 0, the case that inflates false positives.
* Sen's slope (Theil 1950; Sen 1968) with a 95% confidence interval (scipy.stats.theilslopes).
* Ordinary least squares (scipy.stats.linregress) as a parametric cross-check, plus a
  Durbin-Watson statistic on the residuals.

Why annual means: daily temperature is dominated by the seasonal cycle and is strongly
autocorrelated, so a trend test on raw daily values would badly overstate significance.
Calendar-year means remove the seasonal cycle and greatly reduce serial dependence.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date

import numpy as np
import pandas as pd
from scipy import stats

MIN_YEAR_COVERAGE = 0.95  # fraction of days in a year that must be valid for the year to count
MIN_YEARS = 10  # refuse to report a trend on fewer annual values


@dataclass
class MannKendall:
    n: int
    s: int
    var_s: float
    z: float
    p_value: float
    tau: float


def mann_kendall(x: np.ndarray) -> MannKendall:
    x = np.asarray(x, dtype=float)
    if np.isnan(x).any():
        raise ValueError("mann_kendall: input contains NaN; drop or handle missing values explicitly first")
    n = x.size
    if n < 3:
        raise ValueError("mann_kendall: need at least 3 values")
    diffs = x[None, :] - x[:, None]  # diffs[i, j] = x_j - x_i
    s = int(np.sign(diffs[np.triu_indices(n, k=1)]).sum())
    _, counts = np.unique(x, return_counts=True)
    ties = counts[counts > 1]
    var_s = (n * (n - 1) * (2 * n + 5) - np.sum(ties * (ties - 1) * (2 * ties + 5))) / 18.0
    z = _z_from_s(s, var_s)
    p = 2.0 * stats.norm.sf(abs(z))
    tau = s / (0.5 * n * (n - 1))
    return MannKendall(n=n, s=s, var_s=float(var_s), z=float(z), p_value=float(p), tau=float(tau))


def _z_from_s(s: int, var_s: float) -> float:
    if s > 0:
        return (s - 1) / np.sqrt(var_s)
    if s < 0:
        return (s + 1) / np.sqrt(var_s)
    return 0.0


def lag1_autocorrelation(x: np.ndarray) -> float:
    x = np.asarray(x, dtype=float)
    d = x - x.mean()
    denom = np.sum(d * d)
    return float(np.sum(d[:-1] * d[1:]) / denom) if denom > 0 else 0.0


def yue_wang_variance_factor(rho1: float, n: int) -> float:
    """n/n* for an AR(1) process (Yue & Wang 2004, eq. 6). Returns 1 when rho1 <= 0."""
    if rho1 <= 0:
        return 1.0
    return 1.0 + 2.0 * (rho1 ** (n + 1) - n * rho1**2 + (n - 1) * rho1) / (n * (rho1 - 1) ** 2)


@dataclass
class TrendResult:
    variable: str
    units: str
    period_start_year: int
    period_end_year: int
    n_years: int
    excluded_years: dict[str, str]
    sen_slope_per_decade: float
    sen_slope_ci95_per_decade: tuple[float, float]
    sen_intercept: float
    mk_s: int
    mk_tau: float
    mk_z: float
    mk_p_value: float
    lag1_autocorrelation_detrended: float
    variance_inflation_factor: float
    modified_mk_z: float
    modified_mk_p_value: float
    ols_slope_per_decade: float
    ols_slope_stderr_per_decade: float
    ols_p_value: float
    ols_r_squared: float
    durbin_watson: float
    total_change_over_period: float
    significant_at_0_05: bool
    method: str
    data_kind: str
    diagnostics: list[str]
    limitations: list[str]

    def to_dict(self) -> dict:
        return asdict(self)


def annual_means(
    daily: pd.Series, last_allowed_day: date | None = None, min_coverage: float = MIN_YEAR_COVERAGE
) -> tuple[pd.Series, dict[str, str]]:
    """Calendar-year means of a daily series. Years that are incomplete, under-covered or
    end after `last_allowed_day` are excluded (and reported), never padded or imputed."""
    daily = daily.sort_index()
    excluded: dict[str, str] = {}
    means = {}
    for year, s in daily.groupby(daily.index.year):
        year_end = date(year, 12, 31)
        n_days_in_year = 366 if pd.Timestamp(year=year, month=12, day=31).is_leap_year else 365
        if last_allowed_day is not None and year_end > last_allowed_day:
            excluded[str(year)] = f"year ends after analysis cutoff {last_allowed_day.isoformat()}"
            continue
        coverage = s.notna().sum() / n_days_in_year
        if coverage < min_coverage:
            excluded[str(year)] = f"coverage {coverage:.3f} < {min_coverage}"
            continue
        means[year] = float(s.mean())  # pandas mean skips NaN
    out = pd.Series(means, dtype=float)
    out.index.name = "year"
    return out, excluded


ALPHA = 0.05
DW_LOW = 1.5

# Variable-specific caveats, taken from NASA POWER's published validation
# (https://power.larc.nasa.gov/docs/methodology/data/sources_meteorology/).
VARIABLE_CAVEATS = {
    "PRECTOTCORR": (
        "NASA POWER's own validation of MERRA-2 daily precipitation against GSOD stations reports "
        "R^2 0.39 and RMSE 3.69 mm/day (versus R^2 0.97 for daily mean temperature). Treat "
        "precipitation trends from this source with particular caution, and confirm them against "
        "gauge or satellite-gauge records before drawing conclusions."
    ),
}


def trend_diagnostics(mk_p: float, mod_p: float, ols_p: float, dw: float, rho1: float) -> list[str]:
    """Rule-based interpretation flags computed only from the statistics (no free-text generation)."""
    out = []
    if mk_p < ALPHA <= mod_p:
        out.append(
            f"The naive Mann-Kendall test is significant (p={mk_p:.3f}) but loses significance after the "
            f"serial-correlation correction (p={mod_p:.3f}). Do not report this as a significant trend."
        )
    if ols_p < ALPHA <= mod_p:
        out.append(
            f"OLS reports p={ols_p:.3f}, but OLS assumes independent residuals. Prefer the corrected "
            "Mann-Kendall result."
        )
    if dw < DW_LOW or rho1 > 0.3:
        out.append(
            f"Residuals are autocorrelated (Durbin-Watson {dw:.2f}, detrended lag-1 r {rho1:.2f}). A single "
            "linear or monotonic trend may not describe the series well. Multi-decadal variability or step "
            "changes may be present, so inspect the annual series."
        )
    if mod_p < ALPHA:
        out.append(f"The monotonic trend is significant at {ALPHA} after the serial-correlation correction.")
    elif not out:
        out.append(f"No statistically significant monotonic trend at {ALPHA}.")
    return out


def analyze_trend(
    annual: pd.Series, variable: str, units: str, excluded_years: dict[str, str], data_kind: str
) -> TrendResult:
    annual = annual.dropna().sort_index()
    if len(annual) < MIN_YEARS:
        raise ValueError(f"only {len(annual)} usable years; at least {MIN_YEARS} required")
    years = annual.index.to_numpy(dtype=float)
    values = annual.to_numpy(dtype=float)
    n = values.size

    mk = mann_kendall(values)
    sen = stats.theilslopes(values, years, alpha=0.95)
    detrended = values - sen.slope * years
    rho1 = lag1_autocorrelation(detrended)
    factor = yue_wang_variance_factor(rho1, n)
    z_mod = _z_from_s(mk.s, mk.var_s * factor)
    p_mod = float(2.0 * stats.norm.sf(abs(z_mod)))

    ols = stats.linregress(years, values)
    resid = values - (ols.intercept + ols.slope * years)
    dw = float(np.sum(np.diff(resid) ** 2) / np.sum(resid**2))

    span_years = years[-1] - years[0]
    diagnostics = trend_diagnostics(mk.p_value, p_mod, ols.pvalue, dw, rho1)
    limitations = [
        "Input is NASA POWER reanalysis (MERRA-2/GEOS-IT), a grid-cell (~0.5 x 0.625 deg) model estimate, "
        "not a station record. Reanalysis trends can be affected by changes in the observing system "
        "assimilated over time.",
        "A statistically significant monotonic trend describes the change. It does not identify its "
        "cause (for example urbanisation, aerosols, land use or greenhouse forcing).",
        "Sen's slope confidence interval assumes independent annual values; check the lag-1 "
        "autocorrelation and the modified Mann-Kendall p-value.",
        "The trend is fitted to this period only. Extrapolating it beyond the period is not a forecast.",
        "Single grid cell. The result does not resolve within-city differences such as urban heat islands.",
    ]
    if variable in VARIABLE_CAVEATS:
        limitations.append(VARIABLE_CAVEATS[variable])
    return TrendResult(
        variable=variable,
        units=units,
        period_start_year=int(years[0]),
        period_end_year=int(years[-1]),
        n_years=n,
        excluded_years=excluded_years,
        sen_slope_per_decade=float(sen.slope * 10),
        sen_slope_ci95_per_decade=(float(sen.low_slope * 10), float(sen.high_slope * 10)),
        sen_intercept=float(sen.intercept),
        mk_s=mk.s,
        mk_tau=mk.tau,
        mk_z=mk.z,
        mk_p_value=mk.p_value,
        lag1_autocorrelation_detrended=rho1,
        variance_inflation_factor=float(factor),
        modified_mk_z=float(z_mod),
        modified_mk_p_value=p_mod,
        ols_slope_per_decade=float(ols.slope * 10),
        ols_slope_stderr_per_decade=float(ols.stderr * 10),
        ols_p_value=float(ols.pvalue),
        ols_r_squared=float(ols.rvalue**2),
        durbin_watson=dw,
        total_change_over_period=float(sen.slope * span_years),
        significant_at_0_05=bool(p_mod < ALPHA),
        method=(
            "Calendar-year means; Mann-Kendall with Yue-Wang (2004) lag-1 variance correction; "
            "Sen's slope with 95% CI; OLS cross-check"
        ),
        data_kind="derived_statistic",
        diagnostics=diagnostics,
        limitations=limitations,
    )


def analysis_cutoff(retrieved_on: date) -> date:
    """NASA POWER recommends ending climate-trend analysis ~2 months behind near real time."""
    return (pd.Timestamp(retrieved_on) - pd.DateOffset(months=2)).date()
