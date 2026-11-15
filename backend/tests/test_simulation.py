"""Simulation Studio tests. Calculations use SYNTHETIC series with hand-checkable answers;
API tests use a SYNTHETIC POWER-shaped dataset in a temp folder (never the real data/)."""

import json
from datetime import date

import numpy as np
import pandas as pd
import pytest
from fastapi.testclient import TestClient

from earthsignal.analysis import simulation as sim
from earthsignal.api.main import create_app
from earthsignal.config import LUCKNOW, LUCKNOW_AIRPORT
from earthsignal.data import ingest

from .conftest import synthetic_power_doc


def frame(t, p, start="2000-01-01"):
    idx = pd.date_range(start, periods=len(t), freq="D")
    return pd.DataFrame({"T2M": t, "PRECTOTCORR": p}, index=idx, dtype=float)


# ---------------- transformations
def test_apply_scenario_formulas_and_missing():
    f = frame([20.0, np.nan, 30.0], [10.0, 5.0, np.nan])
    out = sim.apply_scenario(f, sim.Scenario(2.0, 1.5))
    assert out["T2M"].tolist()[0] == 22.0 and out["T2M"].tolist()[2] == 32.0
    assert np.isnan(out["T2M"].iloc[1])  # missing stays missing
    assert out["PRECTOTCORR"].tolist()[:2] == [15.0, 7.5] and np.isnan(out["PRECTOTCORR"].iloc[2])
    assert f["T2M"].tolist()[0] == 20.0  # input not modified


def test_baseline_scenario_is_identity():
    f = frame([20.0, 25.0], [0.0, 3.3])
    pd.testing.assert_frame_equal(sim.apply_scenario(f, sim.Scenario(0.0, 1.0)), f)


@pytest.mark.parametrize("o,m", [(-3.1, 1.0), (5.1, 1.0), (0.0, -0.1), (0.0, 2.01)])
def test_scenario_ranges_enforced(o, m):
    with pytest.raises(ValueError):
        sim.Scenario(o, m).validate()


def test_thresholds_validated():
    with pytest.raises(ValueError):
        sim.Thresholds(35, 10, 5).validate()  # heavy below wet
    with pytest.raises(ValueError):
        sim.Thresholds(35, 0, 50).validate()


# ---------------- metrics
def test_metrics_counts_over_valid_days_only():
    f = frame([34.0, 36.0, np.nan, 40.0], [0.5, 1.0, np.nan, 60.0])
    m = sim.metrics(f, sim.Thresholds(35.0, 1.0, 50.0))
    assert (m.n_days, m.n_valid_t, m.n_valid_p) == (4, 3, 3)
    assert m.temp_exceedance_days == 2  # 36 and 40 (> 35)
    assert m.wet_days == 2 and m.high_rain_days == 1  # 1.0 and 60 (>= 1); 60 (>= 50)
    assert m.total_precip_mm == pytest.approx(61.5) and m.max_daily_precip_mm == 60.0
    assert m.mean_temp_c == pytest.approx((34 + 36 + 40) / 3)


def test_metrics_threshold_is_strict_for_temperature_inclusive_for_rain():
    m = sim.metrics(frame([35.0], [50.0]), sim.Thresholds(35.0, 1.0, 50.0))
    assert m.temp_exceedance_days == 0 and m.high_rain_days == 1


def test_compare_percent_only_where_meaningful():
    base = sim.metrics(frame([20.0, 30.0], [10.0, 0.0]), sim.Thresholds(25, 1, 50))
    scen = sim.metrics(frame([22.0, 32.0], [20.0, 0.0]), sim.Thresholds(25, 1, 50))
    c = sim.compare(base, scen)
    assert c["mean_temp_c"]["difference"] == pytest.approx(2.0) and c["mean_temp_c"]["percent"] is None  # deg C: no %
    assert c["total_precip_mm"]["percent"] == pytest.approx(100.0)
    assert "n_days" not in c


def test_complete_years_and_monthly_series_missing():
    idx = pd.date_range("2001-01-01", "2002-12-31", freq="D")
    f = pd.DataFrame({"T2M": 20.0, "PRECTOTCORR": 1.0}, index=idx)
    f.loc["2002-01-01":"2002-02-28", "T2M"] = np.nan  # 59 of 365 missing -> 2002 incomplete
    assert sim.complete_years(f) == [2001]
    ms = sim.monthly_series(f)
    assert np.isnan(ms.loc["2002-01-01", "mean_temp_c"]) and ms.loc["2001-03-01", "total_precip_mm"] == 31.0


