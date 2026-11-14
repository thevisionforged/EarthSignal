"""Shared fixtures.

`power_daily_sample.json` and `power_parameter_metadata_sample.json` are REAL NASA POWER API
responses recorded on 2026-11-14 (Lucknow, 2024-01-01..2024-01-05). They are stored byte-for-byte.

`synthetic_power_doc` builds a CLEARLY SYNTHETIC document with the same structure, used only to
exercise multi-year code paths in tests. It is never written to data/ and never served as real data.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def sample_bytes() -> bytes:
    return (FIXTURES / "power_daily_sample.json").read_bytes()


@pytest.fixture
def sample_doc(sample_bytes) -> dict:
    return json.loads(sample_bytes)


@pytest.fixture
def metadata_bytes() -> bytes:
    return (FIXTURES / "power_parameter_metadata_sample.json").read_bytes()


def synthetic_power_doc(template: dict, start: str, end: str, seed: int = 0, trend_per_year: float = 0.03) -> dict:
    """SYNTHETIC POWER-shaped document (test use only)."""
    rng = np.random.default_rng(seed)
    days = pd.date_range(start, end, freq="D")
    t_years = (days - days[0]).days / 365.25
    seasonal = 26 + 8 * np.sin(2 * np.pi * (days.day_of_year - 100) / 365.25)
    t2m = seasonal + trend_per_year * t_years + rng.normal(0, 1.0, days.size)
    pr = np.clip(rng.gamma(0.3, 8.0, days.size), 0, None)
    doc = copy.deepcopy(template)
    keys = [d.strftime("%Y%m%d") for d in days]
    doc["properties"]["parameter"] = {
        "T2M": dict(zip(keys, np.round(t2m, 2).tolist())),
        "PRECTOTCORR": dict(zip(keys, np.round(pr, 2).tolist())),
    }
    doc["header"]["start"], doc["header"]["end"] = keys[0], keys[-1]
    return doc
