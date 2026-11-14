"""NOAA NCEI Global Surface Summary of the Day (GSOD): station download, parsing, provenance.

Facts below are from the GSOD readme (https://www.ncei.noaa.gov/data/global-summary-of-the-day/doc/readme.txt,
read 2026-11-15; see docs/DECISIONS.md D-014):

* One CSV per station per year: /access/{YEAR}/{USAF}{WBAN}.csv, anonymous HTTPS.
* TEMP: daily mean in deg F, missing 9999.9. TEMP_ATTRIBUTES: number of observations in the mean.
  The daily summary needs at least 4 observations.
* MAX/MIN: deg F, missing 9999.9.
* PRCP: inches, missing 99.99. PRCP_ATTRIBUTES "I" = station reported no precipitation data for the
  day, so a 0.00 with "I" is NOT a confirmed dry day.
* Days are UTC (0000Z-2359Z), not local time.
* Non-US station data are subject to WMO Resolution 40 (see LICENCE_NOTICE).

These are STATION OBSERVATIONS (data_kind "observed"), unlike NASA POWER reanalysis.
"""

from __future__ import annotations

import io
import json
import sys
from datetime import date
from pathlib import Path
from typing import Any, Callable

import httpx
import numpy as np
import pandas as pd

from earthsignal.config import PROCESSED_DIR, RAW_DIR
from earthsignal.data import power

GSOD_ACCESS_URL = "https://www.ncei.noaa.gov/data/global-summary-of-the-day/access/{year}/{station}.csv"
GSOD_README_URL = "https://www.ncei.noaa.gov/data/global-summary-of-the-day/doc/readme.txt"
ISD_HISTORY_URL = "https://www.ncei.noaa.gov/pub/data/noaa/isd-history.csv"

LUCKNOW_AIRPORT_STATION = "42369099999"

LICENCE_NOTICE = (
    "NOAA NCEI GSOD data for non-U.S. stations are subject to WMO Resolution 40 (Cg-XII), which "
    "allows WMO member countries to restrict the use or re-export of their data for commercial purposes. "
    "These data are intended for free and unrestricted use in research, education and other "
    "non-commercial activities. Non-U.S. data and products derived from them must not be used for "
    "commercial purposes or re-export of commercial services. Source: GSOD readme."
)

TEMP_MISSING = 9999.9
PRCP_MISSING = 99.99
MIN_TEMP_OBS = 4  # GSOD's own minimum; stricter filters are applied in the comparison (D-015)

STORAGE_SUBDIR = "stations"


def f_to_c(f: pd.Series) -> pd.Series:
    return (f - 32.0) * 5.0 / 9.0


def _http_get_status(url: str, timeout: float = 120.0) -> tuple[int, bytes]:
    with httpx.Client(timeout=timeout, follow_redirects=True) as client:
        resp = client.get(url)
        return resp.status_code, resp.content


def download(
    station: str, years: range, raw_root: Path = RAW_DIR, http_get_status: Callable = _http_get_status
) -> Path:
    """Fetch one CSV per year into a new immutable raw folder. 404 years are recorded, not fatal."""
    retrieved_at = power.utc_now()
    dataset_id = f"gsod_{station}_{years.start}_{years.stop - 1}_{retrieved_at:%Y%m%dT%H%M%SZ}"
    raw_dir = raw_root / STORAGE_SUBDIR / dataset_id
    files = []
    for year in years:
        url = GSOD_ACCESS_URL.format(year=year, station=station)
        status, payload = http_get_status(url)
        entry: dict[str, Any] = {"year": year, "url": url, "http_status": status}
        if status == 200:
            name = f"{year}.csv"
            power.write_immutable(raw_dir / name, payload)
            entry.update(file=name, sha256=power.sha256_bytes(payload), bytes=len(payload))
        elif status != 404:
            raise RuntimeError(f"unexpected HTTP {status} for {url}")
        files.append(entry)
    request = {
        "dataset_id": dataset_id,
        "station": station,
        "years_requested": [years.start, years.stop - 1],
        "retrieved_at_utc": retrieved_at.isoformat(),
        "access_url_template": GSOD_ACCESS_URL,
        "files": files,
    }
    power.write_immutable(raw_dir / "request.json", json.dumps(request, indent=2).encode())
    return raw_dir


