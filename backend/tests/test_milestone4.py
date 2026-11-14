"""Milestone 4 tests: IMD and CPC readers, overlap weights, arbitration. All data SYNTHETIC."""

import gzip
import json
from datetime import date

import numpy as np
import pandas as pd
import pytest

from earthsignal.analysis import arbiter
from earthsignal.config import LUCKNOW, LUCKNOW_AIRPORT
from earthsignal.data import cpc, grid, imd


# ---------------- IMD binary ----------------

def _imd_bytes(year: int, fill_lucknow: float = 5.0) -> bytes:
    n = 366 if pd.Timestamp(year=year, month=12, day=31).is_leap_year else 365
    a = np.full((n, imd.NY, imd.NX), imd.UNDEF, dtype="<f4")
    j = int(round((26.75 - imd.LAT0) / imd.D)); i = int(round((81.0 - imd.LON0) / imd.D))
    a[:, j - 4:j + 4, i - 6:i + 6] = fill_lucknow  # rain only around Lucknow; elsewhere undefined
    a[:, 0, 0] = 1.0  # south-west corner marker (6.5N, 66.5E)
    return a.tobytes()


def test_imd_decoding_orientation_and_undef():
    arr = imd.read_grid(_imd_bytes(2023), 2023)
    assert arr.shape == (365, 129, 135)
    assert arr[0, 0, 0] == 1.0  # first record value is 6.5N, 66.5E (south-west), per IMD page
    assert np.isnan(arr[0, 128, 134])  # -999 -> NaN, never 0
    j = int(round((26.75 - imd.LAT0) / imd.D)); i = int(round((81.0 - imd.LON0) / imd.D))
    assert arr[10, j, i] == 5.0


def test_imd_rejects_wrong_byte_count(tmp_path):
    with pytest.raises(ValueError, match="expected"):
        imd.download_year(2023, raw_root=tmp_path, post=lambda y: (b"\0" * 100, {}))
    assert not any(tmp_path.rglob("*.grd"))


def test_imd_download_and_process(tmp_path):
    for y in (2020, 2021):
        imd.download_year(y, raw_root=tmp_path / "raw", post=lambda yy: (_imd_bytes(yy), {"content-type": "application/octet-stream"}))
    prov = imd.process(raw_root=tmp_path / "raw", processed_root=tmp_path / "processed")
    f = pd.read_csv(tmp_path / "processed" / "imd" / prov["dataset_id"] / "daily.csv", index_col="date")
    assert len(f) == 366 + 365
    assert f["imd_lucknow_mm_day"].eq(5.0).all() and f["imd_lucknow_airport_mm_day"].eq(5.0).all()
    assert prov["metadata"]["source_type"] == "imd_gridded"


def test_imd_area_mean_requires_all_boxes(tmp_path):
    raw = bytearray(_imd_bytes(2021))
    arr = np.frombuffer(bytes(raw), dtype="<f4").reshape(365, imd.NY, imd.NX).copy()
    b = grid.merra2_cell(LUCKNOW.latitude, LUCKNOW.longitude)
    w = grid.overlap_weights(imd.lats(), imd.lons(), imd.D, imd.D, b)
    # IMD boxes centred at 81.0 E span 80.875-81.125 and straddle the east/west boundary (80.9375),
    # so they belong to BOTH cells. Blank one that lies only in the eastern cell.
    j, i = next((j, i) for j, i, la, lo, *_ in w if lo >= 81.25)
    arr[3, j, i] = imd.UNDEF
    assert any(x[3] == 81.0 for x in w), "expected boundary-straddling boxes"
    imd.download_year(2021, raw_root=tmp_path / "raw", post=lambda y: (arr.tobytes(), {}))
    prov = imd.process(raw_root=tmp_path / "raw", processed_root=tmp_path / "p")
    f = pd.read_csv(tmp_path / "p" / "imd" / prov["dataset_id"] / "daily.csv", index_col="date")
    assert np.isnan(f.loc["2021-01-04", "imd_lucknow_mm_day"])  # one box missing -> day missing
    assert f.loc["2021-01-04", "imd_lucknow_airport_mm_day"] == 5.0


# ---------------- overlap weights ----------------

