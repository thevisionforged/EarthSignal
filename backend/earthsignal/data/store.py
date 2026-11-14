"""Read access to processed datasets produced by earthsignal.data.ingest."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd


class NoDatasetError(LookupError):
    pass


@dataclass
class Dataset:
    dataset_id: str
    frame: pd.DataFrame
    provenance: dict[str, Any]


def list_provenance(processed_root: Path) -> list[dict[str, Any]]:
    out = []
    if not processed_root.exists():
        return out
    for prov_path in processed_root.glob("*/provenance.json"):
        out.append(json.loads(prov_path.read_text()))
    out.sort(key=lambda p: p["retrieved_at_utc"], reverse=True)
    return out


def load_source_periods(processed_root: Path, dataset_id: str) -> dict[str, Any] | None:
    """Result of earthsignal.data.source_probe for this dataset, if it has been run."""
    path = processed_root / dataset_id / "source_periods.json"
    return json.loads(path.read_text()) if path.exists() else None


def load_dataset(processed_root: Path, dataset_id: str | None = None) -> Dataset:
    provs = list_provenance(processed_root)
    if not provs:
        raise NoDatasetError(
            "No processed NASA POWER dataset found. Run: python -m earthsignal.data.ingest"
        )
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
