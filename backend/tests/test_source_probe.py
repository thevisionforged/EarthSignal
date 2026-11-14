import json
from datetime import date
from urllib.parse import parse_qs, urlparse

import pytest

from earthsignal.config import LUCKNOW
from earthsignal.data import source_probe


def fake_power(boundary: date | None, calls: list):
    """Fake single-day POWER responses: MERRA2 before `boundary`, GEOSIT on/after it."""

    def get(url: str) -> bytes:
        q = parse_qs(urlparse(url).query)
        day = date.fromisoformat(f"{q['start'][0][:4]}-{q['start'][0][4:6]}-{q['start'][0][6:]}")
        assert q["start"] == q["end"]
        calls.append(day)
        src = "GEOSIT" if boundary and day >= boundary else "MERRA2"
        return json.dumps({"header": {"sources": [src]}}).encode()

    return get


def test_binary_search_finds_boundary():
    calls = []
    res = source_probe.find_boundary(LUCKNOW, date(2020, 1, 1), date(2026, 11, 11), fake_power(date(2026, 9, 3), calls))
    assert res["last_merra2_day"] == "2026-09-02"
    assert res["first_geosit_day"] == "2026-09-03"
    assert len(calls) <= 14  # log2(~2500 days) + 2 endpoints


def test_no_geosit():
    res = source_probe.find_boundary(LUCKNOW, date(2020, 1, 1), date(2020, 6, 1), fake_power(None, []))
    assert res["geosit_present"] is False


def test_start_must_be_merra2():
    with pytest.raises(ValueError, match="MERRA2"):
        source_probe.find_boundary(LUCKNOW, date(2020, 1, 1), date(2020, 6, 1), fake_power(date(2019, 1, 1), []))
