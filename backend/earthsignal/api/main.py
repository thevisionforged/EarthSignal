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
from earthsignal.analysis import seasonal as seasonal_mod
from earthsignal.analysis import sensitivity as sensitivity_mod
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
            "endpoints": [
                "/api/health", "/api/datasets", "/api/provenance", "/api/timeseries", "/api/trend",
                "/api/seasonal", "/api/sensitivity",
            ],
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

    def _cutoff(ds: store.Dataset):
        return trend_mod.analysis_cutoff(datetime.fromisoformat(ds.provenance["retrieved_at_utc"]).date())

    @app.get("/api/seasonal")
    def seasonal(variable: Variable = "T2M", dataset_id: str | None = None) -> dict:
        ds = _load(dataset_id)
        cutoff = _cutoff(ds)
        try:
            rows = seasonal_mod.seasonal_trends(
                ds.frame[variable],
                variable=variable,
                units=ds.provenance["variables"][variable]["units"],
                data_kind=ds.provenance["data_kind"],
                last_allowed_day=cutoff,
            )
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        return {
            "dataset_id": ds.dataset_id,
            "variable": variable,
            "analysis_cutoff": cutoff.isoformat(),
            "season_definition": "India Meteorological Department seasons",
            "multiple_testing": "Benjamini-Hochberg FDR across the 4 seasons, applied to corrected Mann-Kendall p-values",
            "seasons": rows,
        }

    @app.get("/api/sensitivity")
    def sensitivity(variable: Variable = "T2M", dataset_id: str | None = None) -> dict:
        ds = _load(dataset_id)
        cutoff = _cutoff(ds)
        annual, _ = trend_mod.annual_means(ds.frame[variable], last_allowed_day=cutoff)
        try:
            windows = sensitivity_mod.window_sensitivity(
                annual, variable, ds.provenance["variables"][variable]["units"]
            )
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        source_periods = store.load_source_periods(processed_root, ds.dataset_id)
        geosit_in_window = None
        if source_periods and source_periods.get("first_geosit_day"):
            geosit_in_window = source_periods["first_geosit_day"] <= f"{int(annual.index.max())}-12-31"
        return {
            "dataset_id": ds.dataset_id,
            "variable": variable,
            "units": ds.provenance["variables"][variable]["units"],
            "analysis_cutoff": cutoff.isoformat(),
            **windows,
            "summary": {
                "vary_start": sensitivity_mod.summarize(windows["vary_start"]),
                "vary_end": sensitivity_mod.summarize(windows["vary_end"]),
            },
            "diagnostics": sensitivity_mod.diagnostics(windows),
            "source_periods": source_periods,
            "geosit_in_trend_window": geosit_in_window,
            "note": "Overlapping windows are descriptive robustness checks, not independent significance tests.",
        }

    return app


app = create_app()
