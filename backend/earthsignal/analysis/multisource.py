"""POWER (MERRA-2) versus GPM IMERG precipitation: a compatible, reproducible comparison.

Compatibility rules (docs/research/MULTI_SOURCE_METHODOLOGY.md; DECISIONS D-019):
  1. Same area: IMERG area mean over exactly the MERRA-2 cell (data.grid weights).
  2. Same day boundaries: both series are UTC days. IMERG is UTC-only, so MERRA-2 is requested in UTC too.
  3. Same units: both mm/day. A daily mean rate in mm/day equals the daily total in mm.
  4. Same period: only days on or before the IMERG Final-run end (2025-09-30) with BOTH values valid.
  5. Aggregates are built only from complete periods: a month needs every day valid in both series,
     and a year needs all 12 months.
Nothing is gap-filled. Neither source is treated as truth; differences are reported as
MERRA-2 minus IMERG.
"""

from __future__ import annotations

from datetime import date

import numpy as np
import pandas as pd
from scipy import stats

from earthsignal.analysis import trend

WET_THRESHOLD_MM = 1.0
GPM_ERA_START = pd.Timestamp("2014-06-01")  # TRMM -> GPM transition (May/June 2014, IMERG caveats)
M, I = "merra2", "imerg"


def aligned_daily(frame: pd.DataFrame, final_run_end: date, imerg_col: str = "imerg_area_mean_mm_day") -> pd.DataFrame:
    d = pd.DataFrame({M: frame["merra2_prectotcorr_utc_mm_day"], I: frame[imerg_col]})
    d = d[d.index <= pd.Timestamp(final_run_end)]
    return d.dropna()


def complete_monthly_totals(daily: pd.DataFrame) -> pd.DataFrame:
    """Monthly totals (mm) only for months in which every calendar day is present."""
    g = daily.resample("MS")
    totals = g.sum(min_count=1)
    n = g.size()
    days_in_month = pd.Series(totals.index.days_in_month, index=totals.index)
    return totals[n == days_in_month]


def complete_annual_totals(monthly: pd.DataFrame) -> pd.DataFrame:
    g = monthly.groupby(monthly.index.year)
    return g.sum()[g.size() == 12]


def _pair_stats(a: pd.Series, b: pd.Series) -> dict:
    diff = a - b
    return {
        "n": int(len(a)),
        "mean_merra2": float(a.mean()),
        "mean_imerg": float(b.mean()),
        "bias_merra2_minus_imerg": float(diff.mean()),
        "ratio_merra2_over_imerg": float(a.mean() / b.mean()) if b.mean() else None,
        "rmse": float(np.sqrt((diff**2).mean())),
        "pearson_r": float(stats.pearsonr(a, b).statistic),
        "spearman_rho": float(stats.spearmanr(a, b).statistic),
    }


def contingency(daily: pd.DataFrame, threshold: float = WET_THRESHOLD_MM) -> dict:
    """IMERG as the reference only for this table's vocabulary (hits/misses); it is not 'truth'."""
    mw, iw = daily[M] >= threshold, daily[I] >= threshold
    hits = int((mw & iw).sum())
    misses = int((~mw & iw).sum())
    false_alarms = int((mw & ~iw).sum())
    return {
        "threshold_mm_day": threshold,
        "wet_day_fraction_merra2": float(mw.mean()),
        "wet_day_fraction_imerg": float(iw.mean()),
        "hits": hits,
        "misses": misses,
        "false_alarms": false_alarms,
        "correct_negatives": int((~mw & ~iw).sum()),
        "pod": hits / (hits + misses) if hits + misses else None,
        "far": false_alarms / (hits + false_alarms) if hits + false_alarms else None,
        "csi": hits / (hits + misses + false_alarms) if hits + misses + false_alarms else None,
        "frequency_bias": (hits + false_alarms) / (hits + misses) if hits + misses else None,
    }


def _anomaly(s: pd.Series) -> pd.Series:
    return s - s.groupby(s.index.month).transform("mean")


