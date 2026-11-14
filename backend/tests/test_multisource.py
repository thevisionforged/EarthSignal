"""Multi-source comparison and IMERG processing tests. All series are SYNTHETIC unless noted."""

import json
from datetime import date

import numpy as np
import pandas as pd
import pytest

from earthsignal.analysis import multisource
from earthsignal.config import LUCKNOW
from earthsignal.data import grid, imerg_power
from earthsignal.metadata import DatasetMetadata


def _frame(start="1998-01-01", end="2025-12-31", scale=1.3, seed=0, trend_merra=0.0, noise=0.3):
    rng = np.random.default_rng(seed)
    idx = pd.date_range(start, end, freq="D")
    season = np.clip(np.sin(2 * np.pi * (idx.day_of_year - 150) / 365.25), 0, None) * 12
    wet = rng.random(idx.size) < 0.15 + 0.5 * (season > 2)
    imerg = np.where(wet, rng.gamma(1.0, 1.0, idx.size) * (1 + season), 0.0)
    years = (idx - idx[0]).days / 365.25
    # clipped noise has a POSITIVE mean, so it shifts the ratio; tests that check the ratio use noise=0
    merra = imerg * scale * (1 + trend_merra * years) + (rng.normal(0, noise, idx.size).clip(0) if noise else 0.0)
    f = pd.DataFrame({"imerg_area_mean_mm_day": imerg, "merra2_prectotcorr_utc_mm_day": merra,
                      "imerg_point_cell_mm_day": imerg * rng.uniform(0.7, 1.3, idx.size)}, index=idx)
    return f


def test_alignment_respects_final_run_end_and_missing():
    f = _frame(end="2026-03-31")
    f.iloc[10, 0] = np.nan  # an IMERG gap
    d = multisource.aligned_daily(f, date(2025, 9, 30))
    assert d.index.max() == pd.Timestamp("2025-09-30")
    assert pd.Timestamp("1998-01-11") not in d.index  # dropped, not filled
    assert not d.isna().any().any()


def test_monthly_totals_require_complete_months():
    f = _frame(end="1999-12-31")
    d = multisource.aligned_daily(f, date(2025, 9, 30)).drop(pd.Timestamp("1998-02-10"))
    mo = multisource.complete_monthly_totals(d)
    assert pd.Timestamp("1998-02-01") not in mo.index and pd.Timestamp("1998-03-01") in mo.index
    assert mo.loc["1998-03-01", "imerg"] == pytest.approx(d.loc["1998-03", "imerg"].sum())  # totals in mm


def test_compare_recovers_known_ratio():
    res = multisource.compare(_frame(scale=1.3, noise=0), date(2025, 9, 30))
    assert res["monthly"]["ratio_merra2_over_imerg"] == pytest.approx(1.3, rel=1e-9)
    assert res["monthly"]["pearson_r"] > 0.95
    assert res["annual"]["years"][0] == 1998 and res["annual"]["years"][-1] == 2024  # 2025 incomplete (Final ends Sep)
    assert not res["trend_comparison"]["imerg"]["significant_at_0_05"]


def test_compare_detects_divergent_trend():
    res = multisource.compare(_frame(scale=1.0, trend_merra=0.02), date(2025, 9, 30))
    t = res["trend_comparison"]
    assert t["difference_merra2_minus_imerg"]["significant_at_0_05"]
    assert t["difference_merra2_minus_imerg"]["sen_slope_per_decade"] > 0
    assert any("does not confirm" in s or "difference" in s for s in multisource.diagnostics(res))


def test_contingency_counts():
    d = pd.DataFrame({"merra2": [0.0, 2.0, 2.0, 0.5], "imerg": [0.0, 2.0, 0.0, 3.0]})
    c = multisource.contingency(d)
    assert (c["hits"], c["misses"], c["false_alarms"], c["correct_negatives"]) == (1, 1, 1, 1)
    assert c["pod"] == 0.5 and c["far"] == 0.5 and c["csi"] == pytest.approx(1 / 3)


def test_era_step_detected():
    years = list(range(1998, 2025))
    imerg = pd.Series(1000.0, index=years)
    merra = pd.Series([1100.0 if y <= 2013 else 1300.0 for y in years], index=years)
    e = multisource.era_step(pd.DataFrame({"merra2": merra, "imerg": imerg}))
    assert e["change_mm"] == pytest.approx(200.0) and e["mann_whitney_p"] < 0.01


