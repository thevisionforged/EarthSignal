import json
from datetime import date

import pandas as pd
import pytest

from earthsignal.config import LUCKNOW
from earthsignal.data import ingest, power


def fake_getter(data_bytes: bytes, meta_bytes: bytes):
    calls = []

    def get(url: str) -> bytes:
        calls.append(url)
        return meta_bytes if "/system/manager/parameters" in url else data_bytes

    get.calls = calls
    return get


def test_download_stores_raw_bytes_unmodified(tmp_path, sample_bytes, metadata_bytes):
    getter = fake_getter(sample_bytes, metadata_bytes)
    raw_dir = ingest.download(LUCKNOW, date(2024, 1, 1), date(2024, 1, 5), raw_root=tmp_path, http_get=getter)
    assert (raw_dir / ingest.RAW_RESPONSE_NAME).read_bytes() == sample_bytes
    assert (raw_dir / ingest.RAW_METADATA_NAME).read_bytes() == metadata_bytes
    req = json.loads((raw_dir / ingest.RAW_REQUEST_NAME).read_text())
    assert req["request_url"] == getter.calls[0]
    assert req["requested_start"] == "2024-01-01" and req["requested_end"] == "2024-01-05"
    assert req["retrieved_at_utc"].endswith("+00:00")


def test_download_rejects_non_json_before_writing(tmp_path, metadata_bytes):
    getter = fake_getter(b"<html>error</html>", metadata_bytes)
    with pytest.raises(json.JSONDecodeError):
        ingest.download(LUCKNOW, date(2024, 1, 1), date(2024, 1, 5), raw_root=tmp_path, http_get=getter)
    assert not any(tmp_path.rglob("*.json"))


def test_process_writes_provenance_and_csv(tmp_path, sample_bytes, metadata_bytes):
    getter = fake_getter(sample_bytes, metadata_bytes)
    raw_dir = ingest.download(LUCKNOW, date(2024, 1, 1), date(2024, 1, 5), raw_root=tmp_path / "raw", http_get=getter)
    prov = ingest.process(raw_dir, processed_root=tmp_path / "processed")

    assert prov["api_version"] == "v2.10.3"
    assert prov["data_kind"] == "derived_estimate"
    assert prov["fill_value"] == -999.0
    assert prov["time_standard"] == "LST"
    assert prov["requested"]["latitude"] == LUCKNOW.latitude
    assert prov["variables"]["T2M"]["units"] == "C"
    assert "MERRA-2" in prov["variables"]["PRECTOTCORR"]["definition"]
    assert prov["raw_files"][0]["sha256"] == power.sha256_bytes(sample_bytes)
    assert prov["validation"]["passed"]
    assert "referencing" in prov["documentation"]

    csv = pd.read_csv(tmp_path / "processed" / prov["dataset_id"] / "daily.csv", index_col="date")
    assert list(csv.columns) == ["T2M", "PRECTOTCORR"]
    assert csv.loc["2024-01-01", "T2M"] == pytest.approx(13.61)
    # raw is untouched by processing
    assert (raw_dir / ingest.RAW_RESPONSE_NAME).read_bytes() == sample_bytes


def test_process_rejects_units_disagreeing_with_metadata(tmp_path, sample_bytes, metadata_bytes):
    meta = json.loads(metadata_bytes)
    meta["T2M"]["units"] = "F"
    getter = fake_getter(sample_bytes, json.dumps(meta).encode())
    raw_dir = ingest.download(LUCKNOW, date(2024, 1, 1), date(2024, 1, 5), raw_root=tmp_path / "raw", http_get=getter)
    with pytest.raises(power.PowerResponseError, match="metadata"):
        ingest.process(raw_dir, processed_root=tmp_path / "processed")


@pytest.mark.network
def test_live_power_api_small_request(tmp_path):
    """Live check against NASA POWER (opt in with: pytest -m network)."""
    raw_dir = ingest.download(LUCKNOW, date(2024, 1, 1), date(2024, 1, 3), raw_root=tmp_path / "raw")
    prov = ingest.process(raw_dir, processed_root=tmp_path / "processed")
    assert prov["validation"]["variables"]["T2M"]["n_valid"] == 3