def test_overlap_weights_cover_box_area():
    for area in (LUCKNOW, LUCKNOW_AIRPORT):
        b = grid.merra2_cell(area.latitude, area.longitude)
        for lats_, lons_, d in ((imd.lats(), imd.lons(), 0.25), (cpc.lat_centres(), cpc.lon_centres(), 0.5)):
            w = grid.overlap_weights(lats_, lons_, d, d, b)
            assert sum(x[4] for x in w) * d * d == pytest.approx(0.5 * 0.625)
            assert sum(x[5] for x in w) == pytest.approx(1.0)


# ---------------- CPC ----------------

def test_cpc_ascii_parse():
    idx = (125, 126, 160, 163)
    lines = ["Dataset {", "} x;", "---------------------------------------------", "precip.precip[366][2][4]"]
    for t in range(366):
        for j in range(2):
            vals = ["1.5", "-9.96921E36", "0.0", "2.0"] if t == 0 else ["0.0"] * 4
            lines.append(f"[{t}][{j}], " + ", ".join(vals))
    arr = cpc.parse_ascii("\n".join(lines), 2024, idx)
    assert arr.shape == (366, 2, 4)
    assert arr[0, 0, 0] == 1.5 and np.isnan(arr[0, 0, 1])
    with pytest.raises(ValueError):
        cpc.parse_ascii("\n".join(lines[:-10]), 2024, idx)


def test_cpc_archive_day_units_and_gauges():
    a = np.full((2, cpc.NY_A, cpc.NX_A), -999.0, dtype="<f4")
    a[0, 233, 161] = 125.0  # 12.5 mm in 0.1 mm units
    a[1, 233, 161] = 3.0  # three gauges
    rain, g = cpc.read_archive_day(gzip.compress(a.tobytes()))
    assert rain[233, 161] == pytest.approx(12.5) and g[233, 161] == 3.0
    assert np.isnan(rain[0, 0])
    assert cpc.archive_lat_centres()[233] == pytest.approx(26.75)  # south-to-north grid
    with pytest.raises(ValueError):
        cpc.read_archive_day(b"\0" * 10)


def test_cpc_polite_get_honours_429():
    import httpx

    calls = []

    def flaky(url):
        calls.append(url)
        if len(calls) < 3:
            resp = httpx.Response(429, headers={"retry-after": "7"}, request=httpx.Request("GET", url))
            raise httpx.HTTPStatusError("429", request=resp.request, response=resp)
        return b"ok"

    waits = []
    assert cpc.polite_get("https://x", sleep=waits.append, get=flaky) == b"ok"
    assert waits == [7.0, 7.0]


# ---------------- arbitration ----------------

def _three(drift_merra=0.0, drift_imerg=0.0, step_merra_2006=0.0, seed=0):
    rng = np.random.default_rng(seed)
    idx = pd.date_range("1998-01-01", "2024-12-31", freq="D")
    season = np.clip(np.sin(2 * np.pi * (idx.day_of_year - 150) / 365.25), 0, None) * 10
    base = np.where(rng.random(idx.size) < 0.3, rng.gamma(1.0, 1.0, idx.size) * (1 + season), 0.0)
    yrs = (idx.year - 1998).to_numpy()
    def noisy():
        return base * rng.uniform(0.9, 1.1, idx.size)
    merra = noisy() * (1 + drift_merra * yrs) + np.where(idx.year >= 2006, step_merra_2006, 0.0)
    imerg = noisy() * (1 + drift_imerg * yrs)
    return pd.DataFrame({"merra2": merra, "imerg": imerg, "imd": noisy()}, index=idx)


def test_arbiter_identifies_drifting_product():
    res = arbiter.arbitrate(_three(drift_merra=0.03))
    v = arbiter.verdicts(res)
    assert res["vs_reference"]["merra2"]["difference_trend"]["significant_at_0_05"]
    assert not res["vs_reference"]["imerg"]["difference_trend"]["significant_at_0_05"]
    assert any("MERRA-2 (POWER) drifts away" in s for s in v)


def test_arbiter_neither_when_consistent():
    res = arbiter.arbitrate(_three())
    assert any("neither product drifts" in s for s in arbiter.verdicts(res))


