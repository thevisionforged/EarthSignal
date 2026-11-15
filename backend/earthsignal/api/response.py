"""Response Intelligence API: detect -> investigate -> respond (DECISIONS D-025).

GET  /api/response/events        detected heat episodes or rainfall events for one grid cell
GET  /api/response/investigate   automatic cross-checks and a plain-English summary for one event
GET  /api/cases                  list analyst cases
POST /api/cases                  open a case from an event (the SERVER recomputes the event and evidence)
POST /api/cases/{id}/status      move a case through the workflow (decisions need a reason)
POST /api/cases/{id}/notes       add a note
GET  /api/cases/{id}/brief       Markdown evidence brief (download)
"""

from __future__ import annotations

from pathlib import Path
from typing import Literal

import pandas as pd
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel, Field

from earthsignal.analysis import events as ev
from earthsignal.cases import STATUS_HELP, TRANSITIONS, CaseError, CaseStore, brief_markdown
from earthsignal.config import DEFAULT_AREA, STUDY_AREAS
from earthsignal.data import gsod, imd, imerg_power, store

Kind = Literal["heat", "rain"]
OTHER = {"lucknow": "lucknow_airport", "lucknow_airport": "lucknow"}
PUBLIC_DEMO_NOTE = ("Public demo: cases here are visible to every visitor and are cleared whenever the server restarts. "
                    "Do not enter personal information.")

EXPLAIN = {
    "heat": ("A heat episode is 3 or more days in a row that were hotter than 95% of days at the same time of year in "
             "1991–2020. The comparison is with the same season, so a hot March can count, not just May."),
    "rain": ("An extreme rainfall event is one or more consecutive days with rain in the top 1% of all rainy days "
             "(1 mm or more) in 1991–2020. One threshold is used for the whole year."),
}
METHOD = {
    "heat": [
        "Data: NASA POWER daily-mean 2 m temperature (MERRA-2/GEOS-IT reanalysis) for one ~55 × 62 km grid cell.",
        "Threshold: 95th percentile for each calendar day, from 1991–2020, pooling ±7 days around that date.",
        "Episode: at least 3 consecutive days above that day's threshold; a missing day ends an episode.",
        "Severity: sum of the daily excess above the threshold (°C-days). Rank and frequency are within this record only.",
    ],
    "rain": [
        "Data: NASA POWER daily precipitation PRECTOTCORR (MERRA-2 bias-corrected reanalysis) for one grid cell.",
        "Threshold: 99th percentile of wet days (≥ 1 mm) in 1991–2020, the same all year.",
        "Event: consecutive days at or above the threshold. Severity: event total (mm). Rank is within this record only.",
        "Caution: POWER rainfall drifts from IMD rain gauges after 2006 in the western cell (Milestone 4).",
    ],
}


class CaseCreate(BaseModel):
    area: str
    kind: Kind
    event_id: str = Field(max_length=80)
    title: str | None = Field(default=None, max_length=120)


class StatusChange(BaseModel):
    to: str
    note: str = Field(default="", max_length=2000)


class NoteIn(BaseModel):
    text: str = Field(max_length=2000)


