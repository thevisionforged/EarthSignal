"""GSOD parsing and comparison tests.

All station data here is SYNTHETIC, written in GSOD's CSV column layout. Real GSOD files are never
stored in the repository, because non-U.S. GSOD data is subject to WMO Resolution 40 (DECISIONS D-014).
"""

import json

import numpy as np
import pandas as pd
import pytest

from earthsignal.analysis import compare
from earthsignal.data import gsod

HEADER = (
    '"STATION","DATE","LATITUDE","LONGITUDE","ELEVATION","NAME","TEMP","TEMP_ATTRIBUTES","DEWP",'
    '"DEWP_ATTRIBUTES","SLP","SLP_ATTRIBUTES","STP","STP_ATTRIBUTES","VISIB","VISIB_ATTRIBUTES","WDSP",'
    '"WDSP_ATTRIBUTES","MXSPD","GUST","MAX","MAX_ATTRIBUTES","MIN","MIN_ATTRIBUTES","PRCP","PRCP_ATTRIBUTES",'
    '"SNDP","FRSHTT"'
)


def row(date, temp_f, obs, prcp, flag, tmax=9999.9, tmin=9999.9):
    return (
        f'"42369099999","{date}","26.760594","80.889339","124.96","LUCKNOW, IN","{temp_f}","{obs:>3}",'
        f'"50.0","24","9999.9"," 0","999.9"," 0","2.0","24","3.0","24","5.1","999.9","{tmax}","","{tmin}","*",'
        f'"{prcp}","{flag}","999.9","000000"'
    )


def year_csv(rows):
    return ("\n".join([HEADER, *rows]) + "\n").encode()


def test_parse_units_and_missing_values():
    payload = year_csv([
        row("2024-01-01", 50.0, 24, "0.10", "G", tmax=59.0, tmin=41.0),
        row("2024-01-02", 9999.9, 0, "99.99", " "),
        row("2024-01-03", 68.0, 6, "0.00", "I"),
        row("2024-01-04", 32.0, 24, "0.00", "G"),
    ])
    df = gsod.parse_year(payload)
    assert df.loc["2024-01-01", "tmean_c"] == pytest.approx(10.0)
    assert df.loc["2024-01-01", "tmax_c"] == pytest.approx(15.0)
    assert df.loc["2024-01-01", "prcp_mm"] == pytest.approx(2.54)
    assert np.isnan(df.loc["2024-01-02", "tmean_c"]) and np.isnan(df.loc["2024-01-02", "prcp_mm"])
    assert np.isnan(df.loc["2024-01-03", "prcp_mm"])  # flag I: no report -> missing, NOT zero
    assert df.loc["2024-01-04", "prcp_mm"] == 0.0  # a real reported zero stays zero
    assert df.loc["2024-01-03", "temp_obs"] == 6
    assert df.loc["2024-01-01", "tmin_c"] == pytest.approx(5.0)
    assert np.isnan(df.loc["2024-01-02", "tmax_c"]) and np.isnan(df.loc["2024-01-02", "tmin_c"])


def test_download_records_404_and_is_immutable(tmp_path):
    payload = year_csv([row("2023-01-01", 50.0, 24, "0.00", "G")])

    def get(url):
        return (404, b"") if "/2022/" in url else (200, payload)

    raw = gsod.download("42369099999", range(2022, 2024), raw_root=tmp_path, http_get_status=get)
    req = json.loads((raw / "request.json").read_text())
    assert [f["http_status"] for f in req["files"]] == [404, 200]
    assert (raw / "2023.csv").read_bytes() == payload
    with pytest.raises(FileExistsError):
        gsod.power.write_immutable(raw / "2023.csv", b"x")
    prov = gsod.process(raw, processed_root=tmp_path / "processed")
    assert prov["years_missing_on_server"] == [2022]
    assert prov["data_kind"] == "observed"
    assert "WMO Resolution 40" in prov["licence_notice"]


def _synthetic_pair(years=range(2000, 2024), drift_per_year=0.0, obs_before=6, switch_year=2005, seed=0):
    """SYNTHETIC POWER and station daily series sharing weather noise; the station has a +0.5 C offset."""
    rng = np.random.default_rng(seed)
    idx = pd.date_range(f"{years.start}-01-01", f"{years.stop - 1}-12-31", freq="D")
    t = (idx - idx[0]).days / 365.25
    weather = 25 + 8 * np.sin(2 * np.pi * (idx.day_of_year - 100) / 365.25) + rng.normal(0, 1.5, idx.size)
    power = pd.Series(weather + drift_per_year * t, index=idx)
    station = pd.DataFrame(
        {
            "tmean_c": weather + 0.5 + rng.normal(0, 0.3, idx.size),
            "temp_obs": np.where(idx.year < switch_year, obs_before, 24),
        },
        index=idx,
    )
    return power, station


def test_comparison_uses_only_high_observation_days():
    power, station = _synthetic_pair()
    res = compare.compare_temperature(power, station)
    m = res["metrics_primary"]
    assert m["first_month"] == "2005-01"  # pre-2005 days have 6 obs and are excluded
    assert m["mean_bias"] == pytest.approx(-0.5, abs=0.05)
    assert m["pearson_r"] > 0.98
    assert res["trend_comparison"]["years"][0] == 2005
    assert not res["trend_comparison"]["difference_power_minus_station"]["significant_at_0_05"]


def test_comparison_detects_drift():
    power, station = _synthetic_pair(drift_per_year=-0.05)
    res = compare.compare_temperature(power, station)
    d = res["trend_comparison"]["difference_power_minus_station"]
    assert d["significant_at_0_05"] and d["sen_slope_per_decade"] == pytest.approx(-0.5, abs=0.15)
    assert any("drift apart" in s for s in compare.comparison_diagnostics(res))


def test_annual_anomalies_require_min_months():
    idx = pd.date_range("2010-01-01", "2012-12-01", freq="MS")
    p = pd.Series(np.arange(len(idx), dtype=float), index=idx)
    s = p + 1.0
    s.loc["2011-01-01":"2011-04-01"] = np.nan  # 2011 keeps only 8 paired months
    ann = compare.annual_anomalies(pd.concat({"p": p, "s": s}, axis=1).dropna())
    assert list(ann.index) == [2010, 2012]


def test_too_few_months_rejected():
    idx = pd.date_range("2020-01-01", "2021-06-01", freq="MS")
    s = pd.Series(1.0, index=idx)
    with pytest.raises(ValueError, match="paired months"):
        compare.pair_metrics(s, s)
