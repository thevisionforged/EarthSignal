"""NASA POWER daily point data: request building, immutable raw capture, provenance, parsing.

Source facts below were checked against official NASA POWER documentation and the live
API on 2026-11-14 (see docs/DECISIONS.md, D-004 to D-006):

* Daily meteorology comes from NASA GMAO MERRA-2 reanalysis (1981-01-01 to about a month
  behind real time), extended to near real time with GEOS-IT (about 2 days latency).
  Reanalysis means a weather model that assimilates observations. It is NOT a direct
  station or satellite measurement.
* Native grid: 0.5 deg latitude x 0.625 deg longitude.
* Daily API default time standard is Local Solar Time (LST).
* The missing-value marker is read from the response header (`header.fill_value`; -999.0
  in every response seen so far) and is never hard-coded as the only option.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlencode

import numpy as np
import pandas as pd

POWER_DAILY_POINT_URL = "https://power.larc.nasa.gov/api/temporal/daily/point"
POWER_PARAMETER_METADATA_URL = "https://power.larc.nasa.gov/api/system/manager/parameters"

DOCUMENTATION_URLS = {
    "methodology": "https://power.larc.nasa.gov/docs/methodology/",
    "meteorology_sources": "https://power.larc.nasa.gov/docs/methodology/data/sources_meteorology/",
    "processing": "https://power.larc.nasa.gov/docs/methodology/data/processing/",
    "daily_api": "https://power.larc.nasa.gov/docs/services/api/temporal/daily/",
    "referencing": "https://power.larc.nasa.gov/docs/referencing/",
}

CITATION = (
    "The data was obtained from the National Aeronautics and Space Administration (NASA) "
    "Langley Research Center (LaRC) Prediction of Worldwide Energy Resource (POWER) Project "
    "funded through the NASA Earth Science Division."
)

# The variables EarthSignal requests, with the units we expect. The units are checked against
# both the parameter-metadata endpoint and each response header. A mismatch fails ingestion.
EXPECTED_UNITS = {"T2M": "C", "PRECTOTCORR": "mm/day"}
DEFAULT_PARAMETERS = tuple(EXPECTED_UNITS)
DEFAULT_COMMUNITY = "AG"
DEFAULT_TIME_STANDARD = "LST"

# Loose physical-plausibility bounds, used only to FLAG values, never to drop or alter them.
PLAUSIBLE_RANGES = {"T2M": (-60.0, 60.0), "PRECTOTCORR": (0.0, 1000.0)}

# EarthSignal value categories (CLAUDE.md, scientific integrity rule 3).
DATA_KIND = "derived_estimate"
DATA_KIND_NOTE = (
    "NASA POWER meteorology is reanalysis output (MERRA-2 / GEOS-IT assimilation models), "
    "averaged over a ~0.5 x 0.625 degree grid cell. It is a model-based estimate constrained "
    "by observations, not a direct ground or satellite measurement."
)


class PowerResponseError(ValueError):
    """The POWER response is malformed or inconsistent with what we requested."""


def build_daily_point_url(
    latitude: float,
    longitude: float,
    start: date,
    end: date,
    parameters: tuple[str, ...] = DEFAULT_PARAMETERS,
    community: str = DEFAULT_COMMUNITY,
    time_standard: str = DEFAULT_TIME_STANDARD,
) -> str:
    if end < start:
        raise ValueError("end date precedes start date")
    if not -90 <= latitude <= 90 or not -180 <= longitude <= 180:
        raise ValueError("coordinates out of range")
    query = {
        "parameters": ",".join(parameters),
        "community": community,
        "longitude": f"{longitude:.4f}",
        "latitude": f"{latitude:.4f}",
        "start": start.strftime("%Y%m%d"),
        "end": end.strftime("%Y%m%d"),
        "format": "JSON",
        "time-standard": time_standard,
    }
    return f"{POWER_DAILY_POINT_URL}?{urlencode(query, safe=',')}"


def build_parameter_metadata_url(
    parameters: tuple[str, ...] = DEFAULT_PARAMETERS, community: str = DEFAULT_COMMUNITY
) -> str:
    query = {"community": community, "temporal": "daily", "parameters": ",".join(parameters)}
    return f"{POWER_PARAMETER_METADATA_URL}?{urlencode(query, safe=',')}"


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def write_immutable(path: Path, payload: bytes) -> None:
    """Write bytes to a new file. Refuses to overwrite: raw data is immutable."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "xb") as fh:  # 'x' raises FileExistsError if the file exists
        fh.write(payload)