def _trend_summary(r: trend.TrendResult) -> dict:
    return {
        "sen_slope_per_decade": r.sen_slope_per_decade,
        "ci95_per_decade": list(r.sen_slope_ci95_per_decade),
        "modified_mk_p_value": r.modified_mk_p_value,
        "significant_at_0_05": r.significant_at_0_05,
        "n_years": r.n_years,
        "period": [r.period_start_year, r.period_end_year],
    }


def era_step(annual: pd.DataFrame) -> dict:
    """Mean annual difference before the GPM era (whole years <= 2013) vs after (>= 2015).
    2014 straddles the transition and is excluded."""
    d = (annual[M] - annual[I])
    pre, post = d[d.index <= 2013], d[d.index >= 2015]
    if len(pre) < 5 or len(post) < 5:
        return {"available": False}
    mw = stats.mannwhitneyu(pre, post, alternative="two-sided")
    return {
        "available": True,
        "pre_years": [int(pre.index.min()), int(pre.index.max())],
        "post_years": [int(post.index.min()), int(post.index.max())],
        "mean_diff_pre_mm": float(pre.mean()),
        "mean_diff_post_mm": float(post.mean()),
        "change_mm": float(post.mean() - pre.mean()),
        "mann_whitney_p": float(mw.pvalue),
    }


def compare(frame: pd.DataFrame, final_run_end: date) -> dict:
    daily = aligned_daily(frame, final_run_end)
    if len(daily) < 365 * 3:
        raise ValueError(f"only {len(daily)} aligned days; need at least 3 years")
    monthly = complete_monthly_totals(daily)
    annual = complete_annual_totals(monthly)

    out: dict = {
        "period": {"first_day": daily.index.min().date().isoformat(), "last_day": daily.index.max().date().isoformat(),
                   "final_run_end": final_run_end.isoformat()},
        "daily": {**_pair_stats(daily[M], daily[I]), "units": "mm/day"},
        "contingency": contingency(daily),
        "monthly": {
            **_pair_stats(monthly[M], monthly[I]),
            "units": "mm/month",
            "anomaly_pearson_r": float(stats.pearsonr(_anomaly(monthly[M]), _anomaly(monthly[I])).statistic),
            "bias_by_calendar_month_mm": {
                int(m): float(v) for m, v in (monthly[M] - monthly[I]).groupby(monthly.index.month).mean().items()
            },
            "mean_by_calendar_month_mm": {
                "merra2": {int(m): float(v) for m, v in monthly[M].groupby(monthly.index.month).mean().items()},
                "imerg": {int(m): float(v) for m, v in monthly[I].groupby(monthly.index.month).mean().items()},
            },
        },
        "annual": {**_pair_stats(annual[M], annual[I]), "units": "mm/year", "years": [int(y) for y in annual.index]}
        if len(annual) >= 3 else None,
        "series": {
            "months": [d.strftime("%Y-%m") for d in monthly.index],
            "merra2_mm": [round(float(v), 2) for v in monthly[M]],
            "imerg_mm": [round(float(v), 2) for v in monthly[I]],
        },
    }

    if len(annual) >= trend.MIN_YEARS:
        # annual mean rate in mm/day for consistency with the Milestone 1-2 trend units
        days = pd.Series([366 if pd.Timestamp(year=y, month=1, day=1).is_leap_year else 365 for y in annual.index], index=annual.index)
        rate = annual.div(days, axis=0)
        out["trend_comparison"] = {
            "units": "mm/day per decade (annual mean rate)",
            "merra2": _trend_summary(trend.analyze_trend(rate[M], "PRECTOTCORR", "mm/day", {}, "derived_estimate")),
            "imerg": _trend_summary(trend.analyze_trend(rate[I], "IMERG_PRECTOT", "mm/day", {}, "derived_estimate")),
            "difference_merra2_minus_imerg": _trend_summary(
                trend.analyze_trend(rate[M] - rate[I], "difference", "mm/day", {}, "derived_statistic")),
        }
        out["era_step_2014"] = era_step(annual)
    else:
        out["trend_comparison"] = None
        out["era_step_2014"] = {"available": False}

    # Scale sensitivity: the single IMERG cell containing the study point vs the area mean.
    if "imerg_point_cell_mm_day" in frame and frame["imerg_point_cell_mm_day"].notna().any():
        pd_daily = aligned_daily(frame, final_run_end, "imerg_point_cell_mm_day")
        pm = complete_monthly_totals(pd_daily)
        out["scale_sensitivity"] = {
            "monthly_r_area_mean": out["monthly"]["pearson_r"],
            "monthly_r_point_cell": float(stats.pearsonr(pm[M], pm[I]).statistic),
            "monthly_rmse_area_mean": out["monthly"]["rmse"],
            "monthly_rmse_point_cell": float(np.sqrt(((pm[M] - pm[I]) ** 2).mean())),
            "mean_monthly_area_mean_mm": out["monthly"]["mean_imerg"],
            "mean_monthly_point_cell_mm": float(pm[I].mean()),
        }
    return out


