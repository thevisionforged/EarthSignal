"""IMD 0.25 deg daily gridded rainfall (gauge-based reference; Milestone 4, DECISIONS D-021).

Source facts (IMD Pune pages, read 2026-11-15):
  https://www.imdpune.gov.in/cmpg/Griddata/Rainfall_25_Bin.html
  * "IMD New High Spatial Resolution (0.25X0.25 degree) Long Period (1901-2024) Daily Gridded Rainfall
    Data Set Over India." "The unit of rainfall is in millimeter (mm)."
  * "Data is arranged in 135x129 grid points. The first data in the record is at 6.5N & 66.5E, the second
    is at 6.5N & 66.75E, and so on. The last data record corresponds to 38.5N & 100.0E. The yearly data file
    consists of 365/366 records corresponding to non leap/ leap years."
  * GrADS control: "UNDEF -999.0", "XDEF 135 LINEAR 66.5 0.25", "YDEF 129 LINEAR 6.5 0.25".
  * Download: HTML form POST to rainfall.php with field rain=<year>; the response is ind<year>_rfp25.grd.
  * Citation requested: Pai et al. (2014), MAUSAM 65(1), 1-18.
Grid VALUES are at points (cell centres) 66.5 + 0.25*i E, 6.5 + 0.25*j N. Each represents a 0.25 deg box.

Binary layout: little-endian float32 (verified: values parse to plausible rainfall only in that byte order),
records = days, each record = 129 rows (S->N) x 135 columns (W->E).
"""

from __future__ import annotations

import json
import sys
from datetime import date
from pathlib import Path
from typing import Any, Callable

import httpx
import numpy as np
import pandas as pd

from earthsignal.config import RAW_DIR
from earthsignal.data import grid, power

DOWNLOAD_URL = "https://www.imdpune.gov.in/cmpg/Griddata/rainfall.php"
INFO_URL = "https://www.imdpune.gov.in/cmpg/Griddata/Rainfall_25_Bin.html"
NX, NY = 135, 129
LON0, LAT0, D = 66.5, 6.5, 0.25
UNDEF = -999.0
SUBDIR = "imd"
CITATION = (
    "Pai D.S., Latha Sridhar, Rajeevan M., Sreejith O.P., Satbhai N.S. and Mukhopadhyay B., 2014: Development of a "
    "new high spatial resolution (0.25 x 0.25) long period (1901-2010) daily gridded rainfall data set over India and "
    "its comparison with existing data sets over the region; MAUSAM, 65, 1 (January 2014), pp 1-18. Data: India "
    "Meteorological Department, Pune."
)


def lons() -> np.ndarray:
    return LON0 + D * np.arange(NX)


def lats() -> np.ndarray:
    return LAT0 + D * np.arange(NY)


def _post_year(year: int, timeout: float = 1800.0) -> tuple[bytes, dict]:
    with httpx.Client(timeout=timeout, follow_redirects=True) as client:
        resp = client.post(DOWNLOAD_URL, data={"rain": str(year)})
        resp.raise_for_status()
        return resp.content, {k.lower(): v for k, v in resp.headers.items() if k.lower() in ("content-type", "content-disposition")}


def download_year(year: int, raw_root: Path = RAW_DIR, post: Callable = _post_year) -> Path:
    retrieved_at = power.utc_now()
    payload, headers = post(year)
    n_days = 366 if pd.Timestamp(year=year, month=12, day=31).is_leap_year else 365
    expected = n_days * NX * NY * 4
    if len(payload) != expected:
        raise ValueError(f"IMD {year}: {len(payload)} bytes, expected {expected} ({n_days} days x {NX}x{NY} float32)")
    raw_dir = raw_root / SUBDIR / f"imd_rf025_{year}_{retrieved_at:%Y%m%dT%H%M%SZ}"
    name = f"ind{year}_rfp25.grd"
    power.write_immutable(raw_dir / name, payload)
    request = {
        "source": "IMD Pune 0.25 deg daily gridded rainfall (binary)",
        "info_url": INFO_URL,
        "download_url": DOWNLOAD_URL,
        "method": "POST",
        "form": {"rain": str(year)},
        "response_headers": headers,
        "retrieved_at_utc": retrieved_at.isoformat(),
        "file": name,
        "bytes": len(payload),
        "sha256": power.sha256_bytes(payload),
        "year": year,
    }
    power.write_immutable(raw_dir / "request.json", json.dumps(request, indent=2).encode())
    return raw_dir


