"""Simulation Studio API (`/api/sim/*`). Six tools, one shared calculation module (analysis/simulation.py).

Every response carries: the inputs as interpreted, the exact data version (dataset id and retrieval time), the
method and formulas, the limitations, and `data_kind`. Each tool also returns its main table as CSV with
`format=csv`. Calculations are deterministic given the inputs and the data version; the uncertainty tool also
records its random seed.
"""

from __future__ import annotations

import io
from pathlib import Path
from typing import Literal

import pandas as pd
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import PlainTextResponse

from earthsignal.analysis import simulation as sim
from earthsignal.config import DEFAULT_AREA, STUDY_AREAS
from earthsignal.data import store

COMMON_LIMITATIONS = [
    "Input is NASA POWER reanalysis for one ~55 x 62 km MERRA-2 grid cell: a model-based estimate, not station observations.",
    "Temperature is the DAILY MEAN 2 m air temperature (T2M). Daily maxima are not in this dataset, so threshold counts refer to daily means.",
    "Scenario results apply one uniform change to every historical day. They are hypothetical what-ifs, not projections, forecasts, or impact predictions (no health, flood, crop or economic outcomes).",
    "POWER precipitation drifts from IMD rain gauges after 2006 in the western cell (Milestone 4), so absolute rainfall levels carry that uncertainty.",
    "Missing days are excluded from every count and total, never treated as zero.",
]
FORMULAS = {
    "temperature": "scenario_T2M = historical_T2M + temperature_offset (deg C)",
    "precipitation": "scenario_PRECTOTCORR = historical_PRECTOTCORR x precipitation_multiplier (mm/day)",
    "exceedance_day": "a valid day with daily-mean T2M > threshold",
    "wet_day": "a valid day with precipitation >= wet-day threshold",
    "high_rain_day": "a valid day with precipitation >= high-rainfall threshold",
}

Area = str
Fmt = Literal["json", "csv"]


