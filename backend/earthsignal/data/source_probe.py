"""Find the date where NASA POWER's daily series switches from MERRA-2 to GEOS-IT.

The full-range response header lists every source used (e.g. ["MERRA2", "GEOSIT"]) but not
which dates came from which. Single-day requests report the source for that day (verified
2026-11-15: 2026-08-01 -> MERRA2, 2026-10-01 -> GEOSIT). We binary-search single-day requests
between a known-MERRA2 day and a known-GEOSIT day.

Assumption (checked at both ends, not at every day): the source is MERRA2 up to some date and
GEOSIT after it. The boundary moves forward as NASA back-fills MERRA-2, so the result is only
valid at the probe time, which is recorded.

Usage:  python -m earthsignal.data.source_probe [--area lucknow_airport]   # probes, stores raw, writes result
"""

from __future__ import annotations

import json
import sys
from datetime import date, timedelta
from pathlib import Path
from typing import Any, Callable

from earthsignal.config import DEFAULT_AREA, PROCESSED_DIR, RAW_DIR, STUDY_AREAS, StudyArea
from earthsignal.data import power, store
from earthsignal.data.ingest import _http_get, _repo_relative

MAX_PROBES = 20


def _day_source(area: StudyArea, day: date, http_get: Callable[[str], bytes]) -> tuple[list[str], str, bytes]:
    url = power.build_daily_point_url(area.latitude, area.longitude, day, day, parameters=("T2M",))
    payload = http_get(url)
    doc = json.loads(payload)
    return list(doc["header"].get("sources", [])), url, payload


def find_boundary(
    area: StudyArea, first: date, last: date, http_get: Callable[[str], bytes] = _http_get
) -> dict[str, Any]:
    """Return the last MERRA2 day and first GEOSIT day within [first, last], plus every probe made."""
    probes: list[dict[str, Any]] = []
    payloads: list[tuple[str, bytes]] = []

    def probe(day: date) -> list[str]:
        if len(probes) >= MAX_PROBES:
            raise RuntimeError("probe limit reached")
        sources, url, payload = _day_source(area, day, http_get)
        probes.append({"date": day.isoformat(), "sources": sources, "url": url})
        payloads.append((day.isoformat(), payload))
        return sources

    lo_src, hi_src = probe(first), probe(last)
    if lo_src != ["MERRA2"]:
        raise ValueError(f"{first} is not MERRA2-only ({lo_src}); choose an earlier start")
    if hi_src == ["MERRA2"]:
        return {"geosit_present": False, "last_merra2_day": last.isoformat(), "first_geosit_day": None,
                "probes": probes, "_payloads": payloads}
    if hi_src != ["GEOSIT"]:
        raise ValueError(f"unexpected source label at {last}: {hi_src}")

    lo, hi = first, last  # invariant: lo is MERRA2, hi is GEOSIT
    while (hi - lo).days > 1:
        mid = lo + timedelta(days=(hi - lo).days // 2)
        src = probe(mid)
        if src == ["MERRA2"]:
            lo = mid
        elif src == ["GEOSIT"]:
            hi = mid
        else:
            raise ValueError(f"unexpected source label at {mid}: {src}")
    return {"geosit_present": True, "last_merra2_day": lo.isoformat(), "first_geosit_day": hi.isoformat(),
            "probes": probes, "_payloads": payloads}


def run(
    processed_root: Path = PROCESSED_DIR, raw_root: Path = RAW_DIR, http_get=_http_get, area_key: str = DEFAULT_AREA
) -> dict[str, Any]:
    area = STUDY_AREAS[area_key]
    ds = store.load_dataset(processed_root, area=area_key)
    last_valid = max(v["last_valid"] for v in ds.provenance["validation"]["variables"].values())
    first = date(2020, 1, 1)
    last = date.fromisoformat(last_valid)
    retrieved_at = power.utc_now()
    result = find_boundary(area, first, last, http_get)

    probe_dir = raw_root / f"{ds.dataset_id}__source_probe_{retrieved_at:%Y%m%dT%H%M%SZ}"
    for day, payload in result.pop("_payloads"):
        power.write_immutable(probe_dir / f"day_{day}.json", payload)

    record = {
        "dataset_id": ds.dataset_id,
        "probed_at_utc": retrieved_at.isoformat(),
        "method": "binary search of single-day POWER requests; header.sources per day",
        "assumption": "MERRA2 up to a boundary date, GEOSIT after it (checked at search endpoints)",
        "raw_probe_dir": _repo_relative(probe_dir).as_posix(),
        **result,
        "note": (
            "Boundary as served at probe time. The dataset itself was retrieved at "
            f"{ds.provenance['retrieved_at_utc']}; NASA back-fills MERRA-2 over time, so the boundary "
            "at that retrieval may have been slightly earlier."
        ),
    }
    out = processed_root / ds.dataset_id / "source_periods.json"
    out.write_text(json.dumps(record, indent=2))
    return record


def main(argv: list[str] | None = None) -> int:
    import argparse

    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--area", choices=sorted(STUDY_AREAS), default=DEFAULT_AREA)
    rec = run(area_key=ap.parse_args(argv).area)
    print(f"dataset {rec['dataset_id']}: GEOS-IT present={rec['geosit_present']}")
    print(f"  last MERRA-2 day: {rec['last_merra2_day']}   first GEOS-IT day: {rec['first_geosit_day']}")
    print(f"  {len(rec['probes'])} single-day requests; raw responses in {rec['raw_probe_dir']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
