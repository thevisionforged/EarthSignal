"""Milestone 4: which precipitation product departs from a gauge reference? (DECISIONS D-023)

Products (all area means over the same MERRA-2 cell, totals in mm):
  * merra2 - NASA POWER PRECTOTCORR (MERRA-2, corrected towards the CPC Unified gauge analysis)
  * imerg  - GPM IMERG Final via POWER (satellite, calibrated monthly to GPCC gauges)
  * imd    - IMD 0.25 deg gridded rain-gauge analysis (dense national network): the REFERENCE

Rules:
  * Monthly and annual totals only. IMD's rainfall-day boundary is not documented in the sources read,
    so daily comparison is avoided.
  * Complete months only (every day present in all three), complete years only (12 such months).
  * Break dates are fixed IN ADVANCE from documentation, not chosen from the data:
      2006: CPC Unified switches from the retrospective version (30K+ gauges) to the real-time version
            (~17K gauges) (CPC README; Reichle & Liu 2014). MERRA-2 corrected precipitation follows CPCU.
      2014: TRMM-to-GPM transition in IMERG (May/June 2014; NASA IMERG caveats).
    Transition years (2006, 2014) are excluded from the before/after comparison.
  * IMD is a reference, not truth. Its station network also varies (Pai et al. 2014).
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from scipy import stats

from earthsignal.analysis import trend

PRODUCTS = ("merra2", "imerg")
REFERENCE = "imd"
BREAKS = {
    2006: "CPC Unified gauge analysis: retrospective (30K+ gauges) -> real-time (~17K gauges); used by MERRA-2",
    2014: "IMERG: TRMM -> GPM era (May/June 2014)",
}


def monthly_totals(daily: pd.DataFrame) -> pd.DataFrame:
    """Monthly sums for months where every day is present in every column."""
    full = daily.dropna()
    g = full.resample("MS")
    tot = g.sum()
    n = g.size()
    dim = pd.Series(tot.index.days_in_month, index=tot.index)
    return tot[n == dim]


def annual_totals(monthly: pd.DataFrame) -> pd.DataFrame:
    g = monthly.groupby(monthly.index.year)
    return g.sum()[g.size() == 12]


def _anom(s: pd.Series) -> pd.Series:
    return s - s.groupby(s.index.month).transform("mean")


def _trend(series: pd.Series, name: str) -> dict:
    r = trend.analyze_trend(series, name, "mm/year", {}, "derived_statistic")
    return {"sen_slope_per_decade": r.sen_slope_per_decade, "ci95_per_decade": list(r.sen_slope_ci95_per_decade),
            "modified_mk_p_value": r.modified_mk_p_value, "significant_at_0_05": r.significant_at_0_05,
            "n_years": r.n_years}


def break_test(diff: pd.Series, year: int) -> dict:
    pre, post = diff[diff.index < year], diff[diff.index > year]
    if len(pre) < 5 or len(post) < 5:
        return {"year": year, "available": False}
    mw = stats.mannwhitneyu(pre, post, alternative="two-sided")
    return {"year": year, "available": True, "reason": BREAKS.get(year, ""),
            "pre": [int(pre.index.min()), int(pre.index.max())], "post": [int(post.index.min()), int(post.index.max())],
            "mean_pre_mm": float(pre.mean()), "mean_post_mm": float(post.mean()),
            "change_mm": float(post.mean() - pre.mean()), "mann_whitney_p": float(mw.pvalue),
            "significant_at_0_05": bool(mw.pvalue < 0.05)}


def arbitrate(daily: pd.DataFrame) -> dict:
    """daily: columns merra2, imerg, imd (mm/day), same area."""
    mo = monthly_totals(daily[[*PRODUCTS, REFERENCE]])
    yr = annual_totals(mo)
    if len(yr) < trend.MIN_YEARS:
        raise ValueError(f"only {len(yr)} complete common years")
    out: dict = {"period": [int(yr.index.min()), int(yr.index.max())], "n_months": int(len(mo)), "n_years": int(len(yr)),
                 "reference": REFERENCE, "trends": {}, "vs_reference": {}}
    for c in (*PRODUCTS, REFERENCE):
        out["trends"][c] = _trend(yr[c], c)
    for p in PRODUCTS:
        d_mo = mo[p] - mo[REFERENCE]
        d_yr = yr[p] - yr[REFERENCE]
        out["vs_reference"][p] = {
            "monthly_r": float(stats.pearsonr(mo[p], mo[REFERENCE]).statistic),
            "monthly_anomaly_r": float(stats.pearsonr(_anom(mo[p]), _anom(mo[REFERENCE])).statistic),
            "annual_r": float(stats.pearsonr(yr[p], yr[REFERENCE]).statistic),
            "mean_ratio": float(mo[p].mean() / mo[REFERENCE].mean()),
            "monthly_bias_mm": float(d_mo.mean()),
            "annual_rmse_mm": float(np.sqrt((d_yr**2).mean())),
            "difference_trend": _trend(d_yr, f"{p}-imd"),
            "breaks": {str(y): break_test(d_yr, y) for y in BREAKS},
        }
    out["annual"] = {"years": [int(y) for y in yr.index], **{c: [round(float(v), 1) for v in yr[c]] for c in yr.columns}}
    out["reference_trend_robustness"] = leave_one_out(yr[REFERENCE])
    return out


def leave_one_out(annual: pd.Series) -> dict:
    """IMD trend recomputed with each single year removed: is the reference trend driven by one year?"""
    rows = []
    for y in annual.index:
        r = trend.analyze_trend(annual.drop(y), "imd", "mm/year", {}, "derived_statistic")
        rows.append((int(y), r.sen_slope_per_decade, r.modified_mk_p_value))
    slopes = [s for _, s, _ in rows]
    n_sig = sum(p < trend.ALPHA for _, _, p in rows)
    most = max(rows, key=lambda x: abs(x[1] - np.median(slopes)))
    return {"slope_min": float(min(slopes)), "slope_max": float(max(slopes)), "n_significant": int(n_sig),
            "n_cases": len(rows), "most_influential_year": most[0], "slope_without_it": float(most[1]),
            "p_without_it": float(most[2])}


BREAK_ALPHA = trend.ALPHA / len(BREAKS)  # Bonferroni across the pre-registered break dates


def verdicts(res: dict) -> list[str]:
    """Rule-based statements.

    PRIMARY test per product: the full-period trend of (product - IMD). One pre-specified test each.
    Break tests are SUPPORTING evidence only, at a Bonferroni-corrected level across the break dates.
    """
    def departs(p):
        v = res["vs_reference"][p]
        steps = [b for b in v["breaks"].values() if b.get("available") and b["mann_whitney_p"] < BREAK_ALPHA]
        return v["difference_trend"]["significant_at_0_05"], steps

    out = []
    t = res["trends"]
    def tr(c):
        x = t[c]
        return f"{x['sen_slope_per_decade']:+.0f} mm/yr per decade ({'significant' if x['significant_at_0_05'] else 'not significant'}, p {x['modified_mk_p_value']:.2f})"
    out.append(f"{res['period'][0]}–{res['period'][1]} annual-total trends: MERRA-2 {tr('merra2')}; IMERG {tr('imerg')}; "
               f"IMD gauges {tr('imd')}.")
    dm, sm = departs("merra2")
    di, si = departs("imerg")
    for p, d, steps in (("MERRA-2", dm, sm), ("IMERG", di, si)):
        key = "merra2" if p == "MERRA-2" else "imerg"
        v = res["vs_reference"][key]
        dt = v["difference_trend"]
        txt = (f"{p} minus IMD: trend {dt['sen_slope_per_decade']:+.0f} mm/yr per decade "
               f"(p {dt['modified_mk_p_value']:.2f})")
        for b in v["breaks"].values():
            if b.get("available"):
                txt += (f"; mean difference {b['mean_pre_mm']:+.0f} → {b['mean_post_mm']:+.0f} mm/yr across {b['year']} "
                        f"(p {b['mann_whitney_p']:.3f})")
        out.append(txt + ".")
    if dm and not di:
        out.append("Primary test: MERRA-2 (POWER) drifts away from the IMD gauge analysis over the period and IMERG does not. "
                   "In this cell, the POWER precipitation trend is not supported by the gauges.")
    elif di and not dm:
        out.append("Primary test: IMERG drifts away from the IMD gauge analysis over the period and MERRA-2 does not. "
                   "In this cell, the IMERG trend is not supported by the gauges.")
    elif dm and di:
        out.append("Primary test: both products drift away from the IMD gauge analysis, so neither can be trusted for trends here.")
    else:
        out.append("Primary test: neither product drifts significantly away from the IMD gauge analysis over the full period, "
                   "so this cell does not settle which product is right.")
    for p, steps in (("MERRA-2", sm), ("IMERG", si)):
        for b in steps:
            out.append(f"Supporting evidence: {p} shifts relative to IMD across the pre-registered {b['year']} date "
                       f"({b['mean_pre_mm']:+.0f} → {b['mean_post_mm']:+.0f} mm/yr, p {b['mann_whitney_p']:.3f} < "
                       f"Bonferroni {BREAK_ALPHA:.3f}; date pre-registered because of: {b['reason']}).")
    rob = res.get("reference_trend_robustness")
    if rob:
        imd_t = res["trends"]["imd"]
        if rob["n_significant"] not in (0, rob["n_cases"]):
            out.append(f"The IMD gauge trend is fragile: dropping single years gives {rob['slope_min']:+.0f} to "
                       f"{rob['slope_max']:+.0f} mm/yr per decade, significant in {rob['n_significant']} of {rob['n_cases']} cases. "
                       f"Without {rob['most_influential_year']} it is {rob['slope_without_it']:+.0f} (p {rob['p_without_it']:.2f}).")
        elif rob["n_significant"] == 0 and imd_t["modified_mk_p_value"] < 0.10:
            out.append(f"The IMD gauge trend is borderline and not significant whichever single year is removed "
                       f"(range {rob['slope_min']:+.0f} to {rob['slope_max']:+.0f} mm/yr per decade).")
    out.append("IMD is a reference, not truth: its gauge network varies over time and may share stations with CPC and GPCC. "
               "The break dates were fixed in advance from documentation, not chosen from the data.")
    return out