def parse_year(payload: bytes) -> pd.DataFrame:
    df = pd.read_csv(io.BytesIO(payload), dtype={"STATION": str}, skipinitialspace=True)
    df.columns = [c.strip() for c in df.columns]
    out = pd.DataFrame(index=pd.to_datetime(df["DATE"], format="%Y-%m-%d"))
    out.index.name = "date"

    temp_f = pd.to_numeric(df["TEMP"], errors="coerce").to_numpy()
    out["temp_obs"] = pd.to_numeric(df["TEMP_ATTRIBUTES"], errors="coerce").to_numpy()
    temp_f = np.where(np.isclose(temp_f, TEMP_MISSING), np.nan, temp_f)
    out["tmean_c"] = f_to_c(pd.Series(temp_f, index=out.index))
    for col, name in (("MAX", "tmax_c"), ("MIN", "tmin_c")):
        v = pd.to_numeric(df[col], errors="coerce").to_numpy()
        out[name] = f_to_c(pd.Series(np.where(np.isclose(v, TEMP_MISSING), np.nan, v), index=out.index))

    prcp_in = pd.to_numeric(df["PRCP"], errors="coerce").to_numpy()
    flag = df["PRCP_ATTRIBUTES"].astype(str).str.strip().to_numpy()
    out["prcp_flag"] = flag
    no_report = (flag == "I") | np.isclose(prcp_in, PRCP_MISSING)
    out["prcp_mm"] = np.where(no_report, np.nan, prcp_in * 25.4)

    for col, name in (("LATITUDE", "lat"), ("LONGITUDE", "lon"), ("ELEVATION", "elev_m")):
        out[name] = pd.to_numeric(df[col], errors="coerce").to_numpy()
    out["name"] = df["NAME"].astype(str).to_numpy()
    return out


def parse_raw_dir(raw_dir: Path) -> tuple[pd.DataFrame, dict[str, Any]]:
    request = json.loads((raw_dir / "request.json").read_text())
    frames = [parse_year((raw_dir / f["file"]).read_bytes()) for f in request["files"] if f.get("file")]
    frame = pd.concat(frames).sort_index()
    if frame.index.has_duplicates:
        raise ValueError("duplicate dates across GSOD yearly files")
    return frame, request


def station_metadata_history(frame: pd.DataFrame) -> list[dict[str, Any]]:
    """Distinct (name, lat, lon, elevation) combinations over time. Changes can mean a relocation."""
    key = frame[["name", "lat", "lon", "elev_m"]].round(4).astype(str).agg("|".join, axis=1)
    runs = []
    for k, grp in frame.groupby((key != key.shift()).cumsum()):
        first = grp.iloc[0]
        runs.append(
            {
                "from": grp.index.min().date().isoformat(),
                "to": grp.index.max().date().isoformat(),
                "name": first["name"],
                "lat": float(first["lat"]),
                "lon": float(first["lon"]),
                "elev_m": float(first["elev_m"]),
                "n_days": int(len(grp)),
            }
        )
    return runs