def test_monthly_climatology_and_seasons():
    idx = pd.date_range("2001-01-01", "2002-12-31", freq="D")
    f = pd.DataFrame({"T2M": np.where(idx.month == 6, 40.0, 20.0), "PRECTOTCORR": np.where(idx.month == 7, 2.0, 0.0)}, index=idx)
    th = sim.Thresholds(35, 1, 50)
    clim = {r["month"]: r for r in sim.monthly_climatology(f, th)}
    assert clim[6]["exceedance_days_per_year"] == 30.0 and clim[1]["exceedance_days_per_year"] == 0.0
    assert clim[7]["mean_monthly_precip_mm"] == pytest.approx(62.0) and clim[7]["wet_days_per_year"] == 31.0
    seas = {r["season"]: r for r in sim.seasonal_totals(f, th)}
    assert seas["monsoon"]["mean_seasonal_precip_mm"] == pytest.approx(62.0)


# ---------------- tools
def test_compound_matrix_cells_are_independent_applications():
    f = frame([31.0, 36.0], [10.0, 0.0])  # 31 + 5 = 36 > 35 (exceedance is strict, so 30 + 5 would not count)
    cells = sim.compound_matrix(f, [0.0, 5.0], [1.0, 0.0], sim.Thresholds(35, 1, 50))
    by = {(c["temp_offset_c"], c["precip_multiplier"]): c for c in cells}
    assert by[(0.0, 1.0)]["temp_exceedance_days"] == 1 and by[(5.0, 1.0)]["temp_exceedance_days"] == 2
    assert by[(0.0, 0.0)]["wet_days"] == 0 and by[(5.0, 0.0)]["total_precip_mm"] == 0.0
    with pytest.raises(ValueError):
        sim.compound_matrix(f, list(range(12)), list(range(11)), sim.Thresholds())


def test_analogs_baseline_target_is_closest_to_mean_year():
    feats = pd.DataFrame({"mean_temp_c": [24.0, 25.0, 26.0, 27.0], "total_precip_mm": [800.0, 1000.0, 1000.0, 1200.0]},
                         index=[2001, 2002, 2003, 2004])
    res = sim.find_analogs(feats, sim.Scenario(0.0, 1.0), n=2)
    assert res["target"] == {"mean_temp_c": 25.5, "total_precip_mm": 1000.0}
    assert {a["year"] for a in res["analogs"]} == {2002, 2003}
    warm = sim.find_analogs(feats, sim.Scenario(1.5, 1.2), n=1)
    assert warm["analogs"][0]["year"] == 2004
    assert 0 < warm["analogs"][0]["similarity"] <= 1


def test_analog_features_exclude_missing_explicitly():
    idx = pd.date_range("2001-01-01", "2003-12-31", freq="D")
    f = pd.DataFrame({"T2M": 25.0, "PRECTOTCORR": 2.0}, index=idx)
    f.loc["2002-07-04", "PRECTOTCORR"] = np.nan
    feats = sim.analog_features(f, "monsoon", [2001, 2002, 2003])
    assert list(feats.index) == [2001, 2003]
    assert "2002" in str(feats.attrs["excluded"]) or 2002 in feats.attrs["excluded"]
    assert sim.analog_features(f, "winter", [2001, 2002, 2003]).shape[0] == 3  # missing day is in July only
    with pytest.raises(ValueError):
        sim.analog_features(f, "spring", [2001])


def test_bootstrap_reproducible_and_centred():
    annual = pd.DataFrame({c: np.arange(10, dtype=float) for c in sim.BOOT_METRICS}, index=range(2000, 2010))
    a, b = sim.year_bootstrap(annual, 500, 42), sim.year_bootstrap(annual, 500, 42)
    assert a == b  # same seed -> identical
    c = sim.year_bootstrap(annual, 500, 43)
    assert c["wet_days"]["replicates"] != a["wet_days"]["replicates"]
    assert a["wet_days"]["observed_mean"] == 4.5
    assert a["wet_days"]["p05"] < 4.5 < a["wet_days"]["p95"]
    with pytest.raises(ValueError):
        sim.year_bootstrap(annual, 5, 1)


def test_sensitivity_sweep_monotonic():
    idx = pd.date_range("2001-01-01", "2002-12-31", freq="D")
    f = pd.DataFrame({"T2M": 30.0 + 5 * np.sin(np.arange(idx.size) / 58), "PRECTOTCORR": 2.0}, index=idx)
    sw = sim.sensitivity_sweep(f, sim.Thresholds(33, 1, 50), [2001, 2002], [0, 1, 2], [0.0, 1.0, 2.0])
    ex = [r["exceedance_days_per_year"] for r in sw["by_temp_offset"]]
    assert ex[0] <= ex[1] <= ex[2]
    assert [r["precip_mm_per_year"] for r in sw["by_precip_multiplier"]] == [0.0, pytest.approx(730.0), pytest.approx(1460.0)]