def build_router(processed_root: Path, cases_path: Path, public_demo: bool = False) -> APIRouter:
    r = APIRouter(tags=["response"])
    cases = CaseStore(cases_path)
    cache: dict[tuple, tuple] = {}

    def load(area: str) -> store.Dataset:
        if area not in STUDY_AREAS:
            raise HTTPException(status_code=422, detail=f"unknown area {area!r}")
        try:
            return store.load_dataset(processed_root, area=area)
        except store.NoDatasetError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    def provisional_from(ds: store.Dataset) -> pd.Timestamp | None:
        sp = store.load_source_periods(processed_root, ds.dataset_id)
        if sp and sp.get("first_geosit_day"):
            return pd.Timestamp(sp["first_geosit_day"])
        last = ds.frame.dropna().index.max()
        return last - pd.Timedelta(days=60)  # conservative fallback: the last ~2 months may be revised

    def detect(area: str, kind: str) -> tuple[store.Dataset, list[ev.Event], object]:
        ds = load(area)
        key = (area, kind, ds.dataset_id)
        if key not in cache:
            pf = provisional_from(ds)
            if kind == "heat":
                found, thr = ev.detect_heat(ds.frame["T2M"], area, provisional_from=pf)
            else:
                found, thr = ev.detect_rain(ds.frame["PRECTOTCORR"], area, provisional_from=pf)
            cache[key] = (found, thr, pf)
        found, thr, _ = cache[key]
        return ds, found, thr

    def find(area: str, kind: str, event_id: str) -> tuple[store.Dataset, ev.Event, object]:
        ds, found, thr = detect(area, kind)
        e = next((x for x in found if x.id == event_id), None)
        if e is None:
            raise HTTPException(status_code=404, detail=f"event {event_id!r} not found for {area}/{kind}")
        return ds, e, thr

    def data_version(ds: store.Dataset) -> dict:
        return {"dataset_id": ds.dataset_id, "retrieved_at_utc": ds.provenance["retrieved_at_utc"],
                "api_version": ds.provenance["api_version"], "time_standard": ds.provenance["time_standard"]}

    def investigate_event(area: str, kind: str, event_id: str) -> dict:
        ds, e, thr = find(area, kind, event_id)
        col = "T2M" if kind == "heat" else "PRECTOTCORR"
        a = pd.Timestamp(e.start) - pd.Timedelta(days=14)
        b = pd.Timestamp(e.end) + pd.Timedelta(days=14)
        win = ds.frame[col].loc[a:b]
        if kind == "heat":
            th = [round(float(thr[d]), 2) for d in ev.doy365(win.index)]
        else:
            th = [float(thr)] * len(win)
        _, other_events, _ = detect(OTHER[area], kind)
        other_match = any(ev.overlaps(e, o) for o in other_events)
        checks = [{"label": "Neighbouring grid cell (same NASA POWER data, not independent)", "source": "NASA POWER (other cell)", "independent": False,
                   "verdict": "corroborated" if other_match else "not_corroborated",
                   "detail": "The other Lucknow cell has an overlapping event." if other_match else "The other Lucknow cell has no overlapping event."}]
        data = [f"NASA POWER {ds.dataset_id} (retrieved {ds.provenance['retrieved_at_utc'][:10]}, API {ds.provenance['api_version']})"]
        if kind == "heat":
            st = gsod.latest(processed_root)
            c = ev.station_heat_check(st[0] if st else None, e.start, e.end)
            if area != "lucknow_airport" and "detail" in c:
                c["detail"] += " The station lies in the western cell, just outside this one, so this is a nearby check rather than a same-cell one."
            checks.append({"label": "Airport weather station (NOAA GSOD)", "source": "station", "independent": True, **c})
            if st:
                data.append(f"NOAA GSOD {st[1]['dataset_id']} (station observations; non-commercial use, WMO Resolution 40)")
        else:
            im = imerg_power.latest(processed_root, area)
            checks.append({"label": "Satellite rainfall (NASA GPM IMERG)", "independent": True, **ev.source_rain_check(
                im[0]["imerg_area_mean_mm_day"] if im else None, "IMERG", e.start, e.end, (2001, 2020),
                available_until=imerg_power.FINAL_RUN_END.isoformat())})
            gd = imd.latest(processed_root)
            checks.append({"label": "Rain gauges (IMD gridded)", "independent": True, **ev.source_rain_check(
                gd[0][f"imd_{area}_mm_day"] if gd else None, "IMD", e.start, e.end, (1998, 2024),
                available_until=gd[0].index.max().date().isoformat() if gd else None)})
            if im:
                data.append(f"GPM IMERG via POWER {im[1]['dataset_id']}")
            if gd:
                data.append(f"IMD gridded rainfall {gd[1]['dataset_id']} (Pai et al. 2014)")
        ind = [c for c in checks if c["independent"]]
        n_corr = sum(c["verdict"] == "corroborated" for c in ind)
        n_avail = sum(c["verdict"] != "no_data" for c in ind)
        return {
            "event": e.to_dict(),
            "summary": ev.plain_summary(e, checks, other_match),
            "checks": checks,
            "corroboration": {"independent_corroborated": n_corr, "independent_available": n_avail, "independent_total": len(ind),
                              "other_cell_agrees": other_match},
            "window": {"dates": [d.date().isoformat() for d in win.index], "values": [None if pd.isna(v) else round(float(v), 2) for v in win],
                       "threshold": th, "units": "°C (daily mean)" if kind == "heat" else "mm/day"},
            "method": METHOD[kind],
            "data": data,
            "data_version": data_version(ds),
            "explain": EXPLAIN[kind],
        }

    @r.get("/api/response/events")
    def events(area: str = DEFAULT_AREA, kind: Kind = "heat", start_year: int = Query(1981, ge=1981, le=2100),
               end_year: int = Query(2100, ge=1981, le=2100)) -> dict:
        ds, found, thr = detect(area, kind)
        sel = [e for e in found if start_year <= int(e.start[:4]) <= end_year]
        years = sorted(set(ds.frame.dropna().index.year))
        years = [y for y in years if start_year <= y <= end_year]
        return {
            "area": area, "kind": kind, "events": [e.to_dict() for e in sel],
            "per_year": ev.per_year_counts(sel, years),
            "threshold": ({"kind": "day_of_year", "values": [round(float(x), 2) for x in thr[1:366]], "units": "°C"} if kind == "heat"
                          else {"kind": "constant", "value": round(float(thr), 1), "units": "mm/day"}),
            "explain": EXPLAIN[kind], "method": METHOD[kind], "data_version": data_version(ds),
            "data_kind": "derived_statistic",
            "note": "Detected statistical extremes in historical reanalysis data. Not forecasts, warnings or impact assessments.",
        }

    @r.get("/api/response/investigate")
    def investigate(area: str = DEFAULT_AREA, kind: Kind = "heat", event_id: str = Query(..., max_length=80)) -> dict:
        return investigate_event(area, kind, event_id)

    @r.get("/api/cases")
    def list_cases() -> dict:
        return {"cases": cases.list(), "statuses": STATUS_HELP, "transitions": {k: sorted(v) for k, v in TRANSITIONS.items()},
                "storage_note": PUBLIC_DEMO_NOTE if public_demo else None}

    @r.post("/api/cases")
    def create_case(body: CaseCreate) -> dict:
        evidence = investigate_event(body.area, body.kind, body.event_id)  # recomputed server-side, never trusted from the client
        return cases.create(evidence["event"], evidence, body.title)

    @r.post("/api/cases/{case_id}/status")
    def change_status(case_id: str, body: StatusChange) -> dict:
        try:
            return cases.transition(case_id, body.to, body.note)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=f"case {case_id} not found") from exc
        except CaseError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @r.post("/api/cases/{case_id}/notes")
    def add_note(case_id: str, body: NoteIn) -> dict:
        try:
            return cases.add_note(case_id, body.text)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=f"case {case_id} not found") from exc
        except CaseError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @r.get("/api/cases/{case_id}/brief", response_class=PlainTextResponse)
    def brief(case_id: str) -> PlainTextResponse:
        try:
            case = cases.get(case_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=f"case {case_id} not found") from exc
        return PlainTextResponse(brief_markdown(case), media_type="text/markdown",
                                 headers={"Content-Disposition": f'attachment; filename="{case_id}_brief.md"'})

    return r
