"""Reproducible NASA POWER ingestion for the Lucknow study area.

Usage (from repo root, venv active):
    python -m earthsignal.data.ingest                       # 1981-01-01 .. yesterday (UTC)
    python -m earthsignal.data.ingest --start 2000-01-01 --end 2020-12-31
    python -m earthsignal.data.ingest --from-raw data/raw/<dataset_id>   # reprocess, no network
    python -m earthsignal.data.ingest --area lucknow_airport             # western (airport) grid cell

Each run creates a new dataset_id. Raw responses are written once and never overwritten.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

import httpx

from earthsignal.config import DEFAULT_AREA, PROCESSED_DIR, RAW_DIR, REPO_ROOT, STUDY_AREAS, StudyArea
from earthsignal.data import power

RAW_RESPONSE_NAME = "daily_point_response.json"
RAW_METADATA_NAME = "parameter_metadata_response.json"
RAW_REQUEST_NAME = "request.json"


def _repo_relative(path: Path) -> Path:
    try:
        return path.resolve().relative_to(REPO_ROOT)
    except ValueError:
        return path


def _http_get(url: str, timeout: float = 180.0) -> bytes:
    with httpx.Client(timeout=timeout, follow_redirects=True) as client:
        resp = client.get(url)
        resp.raise_for_status()
        return resp.content


def download(
    area: StudyArea, start: date, end: date, raw_root: Path = RAW_DIR, http_get=_http_get
) -> Path:
    """Download the daily point response and parameter metadata into a new immutable raw folder."""
    retrieved_at = power.utc_now()
    dataset_id = (
        f"power_daily_{area.key}_{start:%Y%m%d}_{end:%Y%m%d}_{retrieved_at:%Y%m%dT%H%M%SZ}"
    )
    raw_dir = raw_root / dataset_id
    data_url = power.build_daily_point_url(area.latitude, area.longitude, start, end)
    meta_url = power.build_parameter_metadata_url()

    data_bytes = http_get(data_url)
    meta_bytes = http_get(meta_url)
    json.loads(data_bytes)  # fail early on non-JSON before writing anything
    json.loads(meta_bytes)

    power.write_immutable(raw_dir / RAW_RESPONSE_NAME, data_bytes)
    power.write_immutable(raw_dir / RAW_METADATA_NAME, meta_bytes)
    request_record = {
        "dataset_id": dataset_id,
        "study_area": area.__dict__,
        "requested_start": start.isoformat(),
        "requested_end": end.isoformat(),
        "parameters": list(power.DEFAULT_PARAMETERS),
        "community": power.DEFAULT_COMMUNITY,
        "time_standard": power.DEFAULT_TIME_STANDARD,
        "request_url": data_url,
        "parameter_metadata_url": meta_url,
        "retrieved_at_utc": retrieved_at.isoformat(),
    }
    power.write_immutable(raw_dir / RAW_REQUEST_NAME, json.dumps(request_record, indent=2).encode())
    return raw_dir


def process(raw_dir: Path, processed_root: Path = PROCESSED_DIR) -> dict[str, Any]:
    """Parse + validate a raw folder; write processed CSV and provenance. Raw files are only read."""
    request = power.load_json(raw_dir / RAW_REQUEST_NAME)
    raw_path = raw_dir / RAW_RESPONSE_NAME
    meta_path = raw_dir / RAW_METADATA_NAME
    raw_bytes = raw_path.read_bytes()
    meta_bytes = meta_path.read_bytes()

    params = tuple(request["parameters"])
    parsed = power.parse_daily_point(json.loads(raw_bytes), params)
    definitions = json.loads(meta_bytes)
    for p in params:
        meta_units = definitions.get(p, {}).get("units")
        if meta_units != parsed.units[p]:
            raise power.PowerResponseError(
                f"{p}: response units {parsed.units[p]!r} disagree with parameter metadata {meta_units!r}"
            )

    start = date.fromisoformat(request["requested_start"])
    end = date.fromisoformat(request["requested_end"])
    validation = power.validate_frame(parsed.frame, start, end)
    if not validation["passed"]:
        raise power.PowerResponseError(f"validation failed: {validation['errors']}")

    out_dir = processed_root / request["dataset_id"]
    out_dir.mkdir(parents=True, exist_ok=True)
    csv_path = out_dir / "daily.csv"
    # NaN written as empty cells: missing stays missing.
    parsed.frame.to_csv(csv_path, float_format="%.4f", date_format="%Y-%m-%d")

    provenance = power.build_provenance(
        dataset_id=request["dataset_id"],
        request_url=request["request_url"],
        metadata_url=request["parameter_metadata_url"],
        retrieved_at=datetime.fromisoformat(request["retrieved_at_utc"]),
        raw_path=_repo_relative(raw_path),
        raw_sha256=power.sha256_bytes(raw_bytes),
        metadata_path=_repo_relative(meta_path),
        metadata_sha256=power.sha256_bytes(meta_bytes),
        requested={
            "latitude": request["study_area"]["latitude"],
            "longitude": request["study_area"]["longitude"],
            "study_area": request["study_area"]["name"],
            "start": request["requested_start"],
            "end": request["requested_end"],
            "parameters": list(params),
            "community": request["community"],
            "time_standard": request["time_standard"],
        },
        parsed=parsed,
        parameter_definitions=definitions,
        validation=validation,
        processed_path=_repo_relative(csv_path),
    )
    (out_dir / "provenance.json").write_text(json.dumps(provenance, indent=2, default=str))
    return provenance


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--start", type=date.fromisoformat, default=date(1981, 1, 1))
    ap.add_argument("--end", type=date.fromisoformat, default=None, help="default: yesterday (UTC)")
    ap.add_argument("--from-raw", type=Path, default=None, help="reprocess an existing raw folder offline")
    ap.add_argument("--area", choices=sorted(STUDY_AREAS), default=DEFAULT_AREA, help="study area (grid cell) to download")
    args = ap.parse_args(argv)

    if args.from_raw:
        raw_dir = args.from_raw
    else:
        end = args.end or (power.utc_now().date() - timedelta(days=1))
        area = STUDY_AREAS[args.area]
        print(f"Requesting NASA POWER daily data {args.start}..{end} for {area.name} ({area.key})")
        raw_dir = download(area, args.start, end)
        print(f"Raw response stored (immutable): {raw_dir}")

    prov = process(raw_dir)
    v = prov["validation"]
    print(f"dataset_id: {prov['dataset_id']}")
    print(f"API version: {prov['api_version']}; sources: {prov['data_sources_reported_by_api']}")
    for name, info in v["variables"].items():
        print(
            f"  {name}: {info['n_valid']}/{info['n_days']} valid, "
            f"{info['first_valid']}..{info['last_valid']}, range {info['min']}..{info['max']}"
        )
    for w in v["warnings"]:
        print(f"  WARNING: {w}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
