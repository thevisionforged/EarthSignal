"""Forecast API (DECISIONS D-026). GET /api/forecast?area=...&format=json|csv

Returns the pre-registered evaluation scorecard and, only for leads that passed it, a temperature
forecast issued from the last available day. Labelled data_kind "forecast"."""

from __future__ import annotations

import io
from pathlib import Path
from typing import Literal

import pandas as pd
from fastapi import APIRouter, HTTPException
from fastapi.responses import PlainTextResponse

from earthsignal.analysis import forecast as fc
from earthsignal.config import DEFAULT_AREA, STUDY_AREAS
from earthsignal.data import store

LIMITATIONS = [
    "Forecasts and their verification use NASA POWER reanalysis (daily mean 2 m temperature for a ~55 × 62 km grid cell), "
    "not a thermometer at a specific place.",
    "The improvement over the strongest simple method (damped anomaly persistence) is modest: about 2–7% lower mean squared error.",
    "Beyond about two weeks the forecast is close to the seasonal average; most of its value is in the first week.",
    "The latest days used to start the forecast are provisional near-real-time data that NASA may revise.",
    "The 5–95% band comes from past forecast errors at each lead. It is not a guarantee; about 1 day in 10 should fall outside it.",
    "This is a statistical forecast from past temperatures only. It knows nothing about current weather systems, so official "
    "IMD forecasts should always take precedence.",
]
METHOD = [
    "Anomaly = daily mean temperature minus a smooth seasonal cycle (3 harmonics) fitted to past data.",
    "Anomaly regression: for each lead (1–30 days), the future anomaly is predicted from today's anomaly, the two days "
    "before, and the 7- and 30-day average anomalies, with weights fitted on past data only.",
    "Pre-registered test (D-026): two candidate methods, chosen per lead on 2002–2013, judged once on 2014–2025 against "
    "damped anomaly persistence. A lead passes only if the improvement is positive with year-block bootstrap 5th percentile above zero.",
    "A forecast is shown only for the unbroken run of passing leads starting at lead 1.",
]


def build_router(processed_root: Path) -> APIRouter:
    r = APIRouter(tags=["forecast"])
    cache: dict[tuple[str, str], dict] = {}

    def compute(area: str) -> dict:
        if area not in STUDY_AREAS:
            raise HTTPException(status_code=422, detail=f"unknown area {area!r}")
        try:
            ds = store.load_dataset(processed_root, area=area)
        except store.NoDatasetError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        key = (area, ds.dataset_id)
        if key not in cache:
            t = ds.frame["T2M"]
            last_eval = pd.Timestamp(fc.HOLDOUT_YEARS[1], 12, 31)
            if t.dropna().index.max() < last_eval:
                raise HTTPException(status_code=422, detail=f"data must cover {last_eval.date()} for the pre-registered evaluation")
            try:
                folds = fc.run_folds(t[t.index <= last_eval], fc.DEV_YEARS[0], fc.HOLDOUT_YEARS[1])
                evaluation = fc.evaluate(folds)
            except ValueError as exc:
                raise HTTPException(status_code=422, detail=str(exc)) from exc
            issued = fc.issue(t, evaluation)
            sp = store.load_source_periods(processed_root, ds.dataset_id) or {}
            first_geosit = sp.get("first_geosit_day")
            provisional = bool(issued and first_geosit and issued["origin"] >= first_geosit)
            cache[key] = {
                "area": area, "variable": "T2M", "units": "°C (daily mean)",
                "data_kind": "forecast",
                "evaluation_data_kind": "evaluation_statistic",
                "evaluation": evaluation,
                "forecast": issued,
                "origin_provisional": provisional if issued else None,
                "no_forecast_reason": None if issued else ("No lead passed the pre-registered test." if evaluation["horizon_days"] == 0
                                                           else "The last 30 days contain a gap, so the method cannot be applied."),
                "data_version": {"dataset_id": ds.dataset_id, "retrieved_at_utc": ds.provenance["retrieved_at_utc"],
                                 "api_version": ds.provenance["api_version"]},
                "method": METHOD, "limitations": LIMITATIONS,
            }
        return cache[key]

    @r.get("/api/forecast")
    def forecast(area: str = DEFAULT_AREA, format: Literal["json", "csv"] = "json"):
        res = compute(area)
        if format == "json":
            return res
        if not res["forecast"]:
            raise HTTPException(status_code=404, detail=res["no_forecast_reason"])
        buf = io.StringIO()
        buf.write(f"# EarthSignal temperature FORECAST (statistical; NASA POWER T2M daily mean, {area})\n")
        buf.write(f"# issued from {res['forecast']['origin']} (provisional data: {res['origin_provisional']}); dataset {res['data_version']['dataset_id']}\n")
        buf.write("# low/high = 5th/95th percentile band from 2014-2025 hold-out errors. Official IMD forecasts take precedence.\n")
        pd.DataFrame(res["forecast"]["days"]).to_csv(buf, index=False, lineterminator="\n")
        return PlainTextResponse(buf.getvalue(), media_type="text/csv",
                                 headers={"Content-Disposition": f'attachment; filename="earthsignal_forecast_{area}_{res["forecast"]["origin"]}.csv"'})

    return r