def test_arbiter_step_at_preregistered_date():
    res = arbiter.arbitrate(_three(step_merra_2006=0.6))
    b = res["vs_reference"]["merra2"]["breaks"]["2006"]
    assert b["available"] and b["change_mm"] > 150 and b["mann_whitney_p"] < arbiter.BREAK_ALPHA
    assert any("Supporting evidence: MERRA-2 shifts" in s and "2006" in s for s in arbiter.verdicts(res))


def test_arbiter_requires_complete_months():
    d = _three()
    d.iloc[40, 2] = np.nan  # one IMD day missing in Feb 1998
    mo = arbiter.monthly_totals(d)
    assert pd.Timestamp("1998-02-01") not in mo.index and pd.Timestamp("1998-03-01") in mo.index
    assert 1998 not in arbiter.annual_totals(mo).index


def test_leave_one_out_flags_influential_year():
    years = list(range(1998, 2025))
    s = pd.Series([1000.0 + (y - 1998) * 0.5 for y in years], index=years)
    s.loc[1998] = 300.0  # one anomalous early year creates an upward trend
    rob = arbiter.leave_one_out(s)
    assert rob["most_influential_year"] == 1998 and rob["n_cases"] == 27


def test_arbitration_endpoint(tmp_path):
    """SYNTHETIC IMERG/MERRA-2 (POWER-shaped) and IMD (binary-shaped) through the real pipelines and API."""
    from fastapi.testclient import TestClient

    from earthsignal.api.main import create_app

    from .test_api import _imerg_synthetic

    client = TestClient(create_app(processed_root=tmp_path / "processed"))
    _imerg_synthetic(tmp_path, LUCKNOW, start="1998-01-01", end="2012-12-31")
    assert client.get("/api/precip-arbitration").status_code == 404  # no IMD yet
    for y in range(1998, 2013):
        imd.download_year(y, raw_root=tmp_path / "raw", post=lambda yy: (_imd_bytes(yy, 3.0), {}))
    imd.process(raw_root=tmp_path / "raw", processed_root=tmp_path / "processed")
    body = client.get("/api/precip-arbitration").json()
    assert body["period"] == [1998, 2012] and body["n_years"] == 15
    assert set(body["trends"]) == {"merra2", "imerg", "imd"}
    assert body["verdicts"] and body["method"]
    assert body["cpc_gauge_counts"] is None  # gauge sample not processed in this temp dir
    assert client.get("/api/precip-arbitration", params={"area": "nope"}).status_code == 422


def test_cpc_archive_url_variants_cover_observed_names():
    urls = cpc.archive_urls(date(2006, 7, 15))
    assert any(u.endswith("20060715RT.gz") for u in urls)
    assert any(u.endswith("20070715.RT.gz") for u in cpc.archive_urls(date(2007, 7, 15)))
    assert cpc.archive_urls(date(2014, 7, 15))[0].endswith("20140715.RT")
    assert cpc.archive_urls(date(2004, 7, 15))[0].endswith("20040715.gz")


def test_gauge_samples_merge_and_count(tmp_path):
    a = np.full((2, cpc.NY_A, cpc.NX_A), -999.0, dtype="<f4")
    a[0] = 0.0
    a[1] = 0.0
    j = int(np.argmin(abs(cpc.archive_lat_centres() - 26.75)))
    i = int(np.argmin(abs(cpc.lon_centres() - 81.25)))
    a[1, j, i] = 2.0  # two gauges inside the eastern cell's main CPC box
    a[1, j + 2, i + 2] = 3.0  # three more within +-2 deg
    a[1, 0, 0] = 5.0  # far away: global count only
    payload = gzip.compress(a.tobytes())
    status = lambda url: (200, payload) if url.endswith(".gz") else (404, b"")
    cpc.download_gauge_sample([date(2004, 7, 15)], raw_root=tmp_path, http_status=status, pause_s=0)
    cpc.download_gauge_sample([date(2007, 7, 15)], raw_root=tmp_path, http_status=status, pause_s=0)
    out = cpc.process_gauge_samples(raw_root=tmp_path, processed_root=tmp_path / "p")
    rows = out["areas"]["lucknow"]
    assert [r["date"] for r in rows] == ["2004-07-15", "2007-07-15"]
    assert [r["version"] for r in rows] == ["V1.0", "RT"]
    assert rows[0]["gauges_in_cell_boxes"] == 2 and rows[0]["gauges_in_neighbourhood"] == 5
    assert rows[0]["gauges_global"] == 10
