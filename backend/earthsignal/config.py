"""Study-area definition and filesystem locations."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = Path(os.environ.get("EARTHSIGNAL_DATA_DIR", REPO_ROOT / "data"))
RAW_DIR = DATA_DIR / "raw"
PROCESSED_DIR = DATA_DIR / "processed"


def _flag(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class DeploySettings:
    """Deployment switches, all off by default so local development is unchanged (D-027).

    EARTHSIGNAL_FRONTEND_DIST  path to the built frontend (frontend/dist); when set, the API also serves the UI
    EARTHSIGNAL_CORS_ORIGINS   comma-separated origins allowed to call the API from another domain (split deploy only)
    EARTHSIGNAL_WARMUP         1 = compute the forecast evaluation in the background at startup
    EARTHSIGNAL_PUBLIC_DEMO    1 = tell visitors that analyst cases are shared and reset when the server restarts
    EARTHSIGNAL_CACHE_DIR      folder for the cached forecast evaluation (deploy: filled at build time)
    """

    frontend_dist: Path | None = None
    cors_origins: tuple[str, ...] = ()
    warmup: bool = False
    public_demo: bool = False
    cache_dir: Path | None = None

    @classmethod
    def from_env(cls) -> "DeploySettings":
        dist = os.environ.get("EARTHSIGNAL_FRONTEND_DIST", "").strip()
        origins = tuple(o.strip().rstrip("/") for o in os.environ.get("EARTHSIGNAL_CORS_ORIGINS", "").split(",") if o.strip())
        return cls(
            frontend_dist=Path(dist) if dist else None,
            cors_origins=origins,
            warmup=_flag("EARTHSIGNAL_WARMUP"),
            public_demo=_flag("EARTHSIGNAL_PUBLIC_DEMO"),
            cache_dir=Path(c) if (c := os.environ.get("EARTHSIGNAL_CACHE_DIR", "").strip()) else None,
        )


@dataclass(frozen=True)
class StudyArea:
    name: str
    latitude: float
    longitude: float
    note: str
    key: str = "lucknow"
    label: str = ""

    def matches(self, latitude: float, longitude: float, tol: float = 1e-4) -> bool:
        return abs(self.latitude - latitude) < tol and abs(self.longitude - longitude) < tol


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
    key="lucknow",
    label="Eastern cell (central Lucknow point)",
)

# Coordinates of the Lucknow airport station (NOAA GSOD 42369099999, as given in its 2024 file).
# Requesting POWER here returns the western cell, which also contains the old city station 42368.
LUCKNOW_AIRPORT = StudyArea(
    name="Lucknow airport (Chaudhary Charan Singh Intl), Uttar Pradesh, India",
    latitude=26.761,
    longitude=80.889,
    note=(
        "Point at the Lucknow airport weather station; the value is that of the enclosing MERRA-2/GEOS-IT "
        "grid cell (centred near 27.0 N, 80.625 E), which covers the airport and western Lucknow (D-013)."
    ),
    key="lucknow_airport",
    label="Western cell (Lucknow airport station)",
)

STUDY_AREAS: dict[str, StudyArea] = {a.key: a for a in (LUCKNOW, LUCKNOW_AIRPORT)}
DEFAULT_AREA = LUCKNOW.key
