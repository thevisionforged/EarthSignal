from datetime import date

import numpy as np
import pandas as pd
import pytest

from earthsignal.analysis import seasonal


def _daily(start, end, fn=lambda idx: np.full(len(idx), 20.0)):
    idx = pd.date_range(start, end, freq="D")
    return pd.Series(fn(idx), index=idx, dtype=float)


def test_seasons_partition_the_year():
    months = sorted(m for ms in seasonal.SEASONS.values() for m in ms)
    assert months == list(range(1, 13))


def test_season_means_use_only_season_months():
    s = _daily("2000-01-01", "2001-12-31", lambda idx: idx.month.to_numpy(dtype=float))
    means, excluded = seasonal.season_means(s, (6, 7, 8, 9))
    assert excluded == {}
    # day-weighted mean of month numbers 6..9 (30, 31, 31, 30 days)
    expected = (6 * 30 + 7 * 31 + 8 * 31 + 9 * 30) / 122
    assert means.loc[2000] == pytest.approx(expected)


def test_season_coverage_and_cutoff():
    s = _daily("2000-01-01", "2002-12-31")
    s.loc["2001-01-01":"2001-01-10"] = np.nan  # 10/59 winter days missing -> excluded
    means, excluded = seasonal.season_means(s, (1, 2), last_allowed_day=date(2002, 1, 31))
    assert list(means.index) == [2000]
    assert "coverage" in excluded["2001"]
    assert "cutoff" in excluded["2002"]


def test_seasonal_trends_bh_adjustment():
    rng = np.random.default_rng(7)
    idx = pd.date_range("1981-01-01", "2020-12-31", freq="D")
    years = idx.year - 1981
    # SYNTHETIC: strong trend only in monsoon months
    trend = np.where(idx.month.isin([6, 7, 8, 9]), 0.05 * years, 0.0)
    s = pd.Series(25 + trend + rng.normal(0, 1.0, idx.size), index=idx)
    rows = seasonal.seasonal_trends(s, "T2M", "C", "test", last_allowed_day=None)
    by = {r["season"]: r for r in rows}
    assert set(by) == set(seasonal.SEASONS)
    assert by["monsoon"]["significant_after_fdr_0_05"]
    for r in rows:
        assert r["bh_adjusted_p"] >= r["result"]["modified_mk_p_value"] - 1e-12
        assert len(r["season_means"]["years"]) == 40