def process(raw_dir: Path, processed_root: Path = PROCESSED_DIR) -> dict[str, Any]:
    frame, request = parse_raw_dir(raw_dir)
    out_dir = processed_root / STORAGE_SUBDIR / request["dataset_id"]
    out_dir.mkdir(parents=True, exist_ok=True)
    cols = ["tmean_c", "temp_obs", "tmax_c", "tmin_c", "prcp_mm", "prcp_flag"]
    frame[cols].to_csv(out_dir / "daily.csv", float_format="%.3f", date_format="%Y-%m-%d")

    per_year = frame.groupby(frame.index.year).agg(
        days=("tmean_c", "size"),
        tmean_valid=("tmean_c", lambda s: int(s.notna().sum())),
        median_temp_obs=("temp_obs", "median"),
        prcp_reported=("prcp_mm", lambda s: int(s.notna().sum())),
    )
    provenance = {
        "dataset_id": request["dataset_id"],
        "source_type": "noaa_gsod",
        "provider": "NOAA National Centers for Environmental Information (NCEI)",
        "product": "Global Surface Summary of the Day (GSOD)",
        "station": request["station"],
        "data_kind": "observed",
        "data_kind_note": "Station observations summarised to daily values by NOAA (UTC days).",
        "retrieved_at_utc": request["retrieved_at_utc"],
        "files": request["files"],
        "years_missing_on_server": [f["year"] for f in request["files"] if f["http_status"] == 404],
        "station_metadata_history": station_metadata_history(frame),
        "units_converted": {"TEMP/MAX/MIN": "deg F -> deg C", "PRCP": "inches -> mm"},
        "missing_value_handling": (
            "TEMP/MAX/MIN 9999.9 -> NaN; PRCP 99.99 -> NaN; PRCP with attribute 'I' (no precipitation "
            "report that day) -> NaN, not 0. No imputation."
        ),
        "time_standard": "UTC day (0000Z-2359Z)",
        "per_year_coverage": {
            int(y): {k: (None if pd.isna(v) else float(v)) for k, v in row.items()} for y, row in per_year.iterrows()
        },
        "documentation": {"readme": GSOD_README_URL, "station_history": ISD_HISTORY_URL},
        "licence_notice": LICENCE_NOTICE,
        "processing_history": [
            "download yearly CSVs (bytes stored unmodified)",
            "parse; sentinel values -> NaN; unit conversion to SI",
            f"write {STORAGE_SUBDIR}/{request['dataset_id']}/daily.csv",
        ],
    }
    (out_dir / "provenance.json").write_text(json.dumps(provenance, indent=2))
    return provenance


def latest(processed_root: Path = PROCESSED_DIR, station: str = LUCKNOW_AIRPORT_STATION) -> tuple[pd.DataFrame, dict] | None:
    base = processed_root / STORAGE_SUBDIR
    provs = [json.loads(p.read_text()) for p in base.glob(f"gsod_{station}_*/provenance.json")] if base.exists() else []
    if not provs:
        return None
    prov = max(provs, key=lambda p: p["retrieved_at_utc"])
    frame = pd.read_csv(base / prov["dataset_id"] / "daily.csv", index_col="date", parse_dates=["date"])
    return frame, prov


def main(argv: list[str] | None = None) -> int:
    import argparse

    ap = argparse.ArgumentParser(description="Download and process NOAA GSOD station data.")
    ap.add_argument("--station", default=LUCKNOW_AIRPORT_STATION)
    ap.add_argument("--start-year", type=int, default=1981)
    ap.add_argument("--end-year", type=int, default=date.today().year - 1)
    ap.add_argument("--from-raw", type=Path, default=None)
    args = ap.parse_args(argv)
    raw_dir = args.from_raw or download(args.station, range(args.start_year, args.end_year + 1))
    prov = process(raw_dir)
    print(f"dataset_id: {prov['dataset_id']}")
    print(f"years missing on server: {prov['years_missing_on_server']}")
    print("station metadata history:")
    for r in prov["station_metadata_history"]:
        print(f"  {r['from']}..{r['to']}  {r['name']}  {r['lat']}, {r['lon']}, {r['elev_m']} m  ({r['n_days']} days)")
    print("NOTICE:", LICENCE_NOTICE)
    return 0


if __name__ == "__main__":
    sys.exit(main())
