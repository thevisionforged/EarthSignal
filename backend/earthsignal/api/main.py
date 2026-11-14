"""EarthSignal HTTP API.

Run (from repo root):  .venv\\Scripts\\python -m uvicorn earthsignal.api.main:app --app-dir backend --port 8000
"""

from __future__ import annotations

import math
from datetime import datetime
from pathlib import Path
from typing import Literal

import pandas as pd
from fastapi import FastAPI, HTTPException, Query

from earthsignal import __version__
from earthsignal.analysis import trend as trend_mod
from earthsignal.config import PROCESSED_DIR
from earthsignal.data import store

MONTHLY_MIN_COVERAGE = 0.9

Variable = Literal["T2M", "PRECTOTCORR"]


def _clean(values) -> list[float | None]:
    return [None if (v is None or (isinstance(v, float) and math.isnan(v))) else round(float(v), 4) for v in values]


def create_app(processed_root: Path = PROCESSED_DIR) -> FastAPI:
    app = FastAPI(title="EarthSignal API", version=__version__)

    def _load(dataset_id: str | None) -> store.Dataset:
        try:
            return store.load_dataset(processed_root, dataset_id)
        except store.NoDatasetError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.get("/")
    def root() -> dict:
        return {
            "service": "EarthSignal API",
            "version": __version__,
            "endpoints": ["/api/health", "/api/datasets", "/api/provenance", "/api/timeseries", "/api/trend"],
            "docs": "/docs",
            "ui": "Run the frontend (cd frontend; npm run dev) and open the URL Vite prints.",
        }

    @app.get("/api/health")
    def health() -> dict:
        n = len(store.list_provenance(processed_root))
        return {"status": "ok", "version": __version__, "datasets_available": n}

    @app.get("/api/datasets")
    def datasets() -> list[dict]:
        return [
            {
                "dataset_id": p["dataset_id"],
                "retrieved_at_utc": p["retrieved_at_utc"],
                "requested": p["requested"],
                "api_version": p["api_version"],
                "data_kind": p["data_kind"],
            }
            for p in store.list_provenance(processed_root)
        ]

    @app.get("/api/provenance")
    def provenance(dataset_id: str | None = None) -> dict:
        return _load(dataset_id).provenance

    @app.get("/api/timeseries")
    def timeseries(
        variable: Variable = "T2M",
        resolution: Literal["daily", "monthly", "annual"] = "monthly",
        dataset_id: str | None = None,
    ) -> dict:
        ds = _load(dataset_id)
        daily = ds.frame[variable]
        if resolution == "daily":
            series = daily
            labels = [d.strftime("%Y-%m-%d") for d in series.index]
            note = "Daily values (Local Solar Time). Missing days are null."
        elif resolution == "monthly":
            grouped = daily.resample("MS")
            coverage = grouped.count() / grouped.size()
            series = grouped.mean().where(coverage >= MONTHLY_MIN_COVERAGE)
            labels = [d.strftime("%Y-%m") for d in series.index]
            note = f"Monthly mean of daily values; months with <{MONTHLY_MIN_COVERAGE:.0%} valid days are null."
        else:
            series, _ = trend_mod.annual_means(daily)
            labels = [str(y) for y in series.index]
            note = f"Calendar-year mean; years with <{trend_mod.MIN_YEAR_COVERAGE:.0%} valid days omitted."
        var_meta = ds.provenance["variables"][variable]
        return {
            "dataset_id": ds.dataset_id,
            "variable": variable,
            "longname": var_meta["longname"],
            "units": var_meta["units"],
            "resolution": resolution,
            "data_kind": ds.provenance["data_kind"],
            "data_kind_note": ds.provenance["data_kind_note"],
            "aggregation_note": note,
            "dates": labels,
            "values": _clean(series.tolist()),
        }

    @app.get("/api/trend")
    def trend(variable: Variable = "T2M", dataset_id: str | None = None) -> dict:
        ds = _load(dataset_id)
        retrieved = datetime.fromisoformat(ds.provenance["retrieved_at_utc"]).date()
        cutoff = trend_mod.analysis_cutoff(retrieved)
        annual, excluded = trend_mod.annual_means(ds.frame[variable], last_allowed_day=cutoff)
        try:
            result = trend_mod.analyze_trend(
                annual,
                variable=variable,
                units=ds.provenance["variables"][variable]["units"],
                excluded_years=excluded,
                data_kind=ds.provenance["data_kind"],
            )
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        return {
            "dataset_id": ds.dataset_id,
            "analysis_cutoff": cutoff.isoformat(),
            "annual_means": {"years": [int(y) for y in annual.index], "values": _clean(annual.tolist())},
            "result": result.to_dict(),
        }

    return app


app = create_app()
