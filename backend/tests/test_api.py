import json
from datetime import date

import pytest
from fastapi.testclient import TestClient

from earthsignal.api.main import create_app
from earthsignal.config import LUCKNOW
from earthsignal.data import ingest

from .conftest import synthetic_power_doc


@pytest.fixture
def empty_client(tmp_path):
    return TestClient(create_app(processed_root=tmp_path / "empty_processed"))


@pytest.fixture
def synthetic_client(tmp_path, sample_doc, metadata_bytes):
    """API backed by a SYNTHETIC multi-year dataset in a temp dir (never the real data/ folder)."""
    doc = synthetic_power_doc(sample_doc, "1990-01-01", "2020-12-31")
    data_bytes = json.dumps(doc).encode()

    def get(url):
        return metadata_bytes if "/system/manager/parameters" in url else data_bytes

    raw_dir = ingest.download(LUCKNOW, date(1990, 1, 1), date(2020, 12, 31), raw_root=tmp_path / "raw", http_get=get)
    ingest.process(raw_dir, processed_root=tmp_path / "processed")
    return TestClient(create_app(processed_root=tmp_path / "processed"))


def test_health(empty_client):
    r = empty_client.get("/api/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"
    assert r.json()["datasets_available"] == 0


def test_root_lists_endpoints(empty_client):
    r = empty_client.get("/")
    assert r.status_code == 200
    assert "/api/health" in r.json()["endpoints"]


def test_datasets_listing(synthetic_client, empty_client):
    assert empty_client.get("/api/datasets").json() == []
    rows = synthetic_client.get("/api/datasets").json()
    assert len(rows) == 1
    assert rows[0]["data_kind"] == "derived_estimate"


def test_no_data_is_404_not_fake(empty_client):
    r = empty_client.get("/api/timeseries")
    assert r.status_code == 404
    assert "ingest" in r.json()["detail"]
    assert empty_client.get("/api/trend").status_code == 404


def test_timeseries_monthly(synthetic_client):
    r = synthetic_client.get("/api/timeseries", params={"variable": "T2M", "resolution": "monthly"})
    body = r.json()
    assert r.status_code == 200
    assert body["units"] == "C"
    assert body["data_kind"] == "derived_estimate"
    assert len(body["dates"]) == len(body["values"]) == 31 * 12
    assert body["dates"][0] == "1990-01"


def test_timeseries_rejects_unknown_variable(synthetic_client):
    assert synthetic_client.get("/api/timeseries", params={"variable": "FOO"}).status_code == 422


def test_trend_endpoint(synthetic_client):
    r = synthetic_client.get("/api/trend", params={"variable": "T2M"})
    body = r.json()
    assert r.status_code == 200
    res = body["result"]
    assert res["n_years"] == 31
    assert res["data_kind"] == "derived_statistic"
    assert res["sen_slope_per_decade"] == pytest.approx(0.3, abs=0.2)  # synthetic trend 0.03 C/yr
    assert len(body["annual_means"]["years"]) == 31


def test_seasonal_endpoint(synthetic_client):
    body = synthetic_client.get("/api/seasonal", params={"variable": "T2M"}).json()
    assert [s["season"] for s in body["seasons"]] == ["winter", "pre_monsoon", "monsoon", "post_monsoon"]
    assert all(0 <= s["bh_adjusted_p"] <= 1 for s in body["seasons"])


def test_sensitivity_endpoint(synthetic_client):
    body = synthetic_client.get("/api/sensitivity", params={"variable": "T2M"}).json()
    assert body["min_window_years"] == 20
    assert len(body["vary_start"]) == 31 - 20 + 1
    assert body["source_periods"] is None  # probe not run for synthetic data
    assert body["geosit_in_trend_window"] is None


def test_areas_are_kept_separate(tmp_path, sample_doc, metadata_bytes):
    """SYNTHETIC data for two areas: each area's endpoints must use only its own dataset."""
    from earthsignal.config import LUCKNOW_AIRPORT

    for area, trend_per_year in ((LUCKNOW, 0.0), (LUCKNOW_AIRPORT, 0.08)):
        doc = synthetic_power_doc(sample_doc, "1990-01-01", "2020-12-31", seed=1, trend_per_year=trend_per_year)
        payload = json.dumps(doc).encode()
        get = lambda url, p=payload: metadata_bytes if "/system/manager/parameters" in url else p
        raw = ingest.download(area, date(1990, 1, 1), date(2020, 12, 31), raw_root=tmp_path / "raw", http_get=get)
        ingest.process(raw, processed_root=tmp_path / "processed")
    client = TestClient(create_app(processed_root=tmp_path / "processed"))

    areas = {a["key"]: a for a in client.get("/api/areas").json()}
    assert areas["lucknow"]["dataset_id"].startswith("power_daily_lucknow_1990")
    assert areas["lucknow_airport"]["dataset_id"].startswith("power_daily_lucknow_airport_")
    east = client.get("/api/trend", params={"area": "lucknow"}).json()["result"]["sen_slope_per_decade"]
    west = client.get("/api/trend", params={"area": "lucknow_airport"}).json()["result"]["sen_slope_per_decade"]
    assert abs(east) < 0.3 and west == pytest.approx(0.8, abs=0.3)
    assert client.get("/api/provenance", params={"area": "lucknow_airport"}).json()["requested"]["longitude"] == 80.889
    assert client.get("/api/trend", params={"area": "nowhere"}).status_code == 422
    assert {d["area"] for d in client.get("/api/datasets").json()} == {"lucknow", "lucknow_airport"}


def test_missing_area_data_is_404(synthetic_client):
    r = synthetic_client.get("/api/trend", params={"area": "lucknow_airport"})
    assert r.status_code == 404 and "--area lucknow_airport" in r.json()["detail"]


def test_station_comparison_endpoint(tmp_path, sample_doc, metadata_bytes):
    """SYNTHETIC POWER (airport area) and SYNTHETIC GSOD-format station files."""
    from earthsignal.config import LUCKNOW_AIRPORT
    from earthsignal.data import gsod

    from .test_gsod import row, year_csv

    doc = synthetic_power_doc(sample_doc, "2005-01-01", "2020-12-31", seed=3, trend_per_year=0.0)
    payload = json.dumps(doc).encode()
    get = lambda url: metadata_bytes if "/system/manager/parameters" in url else payload
    raw = ingest.download(LUCKNOW_AIRPORT, date(2005, 1, 1), date(2020, 12, 31), raw_root=tmp_path / "raw", http_get=get)
    ingest.process(raw, processed_root=tmp_path / "processed")
    client = TestClient(create_app(processed_root=tmp_path / "processed"))
    assert client.get("/api/station-comparison").status_code == 404  # no station data yet

    t2m = doc["properties"]["parameter"]["T2M"]
    files = {}
    for year in range(2005, 2021):
        rows = [
            row(f"{k[:4]}-{k[4:6]}-{k[6:]}", round(v * 9 / 5 + 32 + 0.9, 1), 24, "0.00", "G")
            for k, v in t2m.items() if k.startswith(str(year))
        ]
        files[year] = year_csv(rows)
    sraw = gsod.download("42369099999", range(2005, 2021), raw_root=tmp_path / "raw",
                         http_get_status=lambda url: (200, files[int(url.split("/")[-2])]))
    gsod.process(sraw, processed_root=tmp_path / "processed")

    body = client.get("/api/station-comparison").json()
    m = body["metrics_primary"]
    assert m["mean_bias"] == pytest.approx(-0.5, abs=0.06)  # station = POWER + 0.9 F (0.5 C)
    assert m["pearson_r"] > 0.999
    assert "WMO Resolution 40" in body["licence_notice"]
    assert body["power_area"] == "lucknow_airport"
    assert body["diagnostics"] and body["limitations"]


def test_backtest_endpoint(synthetic_client):
    body = synthetic_client.get("/api/backtest", params={"variable": "T2M"}).json()
    assert body["not_a_forecast"] is True and body["data_kind"] == "evaluation_statistic"
    assert body["test_years"] == [2011, 2020]  # synthetic data 1990-2020: 20 training years + gap
    assert [L["lead_days"] for L in body["by_lead"]] == [1, 3, 7, 14, 30]
    assert body["by_lead"][0]["pooled"]["climatology"]["skill_vs_climatology"] == pytest.approx(0.0)


def test_provenance_endpoint(synthetic_client):
    body = synthetic_client.get("/api/provenance").json()
    assert body["request_url"].startswith("https://power.larc.nasa.gov/")
    assert body["raw_files"][0]["sha256"]