# ---------------------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------------------


@dataclass
class ParsedPower:
    frame: pd.DataFrame  # DatetimeIndex (daily, LST), one float column per parameter, NaN = missing
    fill_value: float
    api_version: str
    sources: list[str]
    units: dict[str, str]
    longnames: dict[str, str]
    returned_coordinates: dict[str, float]
    time_standard: str
    messages: list[Any] = field(default_factory=list)


def parse_daily_point(doc: dict[str, Any], expected_parameters: tuple[str, ...]) -> ParsedPower:
    try:
        header = doc["header"]
        param_values = doc["properties"]["parameter"]
        param_meta = doc["parameters"]
        coords = doc["geometry"]["coordinates"]
    except (KeyError, TypeError) as exc:
        raise PowerResponseError(f"unexpected POWER response structure: missing {exc}") from exc

    if "fill_value" not in header:
        raise PowerResponseError("response header has no fill_value; refusing to guess missing-value marker")
    fill_value = float(header["fill_value"])

    missing = [p for p in expected_parameters if p not in param_values]
    if missing:
        raise PowerResponseError(f"parameters missing from response: {missing}")

    units = {p: param_meta[p]["units"] for p in expected_parameters}
    for p in expected_parameters:
        if p in EXPECTED_UNITS and units[p] != EXPECTED_UNITS[p]:
            raise PowerResponseError(f"{p}: units {units[p]!r} != expected {EXPECTED_UNITS[p]!r}")

    columns = {}
    for p in expected_parameters:
        series = pd.Series(param_values[p], dtype="float64")
        series.index = pd.to_datetime(series.index, format="%Y%m%d")
        # Replace ONLY the documented fill marker with NaN. Never zero-fill.
        series = series.mask(np.isclose(series, fill_value))
        columns[p] = series
    frame = pd.DataFrame(columns).sort_index()
    frame.index.name = "date"

    return ParsedPower(
        frame=frame,
        fill_value=fill_value,
        api_version=str(header.get("api", {}).get("version", "unknown")),
        sources=list(header.get("sources", [])),
        units=units,
        longnames={p: param_meta[p].get("longname", "") for p in expected_parameters},
        returned_coordinates={
            "longitude": float(coords[0]),
            "latitude": float(coords[1]),
            "elevation_m": float(coords[2]) if len(coords) > 2 else float("nan"),
        },
        time_standard=str(header.get("time_standard", "unknown")),
        messages=list(doc.get("messages", [])),
    )


# ---------------------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------------------


def validate_frame(frame: pd.DataFrame, requested_start: date, requested_end: date) -> dict[str, Any]:
    """Data-quality report. Flags problems; does not alter data."""
    report: dict[str, Any] = {"passed": True, "errors": [], "warnings": [], "variables": {}}

    idx = frame.index
    if idx.has_duplicates:
        report["errors"].append("duplicate dates present")
    if not idx.is_monotonic_increasing:
        report["errors"].append("dates not sorted")
    expected = pd.date_range(requested_start, requested_end, freq="D")
    missing_dates = expected.difference(idx)
    extra_dates = idx.difference(expected)
    if len(missing_dates):
        report["errors"].append(f"{len(missing_dates)} requested dates absent from response")
    if len(extra_dates):
        report["errors"].append(f"{len(extra_dates)} dates outside requested range")

    for col in frame.columns:
        s = frame[col]
        valid = s.dropna()
        lo, hi = PLAUSIBLE_RANGES.get(col, (-np.inf, np.inf))
        out_of_range = valid[(valid < lo) | (valid > hi)]
        # Trailing missing days are expected at near-real-time latency; interior gaps are not.
        last_valid = s.last_valid_index()
        trailing_missing = int(s.loc[s.index > last_valid].isna().sum()) if last_valid is not None else len(s)
        interior_missing = int(s.isna().sum()) - trailing_missing
        info = {
            "n_days": int(len(s)),
            "n_valid": int(valid.size),
            "n_missing": int(s.isna().sum()),
            "n_missing_interior": interior_missing,
            "n_missing_trailing": trailing_missing,
            "first_valid": None if s.first_valid_index() is None else s.first_valid_index().date().isoformat(),
            "last_valid": None if last_valid is None else last_valid.date().isoformat(),
            "min": None if valid.empty else float(valid.min()),
            "max": None if valid.empty else float(valid.max()),
            "n_out_of_plausible_range": int(out_of_range.size),
            "plausible_range": [lo, hi],
        }
        report["variables"][col] = info
        if out_of_range.size:
            report["warnings"].append(f"{col}: {out_of_range.size} values outside plausible range {lo}..{hi}")
        if interior_missing:
            report["warnings"].append(f"{col}: {interior_missing} interior missing days")
        if trailing_missing:
            report["warnings"].append(
                f"{col}: {trailing_missing} trailing missing days (expected near-real-time latency)"
            )

    report["passed"] = not report["errors"]
    return report


