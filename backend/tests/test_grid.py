import math

import pytest

from earthsignal.config import LUCKNOW, LUCKNOW_AIRPORT
from earthsignal.data import grid


def test_merra2_cells_match_verified_edges():
    # Edges verified with live POWER requests on 2026-11-15 (DECISIONS D-017)
    assert grid.merra2_cell(LUCKNOW.latitude, LUCKNOW.longitude) == grid.Box(26.75, 27.25, 80.9375, 81.5625)
    assert grid.merra2_cell(LUCKNOW_AIRPORT.latitude, LUCKNOW_AIRPORT.longitude) == grid.Box(26.75, 27.25, 80.3125, 80.9375)
    assert grid.merra2_cell(26.85, 80.937).east == 80.9375  # just west of the boundary
    assert grid.merra2_cell(26.85, 80.938).west == 80.9375  # just east of the boundary


def test_imerg_subcells_cover_box_exactly():
    box = grid.Box(26.75, 27.25, 80.9375, 81.5625)
    cells = grid.imerg_cells_in(box)
    lats = sorted({c.lat for c in cells})
    lons = sorted({c.lon for c in cells})
    assert lats == [26.75, 26.85, 26.95, 27.05, 27.15, 27.25]
    assert lons == [80.95, 81.05, 81.15, 81.25, 81.35, 81.45, 81.55]
    assert len(cells) == 42
    # covered area in IMERG-cell units equals the box area (0.5 x 0.625 deg = 31.25 cells)
    assert sum(c.overlap_fraction for c in cells) == pytest.approx(0.5 * 0.625 / 0.01)
    assert sum(c.weight for c in cells) == pytest.approx(1.0)
    by = {(c.lat, c.lon): c for c in cells}
    assert by[(26.75, 80.95)].overlap_fraction == pytest.approx(0.5 * 0.625)  # half row, 0.625 column
    assert by[(26.85, 81.05)].overlap_fraction == pytest.approx(1.0)


def test_cosine_weighting():
    cells = grid.imerg_cells_in(grid.Box(26.75, 27.25, 80.9375, 81.5625))
    full = [c for c in cells if c.overlap_fraction == pytest.approx(1.0)]
    north = max(full, key=lambda c: c.lat)
    south = min(full, key=lambda c: c.lat)
    assert north.weight / south.weight == pytest.approx(math.cos(math.radians(north.lat)) / math.cos(math.radians(south.lat)))


def test_aligned_box_has_no_partial_cells():
    cells = grid.imerg_cells_in(grid.Box(10.0, 10.3, 20.0, 20.2))
    assert len(cells) == 6 and all(c.overlap_fraction == pytest.approx(1.0) for c in cells)