def diagnostics(res: dict) -> list[str]:
    """Rule-based statements derived only from the computed numbers."""
    d, m, c = res["daily"], res["monthly"], res["contingency"]
    out = [
        f"Monthly totals agree closely in timing (r = {m['pearson_r']:.2f}, {m['n']} complete months), but MERRA-2 "
        f"averages {m['ratio_merra2_over_imerg']:.2f}× IMERG ({m['bias_merra2_minus_imerg']:+.1f} mm/month).",
        f"Day-to-day agreement is weaker (daily r = {d['pearson_r']:.2f}). MERRA-2 has a wet day (≥ {c['threshold_mm_day']:g} mm) "
        f"on {c['wet_day_fraction_merra2']:.0%} of days versus {c['wet_day_fraction_imerg']:.0%} for IMERG "
        f"(frequency bias {c['frequency_bias']:.2f}).",
    ]
    t = res.get("trend_comparison")
    if t:
        mt, it, dt = t["merra2"], t["imerg"], t["difference_merra2_minus_imerg"]
        def verdict(x):
            return "significant" if x["significant_at_0_05"] else "not significant"
        out.append(
            f"Annual-mean trend {mt['period'][0]}–{mt['period'][1]}: MERRA-2 {mt['sen_slope_per_decade']:+.2f} mm/day per decade "
            f"({verdict(mt)}, p {mt['modified_mk_p_value']:.2f}); IMERG {it['sen_slope_per_decade']:+.2f} ({verdict(it)}, "
            f"p {it['modified_mk_p_value']:.2f}); difference {dt['sen_slope_per_decade']:+.2f} ({verdict(dt)}, p {dt['modified_mk_p_value']:.2f})."
        )
        if mt["significant_at_0_05"] and not it["significant_at_0_05"]:
            out.append("IMERG does not confirm the MERRA-2 trend over this common period.")
        elif mt["significant_at_0_05"] and it["significant_at_0_05"] and np.sign(mt["sen_slope_per_decade"]) == np.sign(it["sen_slope_per_decade"]):
            out.append("Both sources show a significant trend of the same sign. They are not independent "
                       "(IMERG Final uses MERRA-2 winds and GPCC gauges), so this is consistency, not independent confirmation.")
    e = res.get("era_step_2014", {})
    if e.get("available"):
        sig = e["mann_whitney_p"] < 0.05
        out.append(
            f"The annual MERRA-2 minus IMERG difference averaged {e['mean_diff_pre_mm']:+.0f} mm/year in "
            f"{e['pre_years'][0]}–{e['pre_years'][1]} (TRMM era) and {e['mean_diff_post_mm']:+.0f} mm/year in "
            f"{e['post_years'][0]}–{e['post_years'][1]} (GPM era); Mann-Whitney p {e['mann_whitney_p']:.2f}"
            + (". The two products shift relative to each other around the TRMM-to-GPM transition. These data cannot "
               "show which one changed: IMERG's calibration changed at that transition, and MERRA-2's corrected "
               "precipitation depends on its own observational inputs. Treat trends spanning 2014 with caution."
               if sig else ". No significant step at the transition.")
        )
    s = res.get("scale_sensitivity")
    if s:
        out.append(
            f"Scale matters: monthly r with MERRA-2 is {s['monthly_r_area_mean']:.2f} for the IMERG area mean versus "
            f"{s['monthly_r_point_cell']:.2f} for the single 0.1° cell at the study point."
        )
    return out