def build_router(processed_root: Path) -> APIRouter:
    r = APIRouter(prefix="/api/sim", tags=["simulation"])
    cache: dict[str, store.Dataset] = {}

    def load(area: str) -> store.Dataset:
        if area not in STUDY_AREAS:
            raise HTTPException(status_code=422, detail=f"unknown area {area!r}; choose from {sorted(STUDY_AREAS)}")
        try:
            ds = store.load_dataset(processed_root, area=area)
        except store.NoDatasetError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        key = f"{area}:{ds.dataset_id}"
        cache.setdefault(key, ds)
        return cache[key]

    def years_for(ds: store.Dataset, start: int, end: int) -> tuple[pd.DataFrame, list[int]]:
        try:
            sub = sim.period_frame(ds.frame, start, end)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        yrs = sim.complete_years(sub)
        if not yrs:
            raise HTTPException(status_code=422, detail=f"no complete years in {start}-{end}")
        # Every tool works on complete years only, so all six agree on the same days.
        return sub[sub.index.year.isin(yrs)], yrs

    def scen(t: float, p: float) -> sim.Scenario:
        try:
            return sim.Scenario(t, p).validate()
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    def thr(t: float, w: float, h: float) -> sim.Thresholds:
        try:
            return sim.Thresholds(t, w, h).validate()
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    def envelope(ds: store.Dataset, area: str, start: int, end: int, years: list[int], inputs: dict, kind: str) -> dict:
        excluded = [y for y in range(start, end + 1) if y not in years]
        return {
            "inputs": {"area": area, "start_year": start, "end_year": end, **inputs},
            "data_version": {"dataset_id": ds.dataset_id, "retrieved_at_utc": ds.provenance["retrieved_at_utc"],
                             "api_version": ds.provenance["api_version"], "time_standard": ds.provenance["time_standard"],
                             "provider": "NASA LaRC POWER (MERRA-2 / GEOS-IT reanalysis)"},
            "years_used": years,
            "years_excluded": excluded,
            "data_kind": kind,
            "formulas": FORMULAS,
            "limitations": COMMON_LIMITATIONS,
        }

    def csv_response(table: pd.DataFrame, header: dict, name: str) -> PlainTextResponse:
        lines = [f"# EarthSignal Simulation Studio: {name}",
                 f"# data_kind: {header['data_kind']} (hypothetical rows are the historical record with a uniform change applied)",
                 f"# inputs: {header['inputs']}",
                 f"# data version: {header['data_version']['dataset_id']} retrieved {header['data_version']['retrieved_at_utc']}",
                 "# source: NASA LaRC POWER daily T2M (daily mean, deg C) and PRECTOTCORR (mm/day), reanalysis, not station data"]
        buf = io.StringIO()
        table.to_csv(buf, index=False, float_format="%.4f")
        return PlainTextResponse("\n".join(lines) + "\n" + buf.getvalue(), media_type="text/csv",
                                 headers={"Content-Disposition": f'attachment; filename="earthsignal_{name}.csv"'})

    @r.get("/meta")
    def meta(area: Area = DEFAULT_AREA) -> dict:
        ds = load(area)
        yrs = sim.complete_years(ds.frame)
        return {
            "areas": [{"key": k, "label": a.label} for k, a in STUDY_AREAS.items()],
            "complete_years": [min(yrs), max(yrs)],
            "default_period": [max(min(yrs), 1991), min(max(yrs), 2020)],
            "ranges": {"temp_offset_c": sim.T_OFFSET_RANGE, "precip_multiplier": sim.P_MULT_RANGE},
            "defaults": {"temp_threshold_c": sim.DEFAULT_TEMP_THRESHOLD, "wet_threshold_mm": sim.DEFAULT_WET_THRESHOLD,
                         "heavy_threshold_mm": sim.DEFAULT_HEAVY_THRESHOLD},
            "presets": sim.PRESETS,
            "formulas": FORMULAS,
            "limitations": COMMON_LIMITATIONS,
            "dataset_id": ds.dataset_id,
        }

    # ---------------- Tool 1: scenario builder
    @r.get("/scenario")
    def scenario(area: Area = DEFAULT_AREA, start_year: int = 1991, end_year: int = 2020,
                 temp_offset_c: float = Query(0.0), precip_multiplier: float = Query(1.0),
                 name: str = Query("Custom", max_length=60), format: Fmt = "json"):
        ds = load(area)
        sub, yrs = years_for(ds, start_year, end_year)
        s = scen(temp_offset_c, precip_multiplier)
        th = sim.Thresholds()
        base, sc = sub, sim.apply_scenario(sub, s)
        mb, ms = sim.monthly_series(base), sim.monthly_series(sc)
        head = envelope(ds, area, start_year, end_year, yrs,
                        {"temp_offset_c": s.temp_offset_c, "precip_multiplier": s.precip_multiplier, "name": name}, "hypothetical")
        if format == "csv":
            t = pd.DataFrame({"month": mb.index.strftime("%Y-%m"), "baseline_mean_temp_c": mb["mean_temp_c"],
                              "scenario_mean_temp_c": ms["mean_temp_c"], "baseline_total_precip_mm": mb["total_precip_mm"],
                              "scenario_total_precip_mm": ms["total_precip_mm"]})
            return csv_response(t, head, f"scenario_{area}")
        return {**head,
                "summary": sim.compare(sim.metrics(base, th), sim.metrics(sc, th)),
                "monthly": {"months": list(mb.index.strftime("%Y-%m")),
                            "baseline_temp": _clean(mb["mean_temp_c"]), "scenario_temp": _clean(ms["mean_temp_c"]),
                            "baseline_precip": _clean(mb["total_precip_mm"]), "scenario_precip": _clean(ms["total_precip_mm"])},
                "climatology": {"baseline": sim.monthly_climatology(base, th), "scenario": sim.monthly_climatology(sc, th)}}

    # ---------------- Tool 2: heat stress explorer
    @r.get("/heat")
    def heat(area: Area = DEFAULT_AREA, start_year: int = 1991, end_year: int = 2020, temp_offset_c: float = 0.0,
             threshold_c: float = sim.DEFAULT_TEMP_THRESHOLD, format: Fmt = "json"):
        ds = load(area)
        sub, yrs = years_for(ds, start_year, end_year)
        s, th = scen(temp_offset_c, 1.0), thr(threshold_c, sim.DEFAULT_WET_THRESHOLD, sim.DEFAULT_HEAVY_THRESHOLD)
        sc = sim.apply_scenario(sub, s)
        ab, as_ = sim.annual_series(sub, th, yrs), sim.annual_series(sc, th, yrs)
        head = envelope(ds, area, start_year, end_year, yrs, {"temp_offset_c": s.temp_offset_c, "threshold_c": th.temp_c}, "hypothetical")
        if format == "csv":
            t = pd.DataFrame({"year": ab.index, "baseline_exceedance_days": ab["exceedance_days"].values,
                              "scenario_exceedance_days": as_["exceedance_days"].values,
                              "baseline_mean_temp_c": ab["mean_temp_c"].values, "scenario_mean_temp_c": as_["mean_temp_c"].values})
            return csv_response(t, head, f"heat_{area}")
        mb, msc = sim.metrics(sub[sub.index.year.isin(yrs)], th), sim.metrics(sc[sc.index.year.isin(yrs)], th)
        return {**head,
                "summary": sim.compare(mb, msc),
                "per_year": {"years": yrs, "baseline": ab["exceedance_days"].tolist(), "scenario": as_["exceedance_days"].tolist()},
                "monthly": {"baseline": sim.monthly_climatology(sub, th), "scenario": sim.monthly_climatology(sc, th)},
                "hottest_days": sim.hottest_days(sub), "hottest_months": sim.hottest_months(sub),
                "label_note": "Counts of days whose daily-mean temperature exceeds the threshold. Not a heat-illness, mortality or health-risk indicator."}

    # ---------------- Tool 3: rainfall stress simulator
    @r.get("/rain")
    def rain(area: Area = DEFAULT_AREA, start_year: int = 1991, end_year: int = 2020, precip_multiplier: float = 1.0,
             wet_threshold_mm: float = sim.DEFAULT_WET_THRESHOLD, heavy_threshold_mm: float = sim.DEFAULT_HEAVY_THRESHOLD,
             format: Fmt = "json"):
        ds = load(area)
        sub, yrs = years_for(ds, start_year, end_year)
        s, th = scen(0.0, precip_multiplier), thr(sim.DEFAULT_TEMP_THRESHOLD, wet_threshold_mm, heavy_threshold_mm)
        sc = sim.apply_scenario(sub, s)
        ab, as_ = sim.annual_series(sub, th, yrs), sim.annual_series(sc, th, yrs)
        head = envelope(ds, area, start_year, end_year, yrs, {"precip_multiplier": s.precip_multiplier,
                        "wet_threshold_mm": th.wet_mm, "heavy_threshold_mm": th.heavy_mm}, "hypothetical")
        if format == "csv":
            t = pd.DataFrame({"year": ab.index, "baseline_total_precip_mm": ab["total_precip_mm"].values,
                              "scenario_total_precip_mm": as_["total_precip_mm"].values, "baseline_wet_days": ab["wet_days"].values,
                              "scenario_wet_days": as_["wet_days"].values, "baseline_high_rain_days": ab["high_rain_days"].values,
                              "scenario_high_rain_days": as_["high_rain_days"].values})
            return csv_response(t, head, f"rain_{area}")
        return {**head,
                "summary": sim.compare(sim.metrics(sub, th), sim.metrics(sc, th)),
                "per_year": {"years": yrs, "baseline_total": ab["total_precip_mm"].tolist(), "scenario_total": as_["total_precip_mm"].tolist(),
                             "baseline_high": ab["high_rain_days"].tolist(), "scenario_high": as_["high_rain_days"].tolist()},
                "monthly": {"baseline": sim.monthly_climatology(sub, th), "scenario": sim.monthly_climatology(sc, th)},
                "seasonal": {"baseline": sim.seasonal_totals(sub, th), "scenario": sim.seasonal_totals(sc, th)},
                "label_note": "Rainfall amounts and day counts only. Not a flood, drainage or inundation prediction."}

    # ---------------- Tool 4: compound climate experiment
    @r.get("/compound")
    def compound(area: Area = DEFAULT_AREA, start_year: int = 1991, end_year: int = 2020,
                 t_min: float = -1.0, t_max: float = 3.0, t_step: float = 1.0,
                 p_min: float = 0.6, p_max: float = 1.4, p_step: float = 0.2,
                 threshold_c: float = sim.DEFAULT_TEMP_THRESHOLD, wet_threshold_mm: float = sim.DEFAULT_WET_THRESHOLD,
                 heavy_threshold_mm: float = sim.DEFAULT_HEAVY_THRESHOLD, format: Fmt = "json"):
        ds = load(area)
        sub, yrs = years_for(ds, start_year, end_year)
        th = thr(threshold_c, wet_threshold_mm, heavy_threshold_mm)
        offsets, mults = _grid(t_min, t_max, t_step, *sim.T_OFFSET_RANGE), _grid(p_min, p_max, p_step, *sim.P_MULT_RANGE)
        try:
            cells = sim.compound_matrix(sub[sub.index.year.isin(yrs)], offsets, mults, th)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        n = len(yrs)
        for c in cells:  # per-year values make periods of different length comparable
            c["exceedance_days_per_year"] = round(c["temp_exceedance_days"] / n, 3)
            c["precip_mm_per_year"] = round((c["total_precip_mm"] or 0) / n, 2)
            c["wet_days_per_year"] = round(c["wet_days"] / n, 3)
            c["high_rain_days_per_year"] = round(c["high_rain_days"] / n, 3)
        head = envelope(ds, area, start_year, end_year, yrs, {"temp_offsets_c": offsets, "precip_multipliers": mults,
                        "threshold_c": th.temp_c, "wet_threshold_mm": th.wet_mm, "heavy_threshold_mm": th.heavy_mm}, "hypothetical")
        if format == "csv":
            return csv_response(pd.DataFrame(cells), head, f"compound_{area}")
        return {**head, "offsets": offsets, "multipliers": mults, "cells": cells,
                "label_note": "Each cell applies both assumptions to the same historical days. Combined cells show joint assumptions, not a causal link between temperature and rainfall."}

    # ---------------- Tool 5: historical analog finder
    @r.get("/analogs")
    def analogs(area: Area = DEFAULT_AREA, start_year: int = 1981, end_year: int = 2025, temp_offset_c: float = 0.0,
                precip_multiplier: float = 1.0, unit: str = "annual", n: int = Query(5, ge=1, le=15),
                temp_weight: float = Query(1.0, ge=0, le=5), precip_weight: float = Query(1.0, ge=0, le=5), format: Fmt = "json"):
        ds = load(area)
        sub, yrs = years_for(ds, start_year, end_year)
        s = scen(temp_offset_c, precip_multiplier)
        if temp_weight == 0 and precip_weight == 0:
            raise HTTPException(status_code=422, detail="at least one weight must be positive")
        try:
            feats = sim.analog_features(sub, unit, yrs)
            res = sim.find_analogs(feats, s, (temp_weight, precip_weight), n)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        head = envelope(ds, area, start_year, end_year, yrs, {"temp_offset_c": s.temp_offset_c, "precip_multiplier": s.precip_multiplier,
                        "unit": unit, "n": n, "weights": [temp_weight, precip_weight]}, "derived_statistic")
        excluded = {str(k): v for k, v in feats.attrs.get("excluded", {}).items()}
        if format == "csv":
            return csv_response(pd.DataFrame(res["all_years"]).sort_values("distance_z"), head, f"analogs_{area}")
        return {**head, **res, "excluded_year_units": excluded,
                "method": "Features per year: mean T2M (deg C) and total PRECTOTCORR (mm) over the chosen unit. Standardised by the "
                          "across-year standard deviation; weighted Euclidean distance to the scenario target; similarity = 1/(1+d).",
                "label_note": "Historical analogues are past years that resemble the assumptions. They are not forecasts or predicted future years."}

    # ---------------- Tool 6: uncertainty & sensitivity lab
    @r.get("/uncertainty")
    def uncertainty(area: Area = DEFAULT_AREA, start_year: int = 1991, end_year: int = 2020, temp_offset_c: float = 0.0,
                    precip_multiplier: float = 1.0, threshold_c: float = sim.DEFAULT_TEMP_THRESHOLD,
                    wet_threshold_mm: float = sim.DEFAULT_WET_THRESHOLD, heavy_threshold_mm: float = sim.DEFAULT_HEAVY_THRESHOLD,
                    n_boot: int = Query(1000, ge=10, le=5000), seed: int = Query(20261115, ge=0, le=2**31 - 1), format: Fmt = "json"):
        ds = load(area)
        sub, yrs = years_for(ds, start_year, end_year)
        s, th = scen(temp_offset_c, precip_multiplier), thr(threshold_c, wet_threshold_mm, heavy_threshold_mm)
        try:
            boot_b = sim.year_bootstrap(sim.annual_series(sub, th, yrs), n_boot, seed)
            boot_s = sim.year_bootstrap(sim.annual_series(sim.apply_scenario(sub, s), th, yrs), n_boot, seed)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        sweep = sim.sensitivity_sweep(sub, th, yrs, [-3, -2, -1, 0, 1, 2, 3, 4, 5], [0.0, 0.25, 0.5, 0.75, 1.0, 1.25, 1.5, 1.75, 2.0])
        head = envelope(ds, area, start_year, end_year, yrs, {"temp_offset_c": s.temp_offset_c, "precip_multiplier": s.precip_multiplier,
                        "threshold_c": th.temp_c, "wet_threshold_mm": th.wet_mm, "heavy_threshold_mm": th.heavy_mm,
                        "n_boot": n_boot, "seed": seed}, "derived_statistic")
        if format == "csv":
            rows = [{"metric": k, "series": lab, "median": b[k]["median"], "p05": b[k]["p05"], "p95": b[k]["p95"], "observed_mean": b[k]["observed_mean"]}
                    for lab, b in (("baseline", boot_b), ("scenario", boot_s)) for k in sim.BOOT_METRICS]
            return csv_response(pd.DataFrame(rows), head, f"uncertainty_{area}")
        return {**head, "baseline": boot_b, "scenario": boot_s, "sensitivity": sweep,
                "method": "Year-level bootstrap: complete calendar years are resampled with replacement (block = one year), and each "
                          "replicate is the mean of the resampled years. The same seed and inputs give identical results.",
                "label_note": "Empirical spread of historical year-to-year variability. Not a calibrated prediction interval, "
                              "and not a probability of any future climate outcome."}

    return r


def _grid(lo: float, hi: float, step: float, lo_lim: float, hi_lim: float) -> list[float]:
    if step <= 0 or hi < lo or lo < lo_lim or hi > hi_lim:
        raise HTTPException(status_code=422, detail=f"grid must satisfy {lo_lim} <= min <= max <= {hi_lim}, step > 0")
    n = int(round((hi - lo) / step)) + 1
    if n > 11:
        raise HTTPException(status_code=422, detail="at most 11 values per axis")
    return [round(lo + i * step, 4) for i in range(n)]


def _clean(s: pd.Series) -> list[float | None]:
    return [None if pd.isna(v) else round(float(v), 3) for v in s]
