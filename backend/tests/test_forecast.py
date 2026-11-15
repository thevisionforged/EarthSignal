"""Forecast tests (D-026). All series are SYNTHETIC; real-data results are in the implementation log."""

import json
from datetime import date

import numpy as np
import pandas as pd
import pytest
from fastapi.testclient import TestClient

from earthsignal.analysis import forecast as fc
from earthsignal.api.main import create_app
from earthsignal.config import LUCKNOW
from earthsignal.data import ingest

from .conftest import synthetic_power_doc

FAST = (1, 2, 3, 7, 14)


def series(kind="ar1", start="1981-01-01", end="2025-12-31", seed=0):
    idx = pd.date_range(start, end, freq="D")
    rng = np.random.default_rng(seed)
    n = idx.size
    a = np.zeros(n)
    eps = rng.normal(0, 1, n)
    for i in range(1, n):
        a[i] = 0.7 * a[i - 1] + eps[i]
    if kind == "slow":  # add a slowly varying component: predictable from the 30-day mean, not from today's value alone
        slow = np.repeat(rng.normal(0, 2.0, n // 60 + 1), 60)[:n]
        a = a + pd.Series(slow).rolling(30, min_periods=1).mean().to_numpy()
    seasonal = 25 + 8 * np.sin(2 * np.pi * (idx.dayofyear - 100) / 365.25)
    return pd.Series(seasonal + a, index=idx)


def test_features_values_and_gaps():
    s = pd.Series(np.arange(40, dtype=float), index=pd.date_range("2000-01-01", periods=40, freq="D"))
    f = fc.features(s)
    assert f.loc["2000-01-03", ["a0", "a1", "a2"]].tolist() == [2.0, 1.0, 0.0]
    assert f.loc["2000-01-07", "m7"] == pytest.approx(3.0)
    assert np.isnan(f.loc["2000-01-29", "m30"]) and f.loc["2000-01-30", "m30"] == pytest.approx(14.5)
    s.loc["2000-01-20"] = np.nan
    f = fc.features(s)
    assert np.isnan(f.loc["2000-01-22", "a2"]) and np.isnan(f.loc["2000-01-25", "m7"]) and not np.isnan(f.loc["2000-01-27", "m7"])


def test_no_information_from_after_the_origin_is_used():
    s = series(seed=1)
    base = fc.forecast_fold(s, 2010, FAST)
    cut = pd.Timestamp("2010-06-15")
    s2 = s.copy()
    s2[s2.index >= cut] = np.random.default_rng(9).normal(100, 50, (s2.index >= cut).sum())
    alt = fc.forecast_fold(s2, 2010, FAST)
    keep = (base["target"] - pd.to_timedelta(base["lead"], unit="D")) < cut
    cols = ["damped_anomaly", "anomaly_regression", "seasonal_damped", "climatology"]
    assert len(alt) == len(base) and keep.sum() > 100  # same rows: the perturbation adds no gaps
    pd.testing.assert_frame_equal(base.loc[keep, cols], alt.loc[keep, cols])
    assert not np.allclose(base.loc[~keep, "anomaly_regression"], alt.loc[~keep, "anomaly_regression"])  # and the test is not vacuous


def test_all_methods_scored_on_the_same_days():
    f = fc.forecast_fold(series(seed=2), 2005, FAST)
    assert f[["observed", "damped_anomaly", "anomaly_regression", "seasonal_damped"]].notna().all().all()
    assert set(f["lead"]) == set(FAST)


def test_pure_ar1_gives_no_real_gain_over_damped_persistence():
    # Damped persistence is the optimal forecast for AR(1); the regression should not improve meaningfully.
    ev = fc.evaluate(fc.run_folds(series("ar1", seed=3), 2002, 2025, FAST))
    for r in ev["per_lead"]:
        assert abs(r["holdout"]["skill_vs_baseline"]) < 0.02


def test_predictable_slow_component_passes():
    ev = fc.evaluate(fc.run_folds(series("slow", seed=4), 2002, 2025, FAST))
    assert ev["horizon_days"] == 3 and all(r["passes"] for r in ev["per_lead"])  # FAST leads 1,2,3 contiguous; 7 is not lead 4
    assert ev["per_lead"][-1]["chosen"] == "anomaly_regression"
    assert all(0.85 <= r["band_coverage_dev"] <= 0.95 for r in ev["per_lead"])


def _fake_folds(cand_err, base_err=1.0, leads=(1, 2, 3)):
    rows = []
    rng = np.random.default_rng(0)
    for y in range(2002, 2026):
        for h in leads:
            e = rng.normal(0, 1, 50)
            rows.append(pd.DataFrame({"fold": y, "lead": h, "target": pd.date_range(f"{y}-01-01", periods=50), "observed": 0.0,
                                      "climatology": 3 * e, "damped_anomaly": base_err * e,
                                      "anomaly_regression": cand_err.get(h, 1.0) * e, "seasonal_damped": 2 * e}))
    return pd.concat(rows, ignore_index=True)


def test_pass_rule_and_contiguous_horizon():
    ev = fc.evaluate(_fake_folds({1: 0.5, 2: 1.0, 3: 0.5}))
    assert [r["passes"] for r in ev["per_lead"]] == [True, False, True]
    assert ev["horizon_days"] == 1 and ev["n_passing"] == 2  # lead 3 passes but is not contiguous with lead 1
    assert fc.evaluate(_fake_folds({1: 1.0}, leads=(1,)))["horizon_days"] == 0  # equal to baseline: no pass
    with pytest.raises(ValueError):
        fc.evaluate(_fake_folds({}), dev=(1900, 1901))


def test_issue_respects_horizon_gaps_and_band():
    s = series("slow", seed=5)
    ev = fc.evaluate(fc.run_folds(s, 2002, 2025, FAST))
    out = fc.issue(s, ev)
    assert out["origin"] == "2025-12-31" and [d["lead_days"] for d in out["days"]] == [1, 2, 3]
    d = out["days"][0]
    assert d["date"] == "2026-01-01" and d["low"] < d["forecast"] < d["high"] and isinstance(d["forecast"], float)
    assert fc.issue(s, {**ev, "horizon_days": 0}) is None
    s2 = s.copy(); s2.loc["2025-12-20"] = np.nan
    assert fc.issue(s2, ev) is None  # gap inside the 30-day window


def test_api_forecast_endpoint(tmp_path, sample_doc, metadata_bytes):
    doc = synthetic_power_doc(sample_doc, "1981-01-01", "2025-12-31", seed=11)
    payload = json.dumps(doc).encode()
    get = lambda url: metadata_bytes if "/system/manager/parameters" in url else payload
    raw = ingest.download(LUCKNOW, date(1981, 1, 1), date(2025, 12, 31), raw_root=tmp_path / "raw", http_get=get)
    ingest.process(raw, processed_root=tmp_path / "processed")
    c = TestClient(create_app(processed_root=tmp_path / "processed", cases_path=tmp_path / "cases.json"))
    b = c.get("/api/forecast").json()
    assert b["data_kind"] == "forecast" and b["evaluation_data_kind"] == "evaluation_statistic"
    assert len(b["evaluation"]["per_lead"]) == 30 and b["limitations"] and b["method"]
    if b["forecast"] is None:  # white-noise-like synthetic data: nothing should pass, and that must be explained
        assert b["no_forecast_reason"] and c.get("/api/forecast", params={"format": "csv"}).status_code == 404
    else:
        csv = c.get("/api/forecast", params={"format": "csv"})
        assert csv.status_code == 200 and "FORECAST" in csv.text and "IMD forecasts take precedence" in csv.text
    assert c.get("/api/forecast", params={"area": "mars"}).status_code == 422
    assert c.get("/api/forecast", params={"area": "lucknow_airport"}).status_code == 404  # no data for that cell
