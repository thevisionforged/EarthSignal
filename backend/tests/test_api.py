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
    return TestClient(create_app(processed_root=tmp_path / "processed"))


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


def test_provenance_endpoint(synthetic_client):
    body = synthetic_client.get("/api/provenance").json()
    assert body["request_url"].startswith("https://power.larc.nasa.gov/")
    assert body["raw_files"][0]["sha256"]