# ---------------------------------------------------------------------------------------
# Provenance
# ---------------------------------------------------------------------------------------


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def build_provenance(
    *,
    dataset_id: str,
    request_url: str,
    metadata_url: str,
    retrieved_at: datetime,
    raw_path: Path,
    raw_sha256: str,
    metadata_path: Path,
    metadata_sha256: str,
    requested: dict[str, Any],
    parsed: ParsedPower,
    parameter_definitions: dict[str, Any],
    validation: dict[str, Any],
    processed_path: Path | None,
) -> dict[str, Any]:
    return {
        "dataset_id": dataset_id,
        "provider": "NASA Langley Research Center - POWER Project",
        "product": "POWER Daily API, point request",
        "api_version": parsed.api_version,
        "data_sources_reported_by_api": parsed.sources,
        "data_kind": DATA_KIND,
        "data_kind_note": DATA_KIND_NOTE,
        "methodology_summary": (
            "Meteorological parameters derived from NASA GMAO MERRA-2 reanalysis "
            "(1981-01-01 to about one month behind real time) and GEOS-IT (near real time, ~2 day latency). "
            "Native resolution 0.5 deg lat x 0.625 deg lon. Daily values aggregated in Local Solar Time. "
            "NASA POWER recommends ending climate-trend analyses about 2 months behind near real time, "
            "because MERRA-2 values replace GEOS-IT values as they become available."
        ),
        "spatial_resolution": "0.5 deg latitude x 0.625 deg longitude (native MERRA-2 grid)",
        "temporal_resolution": "daily",
        "time_standard": parsed.time_standard,
        "request_url": request_url,
        "parameter_metadata_url": metadata_url,
        "retrieved_at_utc": retrieved_at.isoformat(),
        "requested": requested,
        "returned_coordinates": parsed.returned_coordinates,
        "fill_value": parsed.fill_value,
        "fill_value_handling": "values equal to header.fill_value replaced with NaN; no imputation; no zero-fill",
        "variables": {
            p: {
                "units": parsed.units[p],
                "longname": parsed.longnames[p],
                "definition": parameter_definitions.get(p, {}).get("definition"),
                "metadata_units": parameter_definitions.get(p, {}).get("units"),
            }
            for p in parsed.units
        },
        "api_messages": parsed.messages,
        "raw_files": [
            {"role": "daily_point_response", "path": raw_path.as_posix(), "sha256": raw_sha256},
            {"role": "parameter_metadata_response", "path": metadata_path.as_posix(), "sha256": metadata_sha256},
        ],
        "processing_history": [
            {"step": "download", "detail": "HTTP GET request_url; response bytes stored unmodified"},
            {"step": "parse", "detail": "JSON parsed; dates interpreted as YYYYMMDD in time_standard"},
            {"step": "missing_values", "detail": "header.fill_value -> NaN"},
            {"step": "validate", "detail": "continuity, duplicates, units, plausibility flags (no values altered)"},
            {"step": "write_processed", "detail": None if processed_path is None else processed_path.as_posix()},
        ],
        "validation": validation,
        "documentation": DOCUMENTATION_URLS,
        "citation": CITATION,
        "citation_data_reference": (
            f"Data obtained from the POWER Project's Daily API {parsed.api_version} "
            f"on {retrieved_at.date().isoformat()}."
        ),
    }


def load_json(path: Path) -> dict[str, Any]:
    with open(path, "rb") as fh:
        return json.loads(fh.read())
