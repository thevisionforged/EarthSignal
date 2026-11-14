import numpy as np
import pandas as pd
import pytest

from earthsignal.analysis import sensitivity, trend


def _annual(n=30, slope=0.03, seed=0):
    rng = np.random.default_rng(seed)
    years = np.arange(1981, 1981 + n)
    return pd.Series(25 + slope * (years - 1981) + rng.normal(0, 0.2, n), index=years)


def test_window_counts_and_bounds():
    out = sensitivity.window_sensitivity(_annual(30), "T2M", "C", min_years=20)
    assert len(out["vary_start"]) == 11 and len(out["vary_end"]) == 11
    assert out["vary_start"][0]["start_year"] == 1981 and out["vary_start"][-1]["start_year"] == 1991
    assert all(r["end_year"] == 2010 for r in out["vary_start"])
    assert out["vary_end"][0]["end_year"] == 2000 and out["vary_end"][-1]["end_year"] == 2010
    assert all(r["n_years"] >= 20 for r in out["vary_start"] + out["vary_end"])


def test_full_window_matches_main_trend():
    a = _annual(30)
    out = sensitivity.window_sensitivity(a, "T2M", "C", min_years=20)
    main = trend.analyze_trend(a, "T2M", "C", {}, "test")
    assert out["vary_start"][0]["sen_slope_per_decade"] == pytest.approx(main.sen_slope_per_decade)


def test_summary_on_consistent_trend():
    out = sensitivity.window_sensitivity(_annual(30, slope=0.05), "T2M", "C", min_years=20)
    s = sensitivity.summarize(out["vary_start"])
    assert s["sign_consistent"] and s["slope_min"] > 0 and s["n_significant"] == s["n_windows"]


def _w(start_rows, end_rows):
    mk = lambda key, items: [
        {key: y, "sen_slope_per_decade": s, "significant_at_0_05": sig} for y, s, sig in items
    ]
    return {"vary_start": mk("start_year", start_rows), "vary_end": mk("end_year", end_rows)}


def test_diagnostics_window_dependent_significance():
    w = _w([(1981, -0.16, False), (1985, -0.25, True), (1990, -0.30, True), (2000, -0.27, False)],
           [(2000, 0.5, False), (2010, -0.1, False), (2025, -0.16, False)])
    text = " ".join(sensitivity.diagnostics(w))
    assert "2 of 4 later start years (1985-1990)" in text
    assert "direction of the trend changes" in text


def test_diagnostics_recent_years_drive_result():
    w = _w([(1981, 0.24, True), (1990, 0.3, True)],
           [(2000, -0.3, False), (2020, 0.1, False), (2021, 0.2, True), (2025, 0.24, True)])
    text = " ".join(sensitivity.diagnostics(w))
    assert "ending in 2021 or later" in text


def test_diagnostics_stable():
    w = _w([(1981, 0.3, True), (1990, 0.35, True)], [(2000, 0.3, True), (2010, 0.3, True)])
    assert sensitivity.diagnostics(w) == [
        "The trend estimate and its significance are stable across the start and end years tested."
    ]


def test_too_short_rejected():
    with pytest.raises(ValueError):
        sensitivity.window_sensitivity(_annual(15), "T2M", "C", min_years=20)
