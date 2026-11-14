"""Study-area definition and filesystem locations."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = Path(os.environ.get("EARTHSIGNAL_DATA_DIR", REPO_ROOT / "data"))
RAW_DIR = DATA_DIR / "raw"
PROCESSED_DIR = DATA_DIR / "processed"


@dataclass(frozen=True)
class StudyArea:
    name: str
    latitude: float
    longitude: float
    note: str


# Point near central Lucknow (Hazratganj area). NASA POWER returns the value of the
# source grid cell (MERRA-2: 0.5 deg lat x 0.625 deg lon) containing this point, so the
# result represents an area of roughly 55 km x 62 km, not a city-scale measurement.
LUCKNOW = StudyArea(
    name="Lucknow, Uttar Pradesh, India",
    latitude=26.8467,
    longitude=80.9462,
    note="Single point request; value represents the enclosing MERRA-2/GEOS-IT grid cell.",
)
