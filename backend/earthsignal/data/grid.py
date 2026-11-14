"""Grid geometry for MERRA-2 (NASA POWER meteorology) and GPM IMERG cells.

MERRA-2: cell centres at latitude -90 + 0.5*i and longitude -180 + 0.625*j, so a cell spans
+-0.25 deg latitude and +-0.3125 deg longitude. Verified 2026-11-15 by live POWER requests on both
sides of every edge of the two Lucknow cells (DECISIONS D-017): eastern cell 26.75-27.25 N,
80.9375-81.5625 E; western cell 26.75-27.25 N, 80.3125-80.9375 E.

IMERG: 0.1 deg cells with edges on multiples of 0.1 deg (verified: points anywhere inside
26.8-26.9 N x 80.9-81.0 E return identical POWER IMERG values; points across an edge differ).

Area weights use the overlap fraction times cos(latitude). Within half a degree the cosine term
changes weights by under 1%, but it is included for correctness.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

MERRA2_DLAT, MERRA2_DLON = 0.5, 0.625
IMERG_D = 0.1


@dataclass(frozen=True)
class Box:
    south: float
    north: float
    west: float
    east: float

    def as_dict(self) -> dict:
        return {"south": self.south, "north": self.north, "west": self.west, "east": self.east}


def merra2_cell(lat: float, lon: float) -> Box:
    """MERRA-2 grid cell containing (lat, lon). Points exactly on an edge are ambiguous; avoid them."""
    i = round((lat + 90.0) / MERRA2_DLAT)
    j = round((lon + 180.0) / MERRA2_DLON)
    clat, clon = -90.0 + i * MERRA2_DLAT, -180.0 + j * MERRA2_DLON
    return Box(clat - MERRA2_DLAT / 2, clat + MERRA2_DLAT / 2, clon - MERRA2_DLON / 2, clon + MERRA2_DLON / 2)


@dataclass(frozen=True)
class SubCell:
    lat: float  # IMERG cell centre
    lon: float
    overlap_fraction: float  # fraction of the IMERG cell inside the box
    weight: float  # overlap_fraction * cos(lat), normalised so weights sum to 1


def _edges(lo: float, hi: float, d: float) -> list[tuple[float, float]]:
    k0, k1 = math.floor(round(lo / d, 9)), math.ceil(round(hi / d, 9))
    return [(round(k * d, 6), round((k + 1) * d, 6)) for k in range(k0, k1)]


def imerg_cells_in(box: Box) -> list[SubCell]:
    """All IMERG 0.1 deg cells overlapping `box`, with area weights for an area-mean over `box`."""
    raw = []
    for s, n in _edges(box.south, box.north, IMERG_D):
        fy = (min(n, box.north) - max(s, box.south)) / IMERG_D
        for w, e in _edges(box.west, box.east, IMERG_D):
            fx = (min(e, box.east) - max(w, box.west)) / IMERG_D
            if fx <= 0 or fy <= 0:
                continue
            clat, clon = round((s + n) / 2, 6), round((w + e) / 2, 6)
            raw.append((clat, clon, fx * fy, fx * fy * math.cos(math.radians(clat))))
    total = sum(r[3] for r in raw)
    return [SubCell(lat, lon, round(frac, 6), wt / total) for lat, lon, frac, wt in raw]