# ---------------- API
@pytest.fixture
def sim_client(tmp_path, sample_doc, metadata_bytes):
    for area in (LUCKNOW, LUCKNOW_AIRPORT):
        doc = synthetic_power_doc(sample_doc, "1990-01-01", "2020-12-31", seed=4)
        payload = json.dumps(doc).encode()
        get = lambda url, p=payload: metadata_bytes if "/system/manager/parameters" in url else p
        raw = ingest.download(area, date(1990, 1, 1), date(2020, 12, 31), raw_root=tmp_path / "raw", http_get=get)
        ingest.process(raw, processed_root=tmp_path / "processed")
    return TestClient(create_app(processed_root=tmp_path / "processed"))


def test_api_meta_and_scenario(sim_client):
    m = sim_client.get("/api/sim/meta").json()
    assert m["complete_years"] == [1990, 2020] and "combined" in m["presets"]
    b = sim_client.get("/api/sim/scenario", params={"start_year": 2000, "end_year": 2009, "temp_offset_c": 2, "precip_multiplier": 0.5}).json()
    assert b["data_kind"] == "hypothetical" and b["years_used"] == list(range(2000, 2010))
    assert b["summary"]["mean_temp_c"]["difference"] == pytest.approx(2.0, abs=1e-6)
    assert b["summary"]["total_precip_mm"]["percent"] == pytest.approx(-50.0)
    assert len(b["monthly"]["months"]) == 120 and b["data_version"]["dataset_id"].startswith("power_daily_lucknow_")


def test_api_tools_respond(sim_client):
    for path, params in [("/api/sim/heat", {"temp_offset_c": 1}), ("/api/sim/rain", {"precip_multiplier": 1.5}),
                         ("/api/sim/compound", {}), ("/api/sim/analogs", {"unit": "monsoon"}),
                         ("/api/sim/uncertainty", {"n_boot": 50, "seed": 7})]:
        r = sim_client.get(path, params={"area": "lucknow_airport", **params})
        assert r.status_code == 200, (path, r.text)
        body = r.json()
        assert body["limitations"] and body["formulas"] and body["inputs"]["area"] == "lucknow_airport"
    u1 = sim_client.get("/api/sim/uncertainty", params={"n_boot": 50, "seed": 7}).json()
    u2 = sim_client.get("/api/sim/uncertainty", params={"n_boot": 50, "seed": 7}).json()
    assert u1["baseline"] == u2["baseline"] and u1["inputs"]["seed"] == 7
    assert "not a calibrated prediction interval" in u1["label_note"].lower() or "Not a calibrated" in u1["label_note"]


@pytest.mark.parametrize("path,params", [
    ("/api/sim/scenario", {"temp_offset_c": 6}), ("/api/sim/scenario", {"precip_multiplier": 3}),
    ("/api/sim/scenario", {"start_year": 2010, "end_year": 2000}), ("/api/sim/scenario", {"area": "mars"}),
    ("/api/sim/heat", {"threshold_c": 99}), ("/api/sim/rain", {"wet_threshold_mm": 20, "heavy_threshold_mm": 10}),
    ("/api/sim/compound", {"t_min": -4}), ("/api/sim/compound", {"t_step": 0.1}), ("/api/sim/analogs", {"unit": "spring"}),
    ("/api/sim/analogs", {"temp_weight": 0, "precip_weight": 0}), ("/api/sim/uncertainty", {"n_boot": 1}),
    ("/api/sim/scenario", {"start_year": 1800, "end_year": 1810}),
])
def test_api_rejects_invalid_inputs(sim_client, path, params):
    assert sim_client.get(path, params=params).status_code == 422


def test_api_csv_downloads(sim_client):
    for path in ("scenario", "heat", "rain", "compound", "analogs", "uncertainty"):
        r = sim_client.get(f"/api/sim/{path}", params={"format": "csv", "n_boot": 20})
        assert r.status_code == 200 and r.headers["content-type"].startswith("text/csv")
        text = r.text
        assert text.startswith("# EarthSignal Simulation Studio") and "data version:" in text and "reanalysis" in text


def test_api_partial_year_excluded(sim_client):
    b = sim_client.get("/api/sim/scenario", params={"start_year": 2019, "end_year": 2020}).json()
    assert b["years_used"] == [2019, 2020] and b["years_excluded"] == []
