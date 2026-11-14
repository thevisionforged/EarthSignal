from datetime import date
from itertools import combinations

import numpy as np
import pandas as pd
import pytest
from scipy import stats

from earthsignal.analysis import trend


def test_mann_kendall_hand_computed():
    mk = trend.mann_kendall(np.array([1.0, 2.0, 3.0, 4.0, 5.0]))
    assert mk.s == 10
    assert mk.var_s == pytest.approx(5 * 4 * 15 / 18)
    assert mk.z == pytest.approx(9 / np.sqrt(5 * 4 * 15 / 18))
    assert mk.tau == pytest.approx(1.0)


def test_mann_kendall_tie_correction():
    x = np.array([1.0, 2.0, 2.0, 3.0, 4.0])
    mk = trend.mann_kendall(x)
    assert mk.s == 9
    assert mk.var_s == pytest.approx((5 * 4 * 15 - 2 * 1 * 9) / 18)


def test_mann_kendall_matches_scipy_kendall_tau():
    rng = np.random.default_rng(1)
    x = rng.normal(size=40).cumsum()
    t = np.arange(40)
    mk = trend.mann_kendall(x)
    ref = stats.kendalltau(t, x)
    assert mk.tau == pytest.approx(ref.statistic)
    # scipy uses no continuity correction, so p-values agree only approximately
    assert mk.p_value == pytest.approx(ref.pvalue, rel=0.1, abs=1e-3)


def test_mann_kendall_rejects_nan():
    with pytest.raises(ValueError, match="NaN"):
        trend.mann_kendall(np.array([1.0, np.nan, 3.0]))


def test_sen_slope_equals_median_of_pairwise_slopes():
    rng = np.random.default_rng(2)
    years = np.arange(1990, 2020, dtype=float)
    vals = 0.02 * years + rng.normal(0, 0.2, years.size)
    pairwise = [(vals[j] - vals[i]) / (years[j] - years[i]) for i, j in combinations(range(years.size), 2)]
    res = trend.analyze_trend(pd.Series(vals, index=years.astype(int)), "T2M", "C", {}, "test")
    assert res.sen_slope_per_decade == pytest.approx(np.median(pairwise) * 10)


def test_yue_wang_factor():
    assert trend.yue_wang_variance_factor(0.0, 40) == 1.0
    assert trend.yue_wang_variance_factor(-0.3, 40) == 1.0
    # large-n limit for AR(1): (1 + rho) / (1 - rho)
    assert trend.yue_wang_variance_factor(0.5, 100_000) == pytest.approx(3.0, rel=1e-3)


def test_detects_known_trend():
    rng = np.random.default_rng(3)
    years = np.arange(1981, 2026)
    vals = 25 + 0.03 * (years - 1981) + rng.normal(0, 0.3, years.size)
    res = trend.analyze_trend(pd.Series(vals, index=years), "T2M", "C", {}, "test")
    assert res.significant_at_0_05
    lo, hi = res.sen_slope_ci95_per_decade
    assert lo <= 0.3 <= hi
    assert res.n_years == 45


def test_false_positive_rate_white_noise_near_nominal():
    rng = np.random.default_rng(4)
    years = np.arange(1981, 2026)
    sims = 400
    rejections = sum(trend.mann_kendall(rng.normal(size=years.size)).p_value < 0.05 for _ in range(sims))
    assert 0.02 <= rejections / sims <= 0.09


def test_modified_mk_reduces_false_positives_under_autocorrelation():
    rng = np.random.default_rng(5)
    n, rho, sims = 45, 0.6, 300
    orig = mod = 0
    for _ in range(sims):
        e = rng.normal(size=n)
        x = np.empty(n)
        x[0] = e[0]
        for i in range(1, n):
            x[i] = rho * x[i - 1] + e[i]
        r = trend.analyze_trend(pd.Series(x, index=np.arange(1981, 1981 + n)), "X", "u", {}, "test")
        orig += r.mk_p_value < 0.05
        mod += r.modified_mk_p_value < 0.05
    assert mod < orig
    assert mod / sims < 0.15


def _daily(start, end, value=20.0):
    idx = pd.date_range(start, end, freq="D")
    return pd.Series(value, index=idx, dtype=float)


def test_annual_means_excludes_low_coverage_years_without_imputing():
    s = _daily("2000-01-01", "2002-12-31")
    s.loc["2001-03-01":"2001-04-30"] = np.nan  # ~17% missing
    s.loc["2002-06-01"] = np.nan  # one missing day: still counted
    annual, excluded = trend.annual_means(s)
    assert list(annual.index) == [2000, 2002]
    assert "2001" in excluded
    assert annual.loc[2002] == pytest.approx(20.0)  # NaN skipped, not treated as 0


def test_annual_means_respects_cutoff():
    s = _daily("2000-01-01", "2003-06-30")
    annual, excluded = trend.annual_means(s, last_allowed_day=date(2002, 12, 31))
    assert list(annual.index) == [2000, 2001, 2002]
    assert "2003" in excluded


def test_analysis_cutoff_two_months():
    assert trend.analysis_cutoff(date(2026, 11, 14)) == date(2026, 9, 14)


def test_too_few_years_rejected():
    with pytest.raises(ValueError, match="at least"):
        trend.analyze_trend(pd.Series([1.0, 2.0, 3.0], index=[2000, 2001, 2002]), "T2M", "C", {}, "test")


def test_diagnostics_flag_naive_vs_corrected_disagreement():
    d = trend.trend_diagnostics(mk_p=0.03, mod_p=0.18, ols_p=0.02, dw=1.0, rho1=0.43)
    text = " ".join(d)
    assert "Do not report this as a significant trend" in text
    assert "OLS" in text
    assert "autocorrelated" in text
    assert "is significant at" not in text


def test_diagnostics_significant_and_clean():
    d = trend.trend_diagnostics(mk_p=0.001, mod_p=0.004, ols_p=0.001, dw=2.0, rho1=0.05)
    assert d == ["The monotonic trend is significant at 0.05 after the serial-correlation correction."]


def test_diagnostics_no_trend():
    d = trend.trend_diagnostics(mk_p=0.6, mod_p=0.6, ols_p=0.5, dw=2.0, rho1=0.0)
    assert d == ["No statistically significant monotonic trend at 0.05."]


def test_precipitation_caveat_added():
    years = np.arange(1981, 2001)
    res = trend.analyze_trend(pd.Series(np.linspace(1, 2, 20), index=years), "PRECTOTCORR", "mm/day", {}, "test")
    assert any("R^2 0.39" in l for l in res.limitations)


def test_result_documents_limitations():
    years = np.arange(1981, 2001)
    res = trend.analyze_trend(pd.Series(np.linspace(0, 1, 20), index=years), "T2M", "C", {}, "test")
    text = " ".join(res.limitations).lower()
    assert "cause" in text and "reanalysis" in text and "not a forecast" in text
