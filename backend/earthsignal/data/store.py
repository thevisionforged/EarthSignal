"""Read access to processed NASA POWER datasets produced by earthsignal.data.ingest.

Each processed dataset lives in `<processed_root>/<dataset_id>/` with `daily.csv` and
`provenance.json`. A dataset belongs to the study area whose coordinates match the requested
coordinates in its provenance. Station datasets live under `<processed_root>/stations/` and are
not returned here.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd

from earthsignal.config import STUDY_AREAS


class NoDatasetError(LookupError):
    pass


@dataclass
class Dataset:
    dataset_id: str
    frame: pd.DataFrame
    provenance: dict[str, Any]


def area_of(prov: dict[str, Any]) -> str | None:
    req = prov.get("requested", {})
    for key, area in STUDY_AREAS.items():
        if area.matches(req.get("latitude", 999), req.get("longitude", 999)):
            return key
    return None


def list_provenance(processed_root: Path, area: str | None = None) -> list[dict[str, Any]]:
    out = []
    if not processed_root.exists():
        return out
    for prov_path in processed_root.glob("*/provenance.json"):
        prov = json.loads(prov_path.read_text())
        if area is None or area_of(prov) == area:
            out.append(prov)
    out.sort(key=lambda p: p["retrieved_at_utc"], reverse=True)
    return out


def load_source_periods(processed_root: Path, dataset_id: str) -> dict[str, Any] | None:
    """Result of earthsignal.data.source_probe for this dataset, if it has been run."""
    path = processed_root / dataset_id / "source_periods.json"
    return json.loads(path.read_text()) if path.exists() else None


def load_dataset(processed_root: Path, dataset_id: str | None = None, area: str | None = None) -> Dataset:
    provs = list_provenance(processed_root, area)
    if not provs:
        where = f" for area {area!r}" if area else ""
        cmd = "python -m earthsignal.data.ingest" + (f" --area {area}" if area else "")
        raise NoDatasetError(f"No processed NASA POWER dataset found{where}. Run: {cmd}")
    if dataset_id is None:
        prov = provs[0]
    else:
        matches = [p for p in provs if p["dataset_id"] == dataset_id]
        if not matches:
            raise NoDatasetError(f"dataset {dataset_id!r} not found")
        prov = matches[0]
    frame = pd.read_csv(
        processed_root / prov["dataset_id"] / "daily.csv", index_col="date", parse_dates=["date"]
    )
    return Dataset(dataset_id=prov["dataset_id"], frame=frame, provenance=prov)
