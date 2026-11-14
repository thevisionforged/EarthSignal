"""NOAA CPC Unified Gauge-Based Analysis of Global Daily Precipitation (CPCU), Lucknow subset.

Why: MERRA-2's corrected precipitation over land outside Africa is built from CPCU (Reichle & Liu 2014,
NASA/TM-2014-104606 Vol. 35, Table 3: "MERRA-2 Global land (excl. Africa) 1979 - present CPCU"). The memo
also says: "The CPCU 'V1.0' product was used for the period 1979-2005 and the CPCU 'real-time' ('RT') is used
for the period 2006-present." Comparing CPCU with MERRA-2, IMD and IMERG shows whether MERRA-2's behaviour is
inherited from its gauge input. See DECISIONS D-022.

Access: NOAA PSL THREDDS/OPeNDAP (public, no login), server-side subset, ASCII response.
  https://psl.noaa.gov/thredds/dodsC/Datasets/cpc_global_precip/precip.<YEAR>.nc
  Grid (read from the server 2026-11-15): lat[360] from 89.75 to -89.75 (descending), lon[720] from 0.25 to
  359.75, 0.5 deg; precip "Daily total of precipitation", units "mm", missing_value -9.96921E36.
  Note: PSL's copy is the operational archive; it does not state which CPCU version (V1.0 or RT) each year uses.
"""

from __future__ import annotations

import json
import re
import sys
from datetime import date
from pathlib import Path
from typing import Callable

import numpy as np
import pandas as pd

from earthsignal.config import RAW_DIR, STUDY_AREAS
from earthsignal.data import grid, power
from earthsignal.data.ingest import _http_get

BASE = "https://psl.noaa.gov/thredds/dodsC/Datasets/cpc_global_precip/precip.{year}.nc"
SUBDIR = "cpc"
DLAT = DLON = 0.5
MISSING = -9.96921e36


def lat_centres() -> np.ndarray:
    return 89.75 - 0.5 * np.arange(360)


def lon_centres() -> np.ndarray:
    return 0.25 + 0.5 * np.arange(720)


def lucknow_index_box() -> tuple[int, int, int, int]:
    """Smallest index box (j0, j1, i0, i1) covering both Lucknow MERRA-2 cells."""
    cells = []
    for a in STUDY_AREAS.values():
        b = grid.merra2_cell(a.latitude, a.longitude)
        cells += grid.overlap_weights(lat_centres(), lon_centres(), DLAT, DLON, b)
    js, is_ = [c[0] for c in cells], [c[1] for c in cells]
    return min(js), max(js), min(is_), max(is_)


def subset_url(year: int, idx: tuple[int, int, int, int]) -> str:
    j0, j1, i0, i1 = idx
    n = 366 if pd.Timestamp(year=year, month=12, day=31).is_leap_year else 365
    return f"{BASE.format(year=year)}.ascii?precip%5B0:1:{n - 1}%5D%5B{j0}:1:{j1}%5D%5B{i0}:1:{i1}%5D"


def parse_ascii(text: str, year: int, idx: tuple[int, int, int, int]) -> np.ndarray:
    """OPeNDAP ASCII grid -> array (days, nlat, nlon) in mm, NaN for missing."""
    j0, j1, i0, i1 = idx
    nlat, nlon = j1 - j0 + 1, i1 - i0 + 1
    rows = re.findall(r"^\[(\d+)\]\[(\d+)\],\s*(.+)$", text, flags=re.M)
    n = 366 if pd.Timestamp(year=year, month=12, day=31).is_leap_year else 365
    if len(rows) != n * nlat:
        raise ValueError(f"CPC {year}: {len(rows)} data rows, expected {n * nlat}")
    arr = np.full((n, nlat, nlon), np.nan)
    for t, j, vals in rows:
        v = np.array([float(x) for x in vals.split(",")])
        if v.size != nlon:
            raise ValueError("unexpected row length")
        arr[int(t), int(j)] = v
    arr[arr < -1e30] = np.nan
    if np.nanmin(arr) < 0:
        raise ValueError("negative precipitation in CPC subset")
    return arr


PAUSE_S = 10.0  # courtesy spacing between yearly requests (PSL returned 429 during probing)
MAX_429_TRIES = 5


def polite_get(url: str, sleep=None, get: Callable[[str], bytes] = _http_get) -> bytes:
    """GET that honours HTTP 429 Retry-After (default 120 s), up to MAX_429_TRIES attempts."""
    import time

    import httpx

    sleep = sleep or time.sleep
    for attempt in range(MAX_429_TRIES):
        try:
            return get(url)
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code != 429 or attempt == MAX_429_TRIES - 1:
                raise
            ra = exc.response.headers.get("retry-after", "")
            wait = float(ra) if ra.strip().isdigit() else 120.0
            print(f"  429 from server; waiting {wait:.0f} s (attempt {attempt + 1}/{MAX_429_TRIES})", flush=True)
            sleep(wait)
    raise AssertionError("unreachable")


