"""Seasonal trends (IMD season definitions) with multiple-testing control.

Seasons follow the India Meteorological Department convention:
winter Jan-Feb, pre-monsoon Mar-May, monsoon (southwest) Jun-Sep, post-monsoon Oct-Dec.
Every season lies within one calendar year, so no season straddles a year boundary.

Each season gets the same method as the annual trend (trend.analyze_trend). Testing 4 seasons
per variable inflates the chance of at least one false positive, so the corrected Mann-Kendall
p-values are also adjusted with Benjamini-Hochberg (false discovery rate) across the 4 seasons.
"""

from __future__ import annotations

from datetime import date

import pandas as pd
from scipy import stats

from earthsignal.analysis import trend

SEASONS: dict[str, tuple[int, ...]] = {
    "winter": (1, 2),
    "pre_monsoon": (3, 4, 5),
    "monsoon": (6, 7, 8, 9),
    "post_monsoon": (10, 11, 12),
}
SEASON_LABELS = {
    "winter": "Winter (Jan-Feb)",
    "pre_monsoon": "Pre-monsoon (Mar-May)",
    "monsoon": "Monsoon (Jun-Sep)",
    "post_monsoon": "Post-monsoon (Oct-Dec)",
}


def season_means(
    daily: pd.Series,
    months: tuple[int, ...],
    last_allowed_day: date | None = None,
    min_coverage: float = trend.MIN_YEAR_COVERAGE,
) -> tuple[pd.Series, dict[str, str]]:
    """Per-year mean over the given months. A season-year is excluded (never imputed) if it ends
    after the cutoff or fewer than `min_coverage` of its days are valid."""
    daily = daily.sort_index()
    sel = daily[daily.index.month.isin(months)]
    excluded: dict[str, str] = {}
    means: dict[int, float] = {}
    last_month = max(months)
    for year, s in sel.groupby(sel.index.year):
        season_end = (pd.Timestamp(year=year, month=last_month, day=1) + pd.offsets.MonthEnd(0)).date()
        if last_allowed_day is not None and season_end > last_allowed_day:
            excluded[str(year)] = f"season ends after analysis cutoff {last_allowed_day.isoformat()}"
            continue
        expected_days = sum(pd.Timestamp(year=year, month=m, day=1).days_in_month for m in months)
        coverage = s.notna().sum() / expected_days
        if coverage < min_coverage:
            excluded[str(year)] = f"coverage {coverage:.3f} < {min_coverage}"
            continue
        means[int(year)] = float(s.mean())
    out = pd.Series(means, dtype=float)
    out.index.name = "year"
    return out, excluded


def seasonal_trends(
    daily: pd.Series, variable: str, units: str, data_kind: str, last_allowed_day: date | None
) -> list[dict]:
    rows = []
    for key, months in SEASONS.items():
        means, excluded = season_means(daily, months, last_allowed_day)
        res = trend.analyze_trend(means, variable, units, excluded, data_kind)
        rows.append(
            {
                "season": key,
                "label": SEASON_LABELS[key],
                "months": list(months),
                "result": res.to_dict(),
                "season_means": {"years": [int(y) for y in means.index], "values": means.round(4).tolist()},
            }
        )
    adjusted = stats.false_discovery_control([r["result"]["modified_mk_p_value"] for r in rows], method="bh")
    for r, p_adj in zip(rows, adjusted):
        r["bh_adjusted_p"] = float(p_adj)
        r["significant_after_fdr_0_05"] = bool(p_adj < trend.ALPHA)
    return rows