def test_area_mean_requires_all_cells():
    cells = pd.DataFrame({"a": [1.0, 2.0, np.nan], "b": [3.0, 4.0, 5.0]})
    mean, n = imerg_power.area_mean(cells, pd.Series({"a": 0.25, "b": 0.75}))
    assert mean.iloc[0] == pytest.approx(2.5) and mean.iloc[1] == pytest.approx(3.5)
    assert np.isnan(mean.iloc[2]) and n.iloc[2] == 1  # never averaged over a partial set
    with pytest.raises(ValueError):
        imerg_power.area_mean(cells, pd.Series({"a": 0.5, "b": 0.6}))


def _power_doc(param, values: dict, ts="UTC"):
    return {
        "type": "Feature", "geometry": {"type": "Point", "coordinates": [81.0, 26.9, 117.0]},
        "properties": {"parameter": {param: values}},
        "header": {"api": {"version": "v2.10.3"}, "sources": ["IMERG"], "fill_value": -999.0, "time_standard": ts},
        "messages": [], "parameters": {param: {"units": "mm/day", "longname": param}},
    }


def test_imerg_download_and_process_synthetic(tmp_path):
    """End to end with SYNTHETIC POWER-shaped responses: download -> immutable raw -> process."""
    days = pd.date_range("2020-01-01", "2020-01-10", freq="D")
    box = grid.merra2_cell(LUCKNOW.latitude, LUCKNOW.longitude)
    cells = grid.imerg_cells_in(box)

    def get(url):
        if "system/manager/parameters" in url:
            return json.dumps({"IMERG_PRECTOT": {"units": "mm/day"}, "PRECTOTCORR": {"units": "mm/day"}}).encode()
        param = "IMERG_PRECTOT" if "IMERG_PRECTOT" in url else "PRECTOTCORR"
        vals = {d.strftime("%Y%m%d"): (2.0 if param == "IMERG_PRECTOT" else 3.0) for d in days}
        # the URL lists longitude before latitude
        vals["20200105"] = -999.0 if ("longitude=80.9500" in url and "latitude=26.7500" in url) else vals["20200105"]
        return json.dumps(_power_doc(param, vals)).encode()

    raw = imerg_power.download(LUCKNOW, date(2020, 1, 1), date(2020, 1, 10), raw_root=tmp_path / "raw", http_get=get, pause_s=0)
    assert len(list(raw.glob("cell_*.json"))) == len(cells) == 42
    prov = imerg_power.process(raw, processed_root=tmp_path / "processed")
    out = pd.read_csv(tmp_path / "processed" / "imerg" / prov["dataset_id"] / "daily.csv", index_col="date")
    assert out["imerg_area_mean_mm_day"].dropna().eq(2.0).all()
    assert np.isnan(out.loc["2020-01-05", "imerg_area_mean_mm_day"])  # one cell missing -> day missing
    assert out.loc["2020-01-05", "imerg_cells_valid"] == 41
    assert prov["point_cell"] == "26.85_80.95"
    DatasetMetadata.model_validate(prov["metadata"])  # common metadata interface
    assert prov["metadata"]["time_standard"] == "UTC"


def test_imerg_process_rejects_lst_response(tmp_path):
    def get(url):
        if "system/manager/parameters" in url:
            return json.dumps({"IMERG_PRECTOT": {"units": "mm/day"}, "PRECTOTCORR": {"units": "mm/day"}}).encode()
        param = "IMERG_PRECTOT" if "IMERG_PRECTOT" in url else "PRECTOTCORR"
        return json.dumps(_power_doc(param, {"20200101": 1.0}, ts="LST")).encode()

    raw = imerg_power.download(LUCKNOW, date(2020, 1, 1), date(2020, 1, 1), raw_root=tmp_path / "raw", http_get=get, pause_s=0)
    with pytest.raises(Exception, match="UTC"):
        imerg_power.process(raw, processed_root=tmp_path / "processed")


def test_download_writes_nothing_on_failure(tmp_path):
    n = {"calls": 0}

    def get(url):
        n["calls"] += 1
        if n["calls"] == 5:
            raise ConnectionError("reset")
        return json.dumps(_power_doc("IMERG_PRECTOT", {"20200101": 1.0})).encode()

    with pytest.raises(ConnectionError):
        imerg_power.download(LUCKNOW, date(2020, 1, 1), date(2020, 1, 1), raw_root=tmp_path / "raw", http_get=get, pause_s=0)
    assert not any((tmp_path / "raw").rglob("*.json"))