def download(years: range, raw_root: Path = RAW_DIR, http_get: Callable[[str], bytes] = None,
             pause_s: float = PAUSE_S) -> Path:
    import time

    http_get = http_get or polite_get
    retrieved_at = power.utc_now()
    idx = lucknow_index_box()
    raw_dir = raw_root / SUBDIR / f"cpcu_lucknow_{years.start}_{years.stop - 1}_{retrieved_at:%Y%m%dT%H%M%SZ}"
    payloads, files = {}, []
    for k, y in enumerate(years):
        if k and pause_s:
            time.sleep(pause_s)
        url = subset_url(y, idx)
        payload = http_get(url)
        print(f"  {y}: {len(payload)} bytes", flush=True)
        parse_ascii(payload.decode(), y, idx)  # verify before anything is written
        payloads[f"precip_{y}.ascii"] = payload
        files.append({"year": y, "url": url, "file": f"precip_{y}.ascii", "sha256": power.sha256_bytes(payload)})
    for name, p in payloads.items():
        power.write_immutable(raw_dir / name, p)
    request = {
        "source": "NOAA CPC Unified Gauge-Based Analysis of Global Daily Precipitation, via NOAA PSL THREDDS",
        "index_box": {"lat_index": [idx[0], idx[1]], "lon_index": [idx[2], idx[3]],
                      "lat": [float(lat_centres()[idx[0]]), float(lat_centres()[idx[1]])],
                      "lon": [float(lon_centres()[idx[2]]), float(lon_centres()[idx[3]])]},
        "retrieved_at_utc": retrieved_at.isoformat(),
        "files": files,
    }
    power.write_immutable(raw_dir / "request.json", json.dumps(request, indent=2).encode())
    return raw_dir


def main(argv: list[str] | None = None) -> int:
    import argparse

    ap = argparse.ArgumentParser(description="Download the CPCU Lucknow subset from NOAA PSL.")
    ap.add_argument("--start-year", type=int, default=1998)
    ap.add_argument("--end-year", type=int, default=2024)
    a = ap.parse_args(argv)
    d = download(range(a.start_year, a.end_year + 1))
    print(f"stored {d}")
    print(json.loads((d / 'request.json').read_text())["index_box"])
    return 0


if __name__ == "__main__":
    sys.exit(main())


# ---------------- CPC archive daily files: gauge counts (README, GAUGE_GLB/DOCU) ----------------
# README: "1979 - 2005 : Rereospective Version (30K+ gauges); 2006 - Present : Real-time version (~17K gauges)".
# "In each daily file, there are two global fields: analyzed field of daily precipitation in 0.1mm; and number of
# gauges available in each 0.5deg lat/lon grid box." CTL: little_endian, undef -999.0, xdef 720 from 0.25,
# ydef 360 from -89.75 (south to north).
ARCHIVE = "https://ftp.cpc.ncep.noaa.gov/precip/CPC_UNI_PRCP/GAUGE_GLB"
NX_A, NY_A = 720, 360


def archive_urls(day: date) -> list[str]:
    ymd = f"{day:%Y%m%d}"
    name = "PRCP_CU_GAUGE_V1.0GLB_0.50deg.lnx"
    if day.year <= 2005:
        return [f"{ARCHIVE}/V1.0/{day.year}/{name}.{ymd}.gz", f"{ARCHIVE}/V1.0/{day.year}/{name}.{ymd}"]
    # Naming varies by year in the RT archive (observed 2026-11-15): 2006 "...20060715RT.gz",
    # 2007-2008 "...20070715.RT.gz", 2014 "...20140715.RT" (uncompressed).
    base = f"{ARCHIVE}/RT/{day.year}/{name}.{ymd}"
    return [f"{base}.RT", f"{base}RT", f"{base}.RT.gz", f"{base}RT.gz"]


def read_archive_day(payload: bytes) -> tuple[np.ndarray, np.ndarray]:
    """-> (rain_mm[lat S->N, lon], gauge_count[lat, lon]); NaN where undefined."""
    import gzip

    if payload[:2] == b"\x1f\x8b":
        payload = gzip.decompress(payload)
    if len(payload) != NX_A * NY_A * 2 * 4:
        raise ValueError(f"unexpected CPC daily file size {len(payload)}")
    a = np.frombuffer(payload, dtype="<f4").reshape(2, NY_A, NX_A).astype("float64")
    a[np.isclose(a, -999.0)] = np.nan
    return a[0] / 10.0, a[1]


def archive_lat_centres() -> np.ndarray:
    return -89.75 + 0.5 * np.arange(NY_A)


