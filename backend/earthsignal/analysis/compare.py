"""Compare NASA POWER T2M (reanalysis grid cell) with NOAA GSOD station mean temperature.

Design (docs/DECISIONS.md D-015):

* The GSOD daily mean is built from a varying number of observations: a median of 6-8 per day
  before ~1996, 20-24 from ~2005 at Lucknow airport. Means from a few synoptic readings can differ
  systematically from 24-hour means, so the station series is NOT homogeneous across 1981-2025.
* PRIMARY comparison: only station days with >= MIN_OBS_PRIMARY observations. A month is paired
  only if >= MONTH_MIN_COVERAGE of its days are valid in BOTH series. All metrics and trends use
  this primary set.
* CONTEXT series: months built from days with >= 4 observations (GSOD's own minimum), with the
  median observation count, so the effect of the sampling change can be seen. No metrics use it.
* GSOD days are UTC; POWER days are Local Solar Time (~UTC+5.4 h at Lucknow). Monthly aggregation
  reduces, but does not remove, the effect of the different day boundaries.
* Precipitation is NOT compared: GSOD precipitation reports at this station are mostly incomplete
  (flag "I" or partial-day sums), see D-015.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from scipy import stats

from earthsignal.analysis import trend

MIN_OBS_PRIMARY = 20
MIN_OBS_CONTEXT = 4
MONTH_MIN_COVERAGE = 0.9


def monthly_means(daily: pd.Series, valid: pd.Series | None = None, min_coverage: float = MONTH_MIN_COVERAGE) -> pd.Series:
    """Calendar-month means; NaN where fewer than `min_coverage` of the month's days are valid."""
    s = daily.where(valid) if valid is not None else daily
    full = pd.date_range(s.index.min().replace(day=1), s.index.max() + pd.offsets.MonthEnd(0), freq="D")
    s = s.reindex(full)
    g = s.resample("MS")
    days_in_month = g.size()
    cov = g.count() / days_in_month
    return g.mean().where(cov >= min_coverage)


def anomalies(monthly: pd.Series) -> pd.Series:
    clim = monthly.groupby(monthly.index.month).transform("mean")
    return monthly - clim


def pair_metrics(model: pd.Series, obs: pd.Series) -> dict:
    """Metrics for paired monthly values (model = POWER, obs = station). Drops unpaired months."""
    both = pd.concat({"m": model, "o": obs}, axis=1).dropna()
    n = len(both)
    if n < 24:
        raise ValueError(f"only {n} paired months; at least 24 required")
    diff = both["m"] - both["o"]
    am, ao = anomalies(both["m"]), anomalies(both["o"])
    r = stats.pearsonr(both["m"], both["o"])
    ra = stats.pearsonr(am, ao)
    return {
        "n_months": int(n),
        "first_month": both.index.min().strftime("%Y-%m"),
        "last_month": both.index.max().strftime("%Y-%m"),
        "mean_bias": float(diff.mean()),
        "mae": float(diff.abs().mean()),
        "rmse": float(np.sqrt((diff**2).mean())),
        "pearson_r": float(r.statistic),
        "anomaly_pearson_r": float(ra.statistic),
        "anomaly_rmse": float(np.sqrt(((am - ao) ** 2).mean())),
        "bias_by_calendar_month": {int(m): float(v) for m, v in diff.groupby(diff.index.month).mean().items()},
    }


MIN_PAIRED_MONTHS_PER_YEAR = 10


def annual_anomalies(paired: pd.DataFrame, min_months: int = MIN_PAIRED_MONTHS_PER_YEAR) -> pd.DataFrame:
    """Annual means of monthly anomalies over months present in BOTH series.

    Each series' anomalies are relative to its own calendar-month climatology over the paired months,
    which removes the seasonal cycle. A year with a missing month is then not biased towards any
    season, and both series use exactly the same months. Years with fewer than `min_months` paired
    months are dropped. No imputation."""
    anom = paired.apply(anomalies)
    g = anom.groupby(anom.index.year)
    keep = g.size() >= min_months
    return g.mean()[keep]