def read_grid(payload: bytes, year: int) -> np.ndarray:
    """Return array (days, lat, lon) in mm/day with NaN for UNDEF."""
    arr = np.frombuffer(payload, dtype="<f4").reshape(-1, NY, NX).astype("float64")
    n_days = 366 if pd.Timestamp(year=year, month=12, day=31).is_leap_year else 365
    if arr.shape[0] != n_days:
        raise ValueError(f"{arr.shape[0]} daily records, expected {n_days}")
    arr[np.isclose(arr, UNDEF)] = np.nan
    return arr


def box_points(south: float, north: float, west: float, east: float) -> list[tuple[int, int, float, float, float]]:
    """IMD 0.25 deg boxes overlapping the region: (j, i, lat, lon, overlap fraction of the IMD box)."""
    out = []
    for j, la in enumerate(lats()):
        fy = (min(la + D / 2, north) - max(la - D / 2, south)) / D
        if fy <= 0:
            continue
        for i, lo in enumerate(lons()):
            fx = (min(lo + D / 2, east) - max(lo - D / 2, west)) / D
            if fx > 0:
                out.append((j, i, float(la), float(lo), float(fx * fy)))
    return out


def area_mean_series(arr: np.ndarray, year: int, points: list[tuple[int, int, float, float, float]]) -> tuple[pd.Series, pd.Series]:
    """Overlap x cos(lat) weighted mean over `points`; a day is NaN unless every point is valid."""
    w = np.array([f * np.cos(np.radians(la)) for _, _, la, _, f in points])
    w = w / w.sum()
    vals = np.stack([arr[:, j, i] for j, i, *_ in points], axis=1)
    n_valid = np.isfinite(vals).sum(axis=1)
    mean = np.where(n_valid == len(points), np.nansum(vals * w, axis=1), np.nan)
    idx = pd.date_range(f"{year}-01-01", periods=arr.shape[0], freq="D")
    return pd.Series(mean, index=idx), pd.Series(n_valid, index=idx)


def latest_raw_years(raw_root: Path = RAW_DIR) -> dict[int, Path]:
    """Most recent raw folder per year."""
    out: dict[int, Path] = {}
    for d in sorted((raw_root / SUBDIR).glob("imd_rf025_*")):
        req = json.loads((d / "request.json").read_text())
        out[int(req["year"])] = d  # sorted by name, so later retrievals win
    return out