def download_gauge_sample(days: list[date], raw_root: Path = RAW_DIR, http_status=None, pause_s: float = 2.0) -> Path:
    """Fetch selected CPC daily files (bytes unmodified) to examine gauge counts over Lucknow."""
    import time

    from earthsignal.data.gsod import _http_get_status

    http_status = http_status or _http_get_status
    retrieved_at = power.utc_now()
    raw_dir = raw_root / SUBDIR / f"cpcu_archive_sample_{days[0]:%Y%m%d}_{days[-1]:%Y%m%d}_{retrieved_at:%Y%m%dT%H%M%SZ}"
    files = []
    for d in days:
        for url in archive_urls(d):
            status, payload = http_status(url)
            if status == 200:
                read_archive_day(payload)  # verify format before storing
                name = url.rsplit("/", 1)[-1]
                power.write_immutable(raw_dir / name, payload)
                files.append({"date": d.isoformat(), "url": url, "file": name, "sha256": power.sha256_bytes(payload)})
                print(f"  {d}: {name} ({len(payload)} bytes)", flush=True)
                break
            if status != 404:
                raise RuntimeError(f"HTTP {status} for {url}")
        else:
            files.append({"date": d.isoformat(), "url": archive_urls(d), "file": None, "http_status": 404})
            print(f"  {d}: not found", flush=True)
        if pause_s:
            time.sleep(pause_s)
    req = {"source": "NOAA CPC Unified gauge analysis, CPC HTTPS archive (daily binary incl. gauge counts)",
           "readme": f"{ARCHIVE}/DOCU/PRCP_CU_GAUGE_V1.0GLB_0.50deg_README.txt",
           "retrieved_at_utc": retrieved_at.isoformat(), "files": files}
    power.write_immutable(raw_dir / "request.json", json.dumps(req, indent=2).encode())
    return raw_dir


NEIGHBOURHOOD_DEG = 2.0  # gauges within +-2 deg of the cell also inform CPC's optimal interpolation


def process_gauge_samples(raw_root: Path = RAW_DIR, processed_root: Path | None = None) -> dict:
    """Gauge counts near each study area for every sampled day in ALL stored archive samples
    (later retrievals win for a duplicate date)."""
    from earthsignal.config import PROCESSED_DIR

    processed_root = processed_root or PROCESSED_DIR
    entries: dict[str, tuple[Path, dict, str]] = {}
    readme = ""
    for raw_dir in sorted((raw_root / SUBDIR).glob("cpcu_archive_sample_*")):
        if not (raw_dir / "request.json").exists():
            continue  # incomplete run
        r = json.loads((raw_dir / "request.json").read_text())
        readme = r["readme"]
        for f in r["files"]:
            if f.get("file"):
                entries[f["date"]] = (raw_dir, f, r["source"])
    req = {"source": next(iter(entries.values()))[2] if entries else "", "readme": readme,
           "files": [dict(f, _dir=str(d)) for d, f, _ in (entries[k] for k in sorted(entries))]}
    lat, lon = archive_lat_centres(), lon_centres()
    out: dict = {"source": req["source"], "readme": req["readme"], "n_days": len(req["files"]),
                 "neighbourhood_deg": NEIGHBOURHOOD_DEG, "areas": {}}
    for key, a in STUDY_AREAS.items():
        b = grid.merra2_cell(a.latitude, a.longitude)
        cells = grid.overlap_weights(lat, lon, DLAT, DLON, b)
        nb = grid.Box(b.south - NEIGHBOURHOOD_DEG, b.north + NEIGHBOURHOOD_DEG, b.west - NEIGHBOURHOOD_DEG, b.east + NEIGHBOURHOOD_DEG)
        nj = np.where((lat > nb.south) & (lat < nb.north))[0]
        ni = np.where((lon > nb.west) & (lon < nb.east))[0]
        rows = []
        for f in req["files"]:
            if not f.get("file"):
                continue
            _, g = read_archive_day((Path(f["_dir"]) / f["file"]).read_bytes())
            rows.append({
                "date": f["date"],
                "version": "RT" if "RT" in f["file"].rsplit(".lnx.", 1)[-1] else "V1.0",
                "gauges_in_cell_boxes": int(np.nansum([g[j, i] for j, i, *_ in cells])),
                "gauges_in_neighbourhood": int(np.nansum(g[np.ix_(nj, ni)])),
                "gauges_global": int(np.nansum(g)),
            })
        out["areas"][key] = rows
    dest = processed_root / SUBDIR / "gauge_counts.json"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(out, indent=2))
    return out


def latest_gauge_counts(processed_root: Path | None = None) -> dict | None:
    from earthsignal.config import PROCESSED_DIR

    p = (processed_root or PROCESSED_DIR) / SUBDIR / "gauge_counts.json"
    return json.loads(p.read_text())["areas"] if p.exists() else None