def compare_temperature(power_daily: pd.Series, station: pd.DataFrame) -> dict:
    """power_daily: POWER T2M (deg C) for the station's grid cell. station: GSOD frame from gsod.latest()."""
    primary_valid = station["temp_obs"] >= MIN_OBS_PRIMARY
    st_primary = monthly_means(station["tmean_c"], primary_valid)
    st_context = monthly_means(station["tmean_c"], station["temp_obs"] >= MIN_OBS_CONTEXT)
    obs_median = station["temp_obs"].resample("MS").median()

    pw = monthly_means(power_daily.loc[station.index.min(): station.index.max()])
    metrics = pair_metrics(pw, st_primary)

    # Trend comparison over identical complete years in the primary set.
    paired = pd.concat({"p": pw, "s": st_primary}, axis=1).dropna()
    ann = annual_anomalies(paired)
    ann_p, ann_s = ann["p"], ann["s"]
    years = ann.index
    trends = None
    if len(years) >= trend.MIN_YEARS:
        rp = trend.analyze_trend(ann_p.loc[years], "T2M", "C", {}, "derived_estimate")
        rs = trend.analyze_trend(ann_s.loc[years], "TEMP", "C", {}, "observed")
        rd = trend.analyze_trend(ann_p.loc[years] - ann_s.loc[years], "T2M-TEMP", "C", {}, "derived_statistic")
        trends = {
            "years": [int(y) for y in years],
            "contiguous": bool(len(years) == years.max() - years.min() + 1),
            "power": _trend_summary(rp),
            "station": _trend_summary(rs),
            "difference_power_minus_station": _trend_summary(rd),
            "annual_power_anomaly": [round(float(v), 4) for v in ann_p.loc[years]],
            "annual_station_anomaly": [round(float(v), 4) for v in ann_s.loc[years]],
            "method": (
                f"annual means of paired monthly anomalies (own calendar-month climatology), years with "
                f">= {MIN_PAIRED_MONTHS_PER_YEAR} paired months"
            ),
        }

    context = pd.concat({"power": pw, "station": st_context, "obs_median": obs_median}, axis=1)
    context = context[context["station"].notna() | context["power"].notna()]
    return {
        "metrics_primary": metrics,
        "trend_comparison": trends,
        "monthly": {
            "months": [d.strftime("%Y-%m") for d in context.index],
            "power": _clean(context["power"]),
            "station_all": _clean(context["station"]),
            "station_primary": _clean(st_primary.reindex(context.index)),
            "station_obs_median": _clean(context["obs_median"]),
        },
        "rules": {
            "min_obs_primary": MIN_OBS_PRIMARY,
            "min_obs_context": MIN_OBS_CONTEXT,
            "month_min_coverage": MONTH_MIN_COVERAGE,
            "annual": f"annual mean anomaly over paired months; years need >= {MIN_PAIRED_MONTHS_PER_YEAR} paired months",
        },
    }


def _trend_summary(r: trend.TrendResult) -> dict:
    return {
        "sen_slope_per_decade": r.sen_slope_per_decade,
        "ci95_per_decade": list(r.sen_slope_ci95_per_decade),
        "modified_mk_p_value": r.modified_mk_p_value,
        "significant_at_0_05": r.significant_at_0_05,
        "n_years": r.n_years,
    }


def _clean(s: pd.Series) -> list[float | None]:
    return [None if pd.isna(v) else round(float(v), 3) for v in s]


def comparison_diagnostics(result: dict) -> list[str]:
    """Rule-based statements derived only from the computed numbers."""
    m = result["metrics_primary"]
    out = [
        f"Over {m['n_months']} paired months ({m['first_month']} to {m['last_month']}), POWER's monthly mean "
        f"temperature differs from the station by {m['mean_bias']:+.2f} °C on average (RMSE {m['rmse']:.2f} °C, "
        f"r = {m['pearson_r']:.3f}). For month-to-month anomalies, r = {m['anomaly_pearson_r']:.2f}."
    ]
    t = result["trend_comparison"]
    if t is None:
        out.append("Too few complete paired years for a trend comparison.")
        return out
    d = t["difference_power_minus_station"]
    span = f"{t['years'][0]}-{t['years'][-1]}"
    if not t["contiguous"]:
        span += " (with gaps)"
    out.append(
        f"Trend over {span} ({t['station']['n_years']} years with >= {MIN_PAIRED_MONTHS_PER_YEAR} paired months, "
        "annual mean anomalies): station "
        f"{t['station']['sen_slope_per_decade']:+.2f} °C/decade (p {t['station']['modified_mk_p_value']:.2f}), "
        f"POWER {t['power']['sen_slope_per_decade']:+.2f} °C/decade (p {t['power']['modified_mk_p_value']:.2f})."
    )
    if d["significant_at_0_05"]:
        out.append(
            f"The POWER-minus-station difference has a significant trend ({d['sen_slope_per_decade']:+.2f} °C/decade), "
            "so the two records drift apart over this period. POWER's trend should not be taken as the station's. "
            "These data cannot tell which record is responsible. Possibilities include reanalysis behaviour, "
            "station instrument or siting changes, and local land-use change around the station."
        )
    else:
        out.append(
            "No significant drift between POWER and the station over this period "
            f"(difference trend {d['sen_slope_per_decade']:+.2f} °C/decade, p {d['modified_mk_p_value']:.2f})."
        )
    if t["station"]["n_years"] < 25:
        out.append(
            f"Only {t['station']['n_years']} years are comparable, too short to confirm or refute the 1981-2025 "
            "POWER trend. This check covers the recent period only."
        )
    return out
