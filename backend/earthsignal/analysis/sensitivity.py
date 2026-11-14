"""How much does the annual trend depend on the chosen period?

Recomputes the trend (same method as trend.analyze_trend) for every start year with the end
fixed, and for every end year with the start fixed, keeping at least `min_years` annual means.
These are descriptive robustness checks on overlapping windows, not independent tests, so they
are not used to claim significance.
"""

from __future__ import annotations

import pandas as pd

from earthsignal.analysis import trend

MIN_WINDOW_YEARS = 20


def _row(annual: pd.Series, variable: str, units: str) -> dict:
    r = trend.analyze_trend(annual, variable, units, {}, "derived_statistic")
    return {
        "start_year": r.period_start_year,
        "end_year": r.period_end_year,
        "n_years": r.n_years,
        "sen_slope_per_decade": r.sen_slope_per_decade,
        "ci95_per_decade": list(r.sen_slope_ci95_per_decade),
        "modified_mk_p_value": r.modified_mk_p_value,
        "significant_at_0_05": r.significant_at_0_05,
    }


def window_sensitivity(
    annual: pd.Series, variable: str, units: str, min_years: int = MIN_WINDOW_YEARS
) -> dict[str, list[dict]]:
    annual = annual.dropna().sort_index()
    years = list(annual.index)
    if len(years) < min_years:
        raise ValueError(f"need at least {min_years} annual values for sensitivity analysis")
    by_start = [_row(annual.loc[s:], variable, units) for s in years[: len(years) - min_years + 1]]
    by_end = [_row(annual.loc[:e], variable, units) for e in years[min_years - 1 :]]
    return {"vary_start": by_start, "vary_end": by_end, "min_window_years": min_years}


def diagnostics(windows: dict[str, list[dict]]) -> list[str]:
    """Rule-based statements about robustness, computed only from the window results."""
    starts, ends = windows["vary_start"], windows["vary_end"]
    full = starts[0]  # the full analysis period (earliest start, latest end)
    out: list[str] = []
    sig_starts = [r["start_year"] for r in starts if r["significant_at_0_05"]]
    if not full["significant_at_0_05"] and sig_starts:
        out.append(
            f"The full-period trend is not significant, but {len(sig_starts)} of {len(starts)} later start years "
            f"({min(sig_starts)}-{max(sig_starts)}) give a significant result. The verdict depends on the chosen "
            "period. Report the full-period result, not a window selected after looking at the data."
        )
    if full["significant_at_0_05"] and len(sig_starts) < len(starts):
        out.append(
            f"The full-period trend is significant, but only {len(sig_starts)} of {len(starts)} start years "
            "give a significant result."
        )
    end_slopes = [r["sen_slope_per_decade"] for r in ends]
    if min(end_slopes) < 0 < max(end_slopes):
        first_neg = next((r["end_year"] for r in ends if r["sen_slope_per_decade"] < 0), None)
        first_pos = next((r["end_year"] for r in ends if r["sen_slope_per_decade"] > 0), None)
        out.append(
            "The direction of the trend changes with the end year (positive for some windows, negative for "
            f"others; first positive end year {first_pos}, first negative {first_neg}). A single linear trend "
            "is a poor summary of this series."
        )
    sig_ends = [r["end_year"] for r in ends if r["significant_at_0_05"]]
    if sig_ends and len(sig_ends) < len(ends) and sig_ends == [r["end_year"] for r in ends][-len(sig_ends):]:
        out.append(
            f"Significance appears only for windows ending in {min(sig_ends)} or later, so the most recent "
            "years drive the result. Confirm with independent data before drawing conclusions."
        )
    if not out:
        out.append("The trend estimate and its significance are stable across the start and end years tested.")
    return out


def summarize(rows: list[dict]) -> dict:
    slopes = [r["sen_slope_per_decade"] for r in rows]
    n_sig = sum(r["significant_at_0_05"] for r in rows)
    signs = {(s > 0) - (s < 0) for s in slopes}
    return {
        "n_windows": len(rows),
        "slope_min": min(slopes),
        "slope_max": max(slopes),
        "n_significant": n_sig,
        "sign_consistent": len(signs) == 1,
    }
