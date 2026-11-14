"""GPM IMERG precipitation via NASA POWER, aggregated to the MERRA-2 cell for comparison.

What this module acquires (no login needed):
  * IMERG_PRECTOT for EVERY 0.1 deg IMERG cell that overlaps the study area's MERRA-2 cell
    (42 cells for each Lucknow cell), one POWER point request per cell, in UTC (IMERG is UTC-only).
  * PRECTOTCORR (MERRA-2) for the same MERRA-2 cell, ALSO in UTC, so both series share day boundaries.

The IMERG area mean is the overlap- and cos(lat)-weighted mean of the cells (grid.imerg_cells_in).
A day's area mean is computed only if EVERY cell is valid that day; otherwise it is missing.

Provenance caveats (docs/research/GPM_IMERG_RESEARCH.md):
  * POWER does not state the IMERG version. V07 is inferred because V07 supersedes all earlier versions.
  * POWER mixes the Final and Late runs. The CMR record of the Final run (GPM_3IMERGDF V07) ends
    2025-09-30, so later POWER values are flagged and excluded from comparisons.

Usage:
    python -m earthsignal.data.imerg_power --area lucknow --start 2024-07-01 --end 2024-07-31   # sample
    python -m earthsignal.data.imerg_power --area lucknow                                       # full record
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Callable

import numpy as np
import pandas as pd

from earthsignal.config import DEFAULT_AREA, PROCESSED_DIR, RAW_DIR, STUDY_AREAS, StudyArea
from earthsignal.data import grid, power
from earthsignal.data.ingest import _http_get, _repo_relative
from earthsignal.metadata import DatasetMetadata, VariableInfo

SUBDIR = "imerg"
IMERG_START = date(1998, 1, 1)  # first valid POWER IMERG day observed 2026-11-15
FINAL_RUN_END = date(2025, 9, 30)  # CMR temporal extent of GPM_3IMERGDF V07, checked 2026-11-15
IMERG_DOI = "10.5067/GPM/IMERGDF/DAY/07"
IMERG_CITATION = (
    "Huffman, G.J., E.F. Stocker, D.T. Bolvin, E.J. Nelkin, J. Tan (2023), GPM IMERG Final Precipitation L3 "
    "1 day 0.1 degree x 0.1 degree V07, Greenbelt, MD, Goddard Earth Sciences Data and Information Services "
    f"Center (GES DISC), doi:{IMERG_DOI}. Accessed via the NASA LaRC POWER Project (IMERG_PRECTOT)."
)
REQUEST_PAUSE_S = 0.3  # courtesy pause between POWER requests


def _cell_name(lat: float, lon: float) -> str:
    return f"cell_{lat:.2f}_{lon:.2f}.json"


def download(
    area: StudyArea,
    start: date,
    end: date,
    raw_root: Path = RAW_DIR,
    http_get: Callable[[str], bytes] = _http_get,
    pause_s: float = REQUEST_PAUSE_S,
) -> Path:
    if start < IMERG_START:
        raise ValueError(f"IMERG via POWER starts {IMERG_START}")
    retrieved_at = power.utc_now()
    box = grid.merra2_cell(area.latitude, area.longitude)
    cells = grid.imerg_cells_in(box)
    dataset_id = f"imergpower_{area.key}_{start:%Y%m%d}_{end:%Y%m%d}_{retrieved_at:%Y%m%dT%H%M%SZ}"
    raw_dir = raw_root / SUBDIR / dataset_id

    # Fetch everything first and check it parses, then write. A failed run leaves no partial folder.
    payloads: dict[str, bytes] = {}
    cell_records = []
    for c in cells:
        url = power.build_daily_point_url(c.lat, c.lon, start, end, parameters=("IMERG_PRECTOT",), time_standard="UTC")
        payload = http_get(url)
        json.loads(payload)
        name = _cell_name(c.lat, c.lon)
        payloads[name] = payload
        cell_records.append({"file": name, "lat": c.lat, "lon": c.lon, "overlap_fraction": c.overlap_fraction,
                             "weight": c.weight, "url": url})
        if pause_s:
            time.sleep(pause_s)
    merra_url = power.build_daily_point_url(area.latitude, area.longitude, start, end,
                                            parameters=("PRECTOTCORR",), time_standard="UTC")
    payloads["merra2_prectotcorr_utc.json"] = http_get(merra_url)
    meta_url = power.build_parameter_metadata_url(("IMERG_PRECTOT", "PRECTOTCORR"))
    payloads["parameter_metadata.json"] = http_get(meta_url)
    for name in ("merra2_prectotcorr_utc.json", "parameter_metadata.json"):
        json.loads(payloads[name])

    for name, payload in payloads.items():
        power.write_immutable(raw_dir / name, payload)
    request = {
        "dataset_id": dataset_id,
        "study_area": area.__dict__,
        "merra2_cell": box.as_dict(),
        "requested_start": start.isoformat(),
        "requested_end": end.isoformat(),
        "time_standard": "UTC",
        "imerg_cells": cell_records,
        "merra2_request_url": merra_url,
        "parameter_metadata_url": meta_url,
        "retrieved_at_utc": retrieved_at.isoformat(),
    }
    power.write_immutable(raw_dir / "request.json", json.dumps(request, indent=2).encode())
    return raw_dir


def area_mean(cells: pd.DataFrame, weights: pd.Series) -> tuple[pd.Series, pd.Series]:
    """Weighted mean across columns; NaN unless every cell is valid that day. Returns (mean, n_valid)."""
    w = weights.reindex(cells.columns).to_numpy()
    if not np.isclose(w.sum(), 1.0):
        raise ValueError("cell weights must sum to 1")
    n_valid = cells.notna().sum(axis=1)
    mean = (cells.fillna(0.0) * w).sum(axis=1)  # fillna only affects rows that are then masked below
    return mean.where(n_valid == cells.shape[1]), n_valid


def process(raw_dir: Path, processed_root: Path = PROCESSED_DIR) -> dict[str, Any]:
    request = json.loads((raw_dir / "request.json").read_text())
    start, end = date.fromisoformat(request["requested_start"]), date.fromisoformat(request["requested_end"])
    meta = json.loads((raw_dir / "parameter_metadata.json").read_bytes())
    if meta.get("IMERG_PRECTOT", {}).get("units") != "mm/day" or meta.get("PRECTOTCORR", {}).get("units") != "mm/day":
        raise power.PowerResponseError("parameter metadata units are not mm/day as expected")

    series, weights, files, sources = {}, {}, [], set()
    area = request["study_area"]
    point_cell = None
    for rec in request["imerg_cells"]:
        payload = (raw_dir / rec["file"]).read_bytes()
        parsed = power.parse_daily_point(json.loads(payload), ("IMERG_PRECTOT",))
        if parsed.time_standard != "UTC":
            raise power.PowerResponseError(f"{rec['file']}: time standard {parsed.time_standard}, expected UTC")
        rep = power.validate_frame(parsed.frame, start, end)
        if not rep["passed"]:
            raise power.PowerResponseError(f"{rec['file']}: {rep['errors']}")
        key = f"{rec['lat']:.2f}_{rec['lon']:.2f}"
        series[key] = parsed.frame["IMERG_PRECTOT"]
        weights[key] = rec["weight"]
        sources.update(parsed.sources)
        files.append({"file": rec["file"], "sha256": power.sha256_bytes(payload)})
        if (rec["lat"] - 0.05 <= area["latitude"] < rec["lat"] + 0.05) and (rec["lon"] - 0.05 <= area["longitude"] < rec["lon"] + 0.05):
            point_cell = key
    cells = pd.DataFrame(series)
    mean, n_valid = area_mean(cells, pd.Series(weights))

    mpayload = (raw_dir / "merra2_prectotcorr_utc.json").read_bytes()
    mparsed = power.parse_daily_point(json.loads(mpayload), ("PRECTOTCORR",))
    if mparsed.time_standard != "UTC":
        raise power.PowerResponseError("MERRA-2 request is not UTC")
    files.append({"file": "merra2_prectotcorr_utc.json", "sha256": power.sha256_bytes(mpayload)})

    out = pd.DataFrame(
        {
            "imerg_area_mean_mm_day": mean,
            "imerg_point_cell_mm_day": cells[point_cell] if point_cell else np.nan,
            "imerg_cells_valid": n_valid,
            "merra2_prectotcorr_utc_mm_day": mparsed.frame["PRECTOTCORR"],
        }
    )
    out.index.name = "date"
    out["after_final_run_end"] = out.index > pd.Timestamp(FINAL_RUN_END)

    out_dir = processed_root / SUBDIR / request["dataset_id"]
    out_dir.mkdir(parents=True, exist_ok=True)
    out.to_csv(out_dir / "daily.csv", float_format="%.4f", date_format="%Y-%m-%d")
    cells.to_csv(out_dir / "cells_daily.csv", float_format="%.4f", date_format="%Y-%m-%d")

    valid = out["imerg_area_mean_mm_day"].dropna()
    box = request["merra2_cell"]
    metadata = DatasetMetadata(
        dataset_id=request["dataset_id"],
        source_type="nasa_power_imerg",
        provider="NASA GPM IMERG (Huffman et al.), multi-satellite precipitation with monthly gauge calibration (Final run)",
        distributor="NASA LaRC POWER Project (parameter IMERG_PRECTOT), from NASA GES DISC / PPS IMERG",
        product_id="GPM_3IMERGDF (IMERG Final daily), via POWER IMERG_PRECTOT; Late run after 2025-09-30",
        product_version="V07 (inferred; POWER does not state the version)",
        variables=[
            VariableInfo(name="imerg_area_mean_mm_day", units="mm/day",
                         definition=f"Weighted mean of {len(cells.columns)} IMERG 0.1 deg cells over the MERRA-2 cell", data_kind="derived_estimate"),
            VariableInfo(name="imerg_point_cell_mm_day", units="mm/day",
                         definition="IMERG 0.1 deg cell containing the study-area point", data_kind="derived_estimate"),
            VariableInfo(name="merra2_prectotcorr_utc_mm_day", units="mm/day",
                         definition="MERRA-2 bias-corrected precipitation for the same MERRA-2 cell, UTC days", data_kind="derived_estimate"),
        ],
        spatial_resolution="IMERG 0.1 x 0.1 deg; aggregated to the 0.5 x 0.625 deg MERRA-2 cell",
        spatial_support=f"area mean over MERRA-2 cell {box['south']}-{box['north']} N, {box['west']}-{box['east']} E",
        geographic_coverage={"merra2_cell": box, "n_imerg_cells": len(cells.columns)},
        temporal_resolution="daily",
        time_standard="UTC",
        time_coverage={
            "start": None if valid.empty else valid.index.min().date().isoformat(),
            "end": None if valid.empty else valid.index.max().date().isoformat(),
            "final_run_end": FINAL_RUN_END.isoformat(),
        },
        retrieved_at_utc=request["retrieved_at_utc"],
        processing_history=[
            f"download {len(cells.columns)} IMERG cell series and 1 MERRA-2 series from POWER (UTC); bytes stored unmodified",
            "fill value from each response header -> NaN; API messages cause rejection",
            "area mean = overlap x cos(lat) weighted mean; a day is missing unless every cell is valid",
            f"days after {FINAL_RUN_END} flagged (not IMERG Final run)",
        ],
        citation=IMERG_CITATION,
        quality_limitations=[
            "IMERG Final uses MERRA-2 winds for morphing and GPCC gauges for monthly calibration, so it is not independent of MERRA-2.",
            "Changes in the satellite constellation (notably TRMM to GPM, May/June 2014, and sensors before 2005) may introduce artifacts in multi-year changes.",
            "Lower skill expected over complex terrain, coasts and frozen surfaces (CMR abstract).",
            "POWER's IMERG count field counts precipitating half-hours only, so completeness cannot be checked from it.",
            "Equality of POWER IMERG values with native GPM_3IMERGDF files has not been verified (needs Earthdata Login).",
        ],
        access="Public NASA POWER API; no login required. Native IMERG at GES DISC requires Earthdata Login.",
    )
    provenance = {
        "dataset_id": request["dataset_id"],
        "source_type": "nasa_power_imerg",
        "retrieved_at_utc": request["retrieved_at_utc"],
        "study_area_key": area.get("key"),
        "request": {k: request[k] for k in ("requested_start", "requested_end", "time_standard", "merra2_cell", "merra2_request_url", "parameter_metadata_url")},
        "imerg_cells": request["imerg_cells"],
        "point_cell": point_cell,
        "sources_reported_by_api": sorted(sources),
        "raw_dir": _repo_relative(raw_dir).as_posix(),
        "raw_files": files,
        "coverage": {
            "days": int(len(out)),
            "area_mean_valid_days": int(valid.size),
            "merra2_valid_days": int(out["merra2_prectotcorr_utc_mm_day"].notna().sum()),
            "days_after_final_run_end": int(out["after_final_run_end"].sum()),
        },
        "metadata": metadata.model_dump(),
    }
    (out_dir / "provenance.json").write_text(json.dumps(provenance, indent=2))
    return provenance


def latest(processed_root: Path = PROCESSED_DIR, area: str = DEFAULT_AREA) -> tuple[pd.DataFrame, dict] | None:
    base = processed_root / SUBDIR
    if not base.exists():
        return None
    provs = [json.loads(p.read_text()) for p in base.glob(f"imergpower_{area}_*/provenance.json")]
    provs = [p for p in provs if p.get("study_area_key") == area]
    if not provs:
        return None
    prov = max(provs, key=lambda p: (p["request"]["requested_end"] >= "2025-01-01", p["retrieved_at_utc"]))
    frame = pd.read_csv(base / prov["dataset_id"] / "daily.csv", index_col="date", parse_dates=["date"])
    return frame, prov


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--area", choices=sorted(STUDY_AREAS), default=DEFAULT_AREA)
    ap.add_argument("--start", type=date.fromisoformat, default=IMERG_START)
    ap.add_argument("--end", type=date.fromisoformat, default=None, help="default: yesterday (UTC)")
    ap.add_argument("--from-raw", type=Path, default=None)
    args = ap.parse_args(argv)
    if args.from_raw:
        raw_dir = args.from_raw
    else:
        end = args.end or (power.utc_now().date() - timedelta(days=1))
        area = STUDY_AREAS[args.area]
        n = len(grid.imerg_cells_in(grid.merra2_cell(area.latitude, area.longitude)))
        print(f"Requesting {n} IMERG cells + 1 MERRA-2 series ({args.start}..{end}, UTC) for {area.label}")
        raw_dir = download(area, args.start, end)
    prov = process(raw_dir)
    c = prov["coverage"]
    print(f"dataset_id: {prov['dataset_id']}")
    print(f"sources reported: {prov['sources_reported_by_api']}; point cell: {prov['point_cell']}")
    print(f"days {c['days']}; area-mean valid {c['area_mean_valid_days']}; MERRA-2 valid {c['merra2_valid_days']}; "
          f"after Final-run end {c['days_after_final_run_end']}")
    print(f"coverage: {prov['metadata']['time_coverage']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
