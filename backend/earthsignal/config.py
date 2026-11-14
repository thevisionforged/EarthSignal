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


# Point near central Lucknow (Hazratganj area). NASA POWER returns the value of the MERRA-2 grid
# cell (0.5 deg lat x 0.625 deg lon) containing the point, with no interpolation (verified
# 2026-11-15, DECISIONS D-013). CAUTION: 80.9462 E is only 0.009 deg east of the cell boundary
# at 80.9375 E. This point falls in the cell centred near (27.0 N, 81.25 E), which lies mostly EAST
# of the city. The Lucknow airport and old city stations (WMO 42369 and 42368) fall in the
# neighbouring cell centred near (27.0 N, 80.625 E).
LUCKNOW = StudyArea(
    name="Lucknow, Uttar Pradesh, India",
    latitude=26.8467,
    longitude=80.9462,
    note=(
        "Single point request; the value is that of the enclosing MERRA-2/GEOS-IT grid cell. The point "
        "lies just east of a cell boundary, so the cell mostly covers land east of the city (D-013)."
    ),
)