def process(raw_root: Path = RAW_DIR, processed_root: Path | None = None) -> dict:
    """Area means of IMD rainfall over each study area's MERRA-2 cell, all available years."""
    from earthsignal.config import PROCESSED_DIR, STUDY_AREAS
    from earthsignal.data.ingest import _repo_relative
    from earthsignal.metadata import DatasetMetadata, VariableInfo

    processed_root = processed_root or PROCESSED_DIR
    years = latest_raw_years(raw_root)
    if not years:
        raise FileNotFoundError("no IMD raw files; run: python -m earthsignal.data.imd <years>")
    boxes = {k: grid.merra2_cell(a.latitude, a.longitude) for k, a in STUDY_AREAS.items()}
    weights = {k: grid.overlap_weights(lats(), lons(), D, D, b) for k, b in boxes.items()}
    cols: dict[str, list[pd.Series]] = {k: [] for k in boxes}
    files = []
    for y, d in sorted(years.items()):
        req = json.loads((d / "request.json").read_text())
        payload = (d / req["file"]).read_bytes()
        if power.sha256_bytes(payload) != req["sha256"]:
            raise ValueError(f"IMD {y}: checksum mismatch")
        arr = read_grid(payload, y)
        idx = pd.date_range(f"{y}-01-01", periods=arr.shape[0], freq="D")
        for k, w in weights.items():
            vals = np.stack([arr[:, j, i] for j, i, *_ in w], axis=1)
            wt = np.array([x[5] for x in w])
            ok = np.isfinite(vals).all(axis=1)
            cols[k].append(pd.Series(np.where(ok, np.nansum(vals * wt, axis=1), np.nan), index=idx))
        files.append({"year": y, "raw": _repo_relative(d / req["file"]).as_posix(), "sha256": req["sha256"]})
    frame = pd.DataFrame({f"imd_{k}_mm_day": pd.concat(v) for k, v in cols.items()})
    frame.index.name = "date"
    first, last = min(years), max(years)
    dataset_id = f"imd_rf025_lucknow_{first}_{last}"
    out_dir = processed_root / SUBDIR / dataset_id
    out_dir.mkdir(parents=True, exist_ok=True)
    frame.to_csv(out_dir / "daily.csv", float_format="%.3f", date_format="%Y-%m-%d")
    md = DatasetMetadata(
        dataset_id=dataset_id,
        source_type="imd_gridded",
        provider="India Meteorological Department (IMD), Pune: rain-gauge analysis (6,955 stations, varying network)",
        distributor="IMD Pune, Climate Research and Services (rainfall.php, binary)",
        product_id="IMD 0.25 x 0.25 deg daily gridded rainfall (Pai et al. 2014)",
        product_version="operational archive (1901-2024 per IMD page); no version number stated",
        variables=[VariableInfo(name=c, units="mm/day", definition=f"IMD rainfall area mean over the {c.split('_')[1] if 'airport' not in c else 'lucknow_airport'} MERRA-2 cell",
                                data_kind="derived_estimate") for c in frame.columns],
        spatial_resolution="0.25 x 0.25 deg (Shepard inverse-distance interpolation of gauges)",
        spatial_support="area mean over each MERRA-2 cell (overlap x cos(lat) weights)",
        geographic_coverage={k: b.as_dict() for k, b in boxes.items()},
        temporal_resolution="daily",
        time_standard=("IMD rainfall day. The gauge observation time / day boundary is not stated in the IMD pages or "
                       "Pai et al. (2014) as read, so EarthSignal compares IMD only at monthly and annual scales"),
        time_coverage={"start": f"{first}-01-01", "end": f"{last}-12-31"},
        retrieved_at_utc=max(json.loads((d / "request.json").read_text())["retrieved_at_utc"] for d in years.values()),
        processing_history=[
            "POST rainfall.php per year; binary bytes stored unmodified; byte count checked against 135x129xdays float32",
            "decode little-endian float32 (days, lat S->N, lon W->E); -999 -> NaN",
            "area mean over each MERRA-2 cell; a day is missing unless every overlapping IMD box is valid",
        ],
        citation=CITATION,
        quality_limitations=[
            "Gridded from rain gauges by inverse-distance interpolation (Shepard 1968): a gauge-based estimate, not a direct observation at a point.",
            "The station network varies over time: Pai et al. (2014) report >=3100 stations per day from 1951, falling to about 1900 in the last 2-3 years of 1901-2010. Counts after 2010 are not documented in the sources read.",
            "Not fully independent of IMERG and CPCU: Indian gauge reports may also enter GPCC (IMERG calibration) and CPC analyses.",
            "No explicit licence found on the IMD download pages; IMD requests citation of Pai et al. (2014) and disclaims liability.",
        ],
        access="Public download form on imdpune.gov.in; no login observed.",
        usage_notice="Cite Pai et al. (2014). No redistribution terms were found; raw IMD files are not committed to the repository.",
    )
    prov = {"dataset_id": dataset_id, "source_type": "imd_gridded", "retrieved_at_utc": md.retrieved_at_utc,
            "files": files, "cells": {k: [(la, lo, round(f, 4), round(wt, 5)) for _, _, la, lo, f, wt in w] for k, w in weights.items()},
            "metadata": md.model_dump()}
    (out_dir / "provenance.json").write_text(json.dumps(prov, indent=2))
    return prov


def latest(processed_root: Path | None = None) -> tuple[pd.DataFrame, dict] | None:
    from earthsignal.config import PROCESSED_DIR

    base = (processed_root or PROCESSED_DIR) / SUBDIR
    provs = sorted(base.glob("imd_rf025_lucknow_*/provenance.json")) if base.exists() else []
    if not provs:
        return None
    prov = json.loads(provs[-1].read_text())
    frame = pd.read_csv(provs[-1].parent / "daily.csv", index_col="date", parse_dates=["date"])
    return frame, prov


def main(argv: list[str] | None = None) -> int:
    import argparse

    ap = argparse.ArgumentParser(description="Download IMD 0.25 deg daily gridded rainfall years (binary).")
    ap.add_argument("years", nargs="*", type=int)
    ap.add_argument("--process", action="store_true", help="build the Lucknow area-mean dataset from stored raw files")
    args = ap.parse_args(argv)
    if args.process:
        prov = process()
        print(f"processed {prov['dataset_id']}: {len(prov['files'])} years")
        return 0
    for y in args.years:
        d = download_year(y)
        req = json.loads((d / "request.json").read_text())
        print(f"{y}: {req['bytes']} bytes sha256 {req['sha256'][:16]}... -> {d}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
