import copy
import math
from datetime import date

import numpy as np
import pytest

from earthsignal.data import power

PARAMS = ("T2M", "PRECTOTCORR")


def test_url_contains_request_details():
    url = power.build_daily_point_url(26.8467, 80.9462, date(1981, 1, 1), date(2025, 12, 31))
    assert url.startswith("https://power.larc.nasa.gov/api/temporal/daily/point?")
    for part in ["parameters=T2M,PRECTOTCORR", "latitude=26.8467", "longitude=80.9462",
                 "start=19810101", "end=20251231", "time-standard=LST", "format=JSON", "community=AG"]:
        assert part in url


def test_url_rejects_bad_input():
    with pytest.raises(ValueError):
        power.build_daily_point_url(26.8, 80.9, date(2020, 1, 2), date(2020, 1, 1))
    with pytest.raises(ValueError):
        power.build_daily_point_url(95, 80.9, date(2020, 1, 1), date(2020, 1, 2))


def test_parse_recorded_response(sample_doc):
    parsed = power.parse_daily_point(sample_doc, PARAMS)
    f = parsed.frame
    assert len(f) == 5
    assert f.index[0].date() == date(2024, 1, 1)
    assert f.loc["2024-01-01", "T2M"] == pytest.approx(13.61)
    assert f.loc["2024-01-05", "PRECTOTCORR"] == pytest.approx(0.42)
    assert parsed.units == {"T2M": "C", "PRECTOTCORR": "mm/day"}
    assert parsed.fill_value == -999.0
    assert parsed.api_version == "v2.10.3"
    assert parsed.sources == ["MERRA2"]
    assert parsed.time_standard == "LST"
    assert parsed.returned_coordinates["latitude"] == pytest.approx(26.847)


def test_fill_value_becomes_nan_never_zero(sample_doc):
    doc = copy.deepcopy(sample_doc)
    doc["properties"]["parameter"]["T2M"]["20240103"] = -999.0
    doc["properties"]["parameter"]["PRECTOTCORR"]["20240104"] = -999.0
    f = power.parse_daily_point(doc, PARAMS).frame
    assert math.isnan(f.loc["2024-01-03", "T2M"])
    assert math.isnan(f.loc["2024-01-04", "PRECTOTCORR"])
    # genuine zero precipitation stays zero
    assert f.loc["2024-01-01", "PRECTOTCORR"] == 0.0
    assert not (f == -999.0).any().any()


def test_fill_value_read_from_header_not_hardcoded(sample_doc):
    doc = copy.deepcopy(sample_doc)
    doc["header"]["fill_value"] = -9999.0
    doc["properties"]["parameter"]["T2M"]["20240102"] = -9999.0
    f = power.parse_daily_point(doc, PARAMS).frame
    assert math.isnan(f.loc["2024-01-02", "T2M"])


def test_missing_fill_value_header_is_rejected(sample_doc):
    doc = copy.deepcopy(sample_doc)
    del doc["header"]["fill_value"]
    with pytest.raises(power.PowerResponseError, match="fill_value"):
        power.parse_daily_point(doc, PARAMS)


def test_unexpected_units_rejected(sample_doc):
    doc = copy.deepcopy(sample_doc)
    doc["parameters"]["T2M"]["units"] = "K"
    with pytest.raises(power.PowerResponseError, match="units"):
        power.parse_daily_point(doc, PARAMS)


def test_missing_parameter_rejected(sample_doc):
    doc = copy.deepcopy(sample_doc)
    del doc["properties"]["parameter"]["PRECTOTCORR"]
    with pytest.raises(power.PowerResponseError, match="missing"):
        power.parse_daily_point(doc, PARAMS)


def test_malformed_structure_rejected():
    with pytest.raises(power.PowerResponseError):
        power.parse_daily_point({"header": {}}, PARAMS)


def test_validate_recorded_response_passes(sample_doc):
    f = power.parse_daily_point(sample_doc, PARAMS).frame
    report = power.validate_frame(f, date(2024, 1, 1), date(2024, 1, 5))
    assert report["passed"]
    assert report["variables"]["T2M"]["n_valid"] == 5
    assert report["warnings"] == []


def test_validate_detects_absent_dates(sample_doc):
    f = power.parse_daily_point(sample_doc, PARAMS).frame
    report = power.validate_frame(f, date(2024, 1, 1), date(2024, 1, 7))
    assert not report["passed"]
    assert any("absent" in e for e in report["errors"])


def test_validate_classifies_trailing_vs_interior_missing(sample_doc):
    doc = copy.deepcopy(sample_doc)
    doc["properties"]["parameter"]["T2M"]["20240102"] = -999.0  # interior
    doc["properties"]["parameter"]["T2M"]["20240105"] = -999.0  # trailing (latency-like)
    f = power.parse_daily_point(doc, PARAMS).frame
    info = power.validate_frame(f, date(2024, 1, 1), date(2024, 1, 5))["variables"]["T2M"]
    assert info["n_missing_interior"] == 1
    assert info["n_missing_trailing"] == 1
    assert info["last_valid"] == "2024-01-04"


def test_validate_flags_but_keeps_implausible_values(sample_doc):
    doc = copy.deepcopy(sample_doc)
    doc["properties"]["parameter"]["T2M"]["20240102"] = 75.0
    f = power.parse_daily_point(doc, PARAMS).frame
    report = power.validate_frame(f, date(2024, 1, 1), date(2024, 1, 5))
    assert report["variables"]["T2M"]["n_out_of_plausible_range"] == 1
    assert f.loc["2024-01-02", "T2M"] == 75.0  # flagged, not altered


def test_write_immutable_refuses_overwrite(tmp_path):
    p = tmp_path / "raw.json"
    power.write_immutable(p, b"original")
    with pytest.raises(FileExistsError):
        power.write_immutable(p, b"changed")
    assert p.read_bytes() == b"original"


def test_sha256():
    assert power.sha256_bytes(b"") == "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
