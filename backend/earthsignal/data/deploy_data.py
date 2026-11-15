"""Deployment data preparation (DECISIONS D-027).

The repository carries a snapshot of the processed public NASA datasets (POWER for both cells, GPM IMERG via
POWER) and the NOAA CPC gauge counts. Two sources are NOT committed:

* NOAA GSOD station data: non-US station data is for non-commercial research use (WMO Resolution 40).
* IMD gridded rainfall: no redistribution terms were found.

For a deployment, this module downloads those two from their official servers at build time, checks every
file against the SHA-256 checksums recorded when the analysis was done (data/manifests/), and processes them
with the same code as local development. Raw files stay on the build machine and are deleted after processing
(the Dockerfile does this); the processed provenance keeps each file's checksum.

    python -m earthsignal.data.deploy_data --check               # exit 1 unless the required NASA snapshot is present
    python -m earthsignal.data.deploy_data --fetch gsod imd      # download, verify, process (skips what is present)
    python -m earthsignal.data.deploy_data --precompute-forecast DIR   # run the D-026 evaluation once, cache it in DIR
    python -m earthsignal.data.deploy_data --write-manifests     # maintainer: record checksums from current provenance
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Callable

from earthsignal.config import PROCESSED_DIR, RAW_DIR, REPO_ROOT
from earthsignal.data import gsod, imd, store

MANIFEST_DIR = REPO_ROOT / "data" / "manifests"
GSOD_MANIFEST = "gsod_42369099999.json"
IMD_MANIFEST = "imd_rf025.json"


def compare(expected: dict[str, str], got: dict[str, str]) -> dict[str, list[str]]:
    """Per-year checksum comparison. Keys are years as strings; values are SHA-256 hex digests."""
    return {
        "matched": sorted(y for y in expected if got.get(y) == expected[y]),
        "changed": sorted(y for y in expected if y in got and got[y] != expected[y]),
        "missing": sorted(y for y in expected if y not in got),
        "extra": sorted(y for y in got if y not in expected),
    }


def _report(name: str, result: dict[str, list[str]], strict: bool) -> bool:
    ok = not (result["changed"] or result["missing"] or result["extra"])
    print(f"{name}: {len(result['matched'])} files match the recorded checksums", flush=True)
    for k in ("changed", "missing", "extra"):
        if result[k]:
            print(f"  {k}: {', '.join(result[k])}", flush=True)
    if not ok:
        print(
            f"  NOTE: {name} differs from the analysed version. The processed provenance records the new checksums, "
            "so results stay traceable, but numbers may differ slightly from the documentation."
            + (" Failing because --strict was given." if strict else ""),
            flush=True,
        )
    return ok or not strict


def load_manifest(name: str, manifest_dir: Path = MANIFEST_DIR) -> dict[str, Any]:
    return json.loads((manifest_dir / name).read_text(encoding="utf-8"))


def fetch_gsod(manifest: dict[str, Any], raw_root: Path, processed_root: Path, strict: bool,
               http_get_status: Callable | None = None) -> bool:
    if gsod.latest(processed_root, manifest["station"]) is not None:
        print("gsod: processed station data already present, skipping download", flush=True)
        return True
    years = range(manifest["years"][0], manifest["years"][1] + 1)
    kw = {"http_get_status": http_get_status} if http_get_status else {}
    raw_dir = gsod.download(manifest["station"], years, raw_root=raw_root, **kw)
    req = json.loads((raw_dir / "request.json").read_text())
    got = {str(f["year"]): f["sha256"] for f in req["files"] if "sha256" in f}
    ok = _report("gsod", compare(manifest["sha256"], got), strict)
    if ok:
        gsod.process(raw_dir, processed_root=processed_root)
        print(f"gsod: processed. {gsod.LICENCE_NOTICE}", flush=True)
    return ok


def fetch_imd(manifest: dict[str, Any], raw_root: Path, processed_root: Path, strict: bool,
              post: Callable | None = None) -> bool:
    if imd.latest(processed_root) is not None:
        print("imd: processed gauge-grid data already present, skipping download", flush=True)
        return True
    got: dict[str, str] = {}
    for y in sorted(int(k) for k in manifest["sha256"]):
        kw = {"post": post} if post else {}
        d = imd.download_year(y, raw_root=raw_root, **kw)
        got[str(y)] = json.loads((d / "request.json").read_text())["sha256"]
        print(f"imd: {y} downloaded", flush=True)
    ok = _report("imd", compare(manifest["sha256"], got), strict)
    if ok:
        imd.process(raw_root=raw_root, processed_root=processed_root)
        print(f"imd: processed. Cite: {imd.CITATION}", flush=True)
    return ok


def write_manifests(processed_root: Path = PROCESSED_DIR, manifest_dir: Path = MANIFEST_DIR) -> None:
    manifest_dir.mkdir(parents=True, exist_ok=True)
    got = gsod.latest(processed_root)
    if got:
        prov = got[1]
        files = [f for f in prov["files"] if "sha256" in f]
        (manifest_dir / GSOD_MANIFEST).write_text(json.dumps({
            "source": "NOAA NCEI GSOD", "station": prov["station"],
            "years": [min(f["year"] for f in prov["files"]), max(f["year"] for f in prov["files"])],
            "url_template": gsod.GSOD_ACCESS_URL,
            "recorded_from_dataset": prov["dataset_id"],
            "note": "Checksums only. The station data itself is not committed (WMO Resolution 40).",
            "sha256": {str(f["year"]): f["sha256"] for f in files},
        }, indent=2) + "\n", encoding="utf-8")
    got = imd.latest(processed_root)
    if got:
        prov = got[1]
        (manifest_dir / IMD_MANIFEST).write_text(json.dumps({
            "source": "IMD Pune 0.25 deg daily gridded rainfall (binary)", "download_url": imd.DOWNLOAD_URL,
            "recorded_from_dataset": prov["dataset_id"],
            "note": "Checksums only. IMD files are not committed (no redistribution terms found). Cite Pai et al. (2014).",
            "sha256": {str(f["year"]): f["sha256"] for f in prov["files"]},
        }, indent=2) + "\n", encoding="utf-8")


def precompute_forecast(cache_dir: Path, processed_root: Path = PROCESSED_DIR) -> bool:
    """Run the pre-registered evaluation for every area and cache it (same code path as the API)."""
    from earthsignal.api.forecast import build_router, cache_path
    from earthsignal.config import STUDY_AREAS

    build_router(processed_root, cache_dir).warm()
    ok = True
    for area in STUDY_AREAS:
        provs = store.list_provenance(processed_root, area)
        done = bool(provs) and cache_path(cache_dir, area, provs[0]["dataset_id"]).is_file()
        print(f"forecast evaluation {area}: {'cached' if done else 'NOT cached'}", flush=True)
        ok = ok and done
    return ok


def check(processed_root: Path = PROCESSED_DIR) -> bool:
    from earthsignal.api.deploy import data_status

    status = data_status(processed_root)
    print(json.dumps(status, indent=2), flush=True)
    return bool(status["ready"])


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--check", action="store_true", help="fail unless NASA POWER data is present for every study area")
    ap.add_argument("--fetch", nargs="*", choices=["gsod", "imd"], default=[], help="sources to download and verify")
    ap.add_argument("--strict", action="store_true", help="fail when a downloaded file differs from the recorded checksum")
    ap.add_argument("--write-manifests", action="store_true")
    ap.add_argument("--precompute-forecast", type=Path, default=None, metavar="CACHE_DIR")
    args = ap.parse_args(argv)
    if args.write_manifests:
        write_manifests()
        return 0
    ok = True
    for src in args.fetch:
        fn = fetch_gsod if src == "gsod" else fetch_imd
        manifest = load_manifest(GSOD_MANIFEST if src == "gsod" else IMD_MANIFEST)
        try:
            ok = fn(manifest, RAW_DIR, PROCESSED_DIR, args.strict) and ok
        except Exception as exc:  # a source being unreachable must not hide the others
            print(f"{src}: FAILED: {type(exc).__name__}: {exc}", flush=True)
            ok = ok and not args.strict
    if args.check:
        ok = check() and ok
    if args.precompute_forecast is not None:
        ok = precompute_forecast(args.precompute_forecast) and ok
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
