"""Backtest harness tests. All series here are SYNTHETIC with known properties."""

from datetime import date

import numpy as np
import pandas as pd
import pytest

from earthsignal.analysis import backtest


def seasonal_ar1(phi=0.8, sigma=1.0, start="1981-01-01", end="2010-12-31", seed=0):
    idx = pd.date_range(start, end, freq="D")
    rng = np.random.default_rng(seed)
    e = rng.normal(0, sigma * np.sqrt(1 - phi**2), idx.size)
    a = np.empty(idx.size)
    a[0] = rng.normal(0, sigma)
    for i in range(1, idx.size):
        a[i] = phi * a[i - 1] + e[i]
    seas = 25 + 8 * np.sin(2 * np.pi * (idx.day_of_year - 100) / 365.25)
    return pd.Series(seas + a, index=idx)


def test_climatology_recovers_seasonal_cycle():
    idx = pd.date_range("1990-01-01", "1999-12-31", freq="D")
    truth = 20 + 5 * np.cos(2 * np.pi * (idx.day_of_year - 1) / np.where(idx.is_leap_year, 366, 365))
    clim = backtest.Climatology.fit(pd.Series(truth, index=idx))
    assert np.allclose(clim(idx), truth, atol=1e-6)


def test_no_leakage_from_after_the_origin():
    s = seasonal_ar1()
    base = backtest.forecast_fold(s, 2005)
    # Scramble everything after a chosen origin; forecasts whose origin is on/before it must not change.
    cut = pd.Timestamp("2005-06-15")
    scrambled = s.copy()
    scrambled[scrambled.index > cut] = np.random.default_rng(9).normal(100, 50, (scrambled.index > cut).sum())
    again = backtest.forecast_fold(scrambled, 2005)
    keep = base["origin"] <= cut
    cols = ["climatology", "persistence", "damped_anomaly"]
    assert keep.sum() > 500
    np.testing.assert_allclose(base.loc[keep, cols].to_numpy(), again.loc[keep, cols].to_numpy())


def test_training_ends_before_first_origin():
    s = seasonal_ar1()
    base = backtest.forecast_fold(s, 2005)
    # Changing data in the gap [train_end, test_start) must not change climatology/phi.
    gap = (s.index >= pd.Timestamp("2005-01-01") - pd.Timedelta(days=max(backtest.LEADS))) & (s.index < "2005-01-01")
    s2 = s.copy()
    s2[gap] += 50
    again = backtest.forecast_fold(s2, 2005)
    np.testing.assert_allclose(base["climatology"], again["climatology"])
    np.testing.assert_allclose(base["phi"], again["phi"])


def test_skill_matches_ar1_theory():
    # For anomalies following AR(1) with coefficient phi, damped persistence MSE = s^2 (1 - phi^(2h)),
    # so skill vs climatology is about phi^(2h).
    s = seasonal_ar1(phi=0.8, end="2015-12-31")
    r = backtest.run_backtest(s, 2003, 2015, leads=(1, 3, 7))
    sk = {L["lead_days"]: L["pooled"]["damped_anomaly"]["skill_vs_climatology"] for L in r["by_lead"]}
    assert sk[1] == pytest.approx(0.8**2, abs=0.05)
    assert sk[3] == pytest.approx(0.8**6, abs=0.05)
    assert sk[7] == pytest.approx(0.8**14, abs=0.05)
    assert all(L["best_baseline"] == "damped_anomaly" for L in r["by_lead"])


def test_white_noise_has_no_skill():
    s = seasonal_ar1(phi=0.0, end="2015-12-31")
    r = backtest.run_backtest(s, 2003, 2015, leads=(1, 7))
    by = {L["lead_days"]: L["pooled"] for L in r["by_lead"]}
    for p in by.values():
        assert abs(p["damped_anomaly"]["skill_vs_climatology"]) < 0.02
    # Raw persistence: noise MSE doubles (skill -1) and the seasonal change between origin and target
    # adds error that grows with lead. At 1 day that change is negligible; at 7 days it is not.
    assert by[1]["persistence"]["skill_vs_climatology"] == pytest.approx(-1.0, abs=0.1)
    assert by[7]["persistence"]["skill_vs_climatology"] < -1.2


def test_missing_values_are_skipped_not_filled():
    s = seasonal_ar1()
    s.loc["2005-03-01":"2005-03-31"] = np.nan
    f = backtest.forecast_fold(s, 2005, leads=(1,))
    assert not f["target"].between("2005-03-01", "2005-03-31").any()  # NaN targets dropped
    assert not f["origin"].between("2005-03-01", "2005-03-31").any()  # NaN origins dropped
    assert not f[["observed", "persistence"]].isna().any().any()


def test_too_little_training_rejected():
    s = seasonal_ar1(start="1990-01-01", end="2005-12-31")
    with pytest.raises(ValueError, match="training years"):
        backtest.forecast_fold(s, 2000)


def test_test_year_range():
    s = seasonal_ar1(end="2025-12-31")
    assert backtest.test_year_range(s, date(2026, 9, 14)) == (2002, 2025)
    assert backtest.test_year_range(s, date(2025, 12, 31)) == (2002, 2025)
    assert backtest.test_year_range(s, date(2025, 11, 30)) == (2002, 2024)
    # data ending before the cutoff year limits the range (regression: empty folds were scheduled)
    assert backtest.test_year_range(s[:"2020-12-31"], date(2026, 9, 14)) == (2002, 2020)
    assert backtest.test_year_range(s[:"2020-06-30"], date(2026, 9, 14)) == (2002, 2019)
