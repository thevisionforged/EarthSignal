"""Response Intelligence, steps 1 and 2: detect extreme events, then investigate them (DECISIONS D-025).

DETECTION (NASA POWER daily, one grid cell)
  Heat episode  : >= MIN_HEAT_DAYS consecutive days whose daily-mean T2M exceeds that calendar day's
                  95th percentile, computed from the 1991-2020 baseline with a +-7-day window ("unusually
                  hot for the time of year").
  Rainfall event: consecutive days with PRECTOTCORR >= the 99th percentile of baseline WET days
                  (>= 1 mm), pooled over the whole year. A single threshold is used because a seasonal one
                  would call light dry-season rain "extreme".
  Severity      : heat = cumulative exceedance (deg C-days above the threshold); rain = event total (mm).
                  Rank and frequency are relative to THIS record only.
  Provisional   : any event day on or after the first GEOS-IT day (data NASA may still revise).

INVESTIGATION (automatic cross-checks; every source judged against its OWN history)
  other cell : the neighbouring POWER cell also has an event overlapping the dates
  heat       : NOAA airport station (near-hourly days only), days above the station's own
               day-of-year 95th percentile (2005-2024 baseline)
  rain       : GPM IMERG area mean and IMD gauge grid, any day in the event window +-1 day above that
               source's own wet-day 99th percentile. +-1 day allows for different day boundaries.

None of this is a forecast, warning or impact assessment. Events are statistical extremes in reanalysis data.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass

import numpy as np
import pandas as pd

BASELINE = (1991, 2020)
WINDOW_DAYS = 7
HEAT_PCT = 95.0
RAIN_PCT = 99.0
WET_MM = 1.0
MIN_HEAT_DAYS = 3


def doy365(idx: pd.DatetimeIndex) -> np.ndarray:
    """Day of year on a 365-day calendar: Feb 29 shares Feb 28's slot, later leap-year days shift back one."""
    d = idx.dayofyear.to_numpy().copy()
    # In a leap year, Feb 29 (day 60) and every later day shift back by one, so Feb 29 shares Feb 28's slot (59).
    shift = idx.is_leap_year & ((idx.month > 2) | ((idx.month == 2) & (idx.day == 29)))
    d[shift] -= 1
    return d


def doy_percentile(series: pd.Series, pct: float, baseline: tuple[int, int] = BASELINE, window: int = WINDOW_DAYS) -> np.ndarray:
    """Percentile for each of the 365 day-of-year slots, pooling baseline values within +-window days (circular)."""
    s = series[(series.index.year >= baseline[0]) & (series.index.year <= baseline[1])].dropna()
    if s.empty:
        raise ValueError("no baseline data")
    d = doy365(s.index)
    v = s.to_numpy()
    out = np.full(366, np.nan)  # index 1..365 used
    for day in range(1, 366):
        dist = np.abs(d - day)
        dist = np.minimum(dist, 365 - dist)
        sel = v[dist <= window]
        if sel.size:
            out[day] = np.percentile(sel, pct)
    return out


def wet_percentile(series: pd.Series, pct: float, baseline: tuple[int, int] = BASELINE, wet_mm: float = WET_MM) -> float:
    s = series[(series.index.year >= baseline[0]) & (series.index.year <= baseline[1])].dropna()
    wet = s[s >= wet_mm]
    if wet.size < 30:
        raise ValueError("too few baseline wet days for a percentile")
    return float(np.percentile(wet, pct))


def _runs(mask: pd.Series) -> list[tuple[pd.Timestamp, pd.Timestamp]]:
    """Consecutive True runs (a missing day breaks a run; mask must already be False there)."""
    runs, start, prev = [], None, None
    for day, flag in mask.items():
        if flag and start is None:
            start = day
        if not flag and start is not None:
            runs.append((start, prev))
            start = None
        prev = day
    if start is not None:
        runs.append((start, prev))
    return runs


@dataclass
class Event:
    id: str
    kind: str
    area: str
    start: str
    end: str
    days: int
    peak_value: float
    peak_date: str
    threshold_summary: float
    severity: float
    severity_unit: str
    provisional: bool
    rank: int = 0
    n_events: int = 0
    years_with_event_this_severe: int = 0
    n_years: int = 0
    severity_band: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


def detect_heat(t: pd.Series, area: str, pct: float = HEAT_PCT, min_days: int = MIN_HEAT_DAYS,
                baseline: tuple[int, int] = BASELINE, provisional_from: pd.Timestamp | None = None) -> tuple[list[Event], np.ndarray]:
    t = t.asfreq("D")
    thr = doy_percentile(t, pct, baseline)
    th_series = pd.Series(thr[doy365(t.index)], index=t.index)
    excess = t - th_series
    mask = (excess > 0).fillna(False)
    events = []
    for a, b in _runs(mask):
        n = (b - a).days + 1
        if n < min_days:
            continue
        seg, ex = t.loc[a:b], excess.loc[a:b]
        events.append(Event(
            id=f"heat-{area}-{a.date()}", kind="heat", area=area, start=a.date().isoformat(), end=b.date().isoformat(), days=n,
            peak_value=round(float(seg.max()), 2), peak_date=seg.idxmax().date().isoformat(),
            threshold_summary=round(float(th_series.loc[a:b].mean()), 2), severity=round(float(ex.sum()), 2), severity_unit="°C-days",
            provisional=bool(provisional_from is not None and b >= provisional_from)))
    return _rank(events, t.index), thr


def detect_rain(p: pd.Series, area: str, pct: float = RAIN_PCT, baseline: tuple[int, int] = BASELINE,
                provisional_from: pd.Timestamp | None = None) -> tuple[list[Event], float]:
    p = p.asfreq("D")
    thr = wet_percentile(p, pct, baseline)
    mask = (p >= thr).fillna(False)
    events = []
    for a, b in _runs(mask):
        seg = p.loc[a:b]
        events.append(Event(
            id=f"rain-{area}-{a.date()}", kind="rain", area=area, start=a.date().isoformat(), end=b.date().isoformat(),
            days=(b - a).days + 1, peak_value=round(float(seg.max()), 1), peak_date=seg.idxmax().date().isoformat(),
            threshold_summary=round(thr, 1), severity=round(float(seg.sum()), 1), severity_unit="mm",
            provisional=bool(provisional_from is not None and b >= provisional_from)))
    return _rank(events, p.index), thr


def _rank(events: list[Event], idx: pd.DatetimeIndex) -> list[Event]:
    """Rank by severity within the record, and count the years that had an event at least this severe."""
    years_total = len(set(idx.year))
    order = sorted(events, key=lambda e: -e.severity)
    for r, e in enumerate(order, 1):
        e.rank, e.n_events, e.n_years = r, len(events), years_total
        e.years_with_event_this_severe = len({int(x.start[:4]) for x in events if x.severity >= e.severity})
        frac = r / max(len(events), 1)
        e.severity_band = "top 10% of detected events" if frac <= 0.10 else "top 25%" if frac <= 0.25 else "other detected events"
    return sorted(events, key=lambda e: e.start)


def per_year_counts(events: list[Event], years: list[int]) -> dict:
    counts = {y: 0 for y in years}
    for e in events:
        y = int(e.start[:4])
        if y in counts:
            counts[y] += 1
    return {"years": years, "counts": [counts[y] for y in years]}


# ---------------------------------------------------------------- investigation helpers

def overlaps(a: Event, b: Event) -> bool:
    return not (b.end < a.start or b.start > a.end)


def station_heat_check(station: pd.DataFrame | None, start: str, end: str, pct: float = HEAT_PCT, min_obs: int = 20) -> dict:
    """Airport station daily means (near-hourly days only) against the station's own day-of-year percentile."""
    if station is None or station.empty:
        return {"verdict": "no_data", "detail": "No station dataset available."}
    good = station["tmean_c"].where(station["temp_obs"] >= min_obs)
    try:
        thr = doy_percentile(good, pct, (2005, 2024))
    except ValueError:
        return {"verdict": "no_data", "detail": "No station baseline."}
    seg = good.loc[start:end]
    valid = seg.dropna()
    if valid.empty:
        return {"verdict": "no_data", "detail": "The station has no near-hourly observations for these dates."}
    above = valid > thr[doy365(valid.index)]
    share = float(above.mean())
    return {
        "verdict": "corroborated" if share >= 0.5 else "not_corroborated",
        "days_valid": int(valid.size), "days_above": int(above.sum()), "share_above": round(share, 2),
        "station_mean_c": round(float(valid.mean()), 2),
        "detail": f"{int(above.sum())} of {valid.size} station days were above the station's own {pct:.0f}th percentile for the time of year (station days are UTC; POWER days are local solar time).",
    }


def source_rain_check(series: pd.Series | None, name: str, start: str, end: str, baseline: tuple[int, int],
                      pct: float = RAIN_PCT, available_until: str | None = None) -> dict:
    """Did another rainfall source also record a day above ITS OWN wet-day percentile within the window +-1 day?"""
    if series is None or series.dropna().empty:
        return {"source": name, "verdict": "no_data", "detail": f"No {name} data."}
    a = (pd.Timestamp(start) - pd.Timedelta(days=1)).date().isoformat()
    b = (pd.Timestamp(end) + pd.Timedelta(days=1)).date().isoformat()
    if available_until and a > available_until:
        return {"source": name, "verdict": "no_data", "detail": f"{name} is used only up to {available_until}."}
    try:
        thr = wet_percentile(series, pct, baseline)
    except ValueError:
        return {"source": name, "verdict": "no_data", "detail": f"Too little {name} baseline data."}
    seg = series.loc[a:b]
    if available_until:
        seg = seg.loc[:available_until]
    valid = seg.dropna()
    if valid.empty:
        return {"source": name, "verdict": "no_data", "detail": f"No {name} values for these dates."}
    hit = bool((valid >= thr).any())
    return {
        "source": name, "verdict": "corroborated" if hit else "not_corroborated",
        "window": [a, b], "window_total_mm": round(float(valid.sum()), 1), "max_day_mm": round(float(valid.max()), 1),
        "own_threshold_mm": round(thr, 1),
        "detail": f"{name}: wettest day in the window {valid.max():.1f} mm against its own {pct:.0f}th-percentile wet-day threshold of {thr:.1f} mm (baseline {baseline[0]}–{baseline[1]}).",
    }


def plain_summary(e: Event, checks: list[dict], other_cell_match: bool | None) -> str:
    """Rule-based plain-English summary for non-specialists. Built only from the numbers above."""
    cell = "western (airport)" if e.area == "lucknow_airport" else "eastern (city centre)"
    when = e.start if e.days == 1 else f"{e.start} to {e.end}"
    if e.kind == "heat":
        head = (f"A {e.days}-day hot spell ({when}) in the {cell} grid cell: daily-mean temperatures stayed above the usual "
                f"top 5% for that time of year, peaking at {e.peak_value:.1f} °C.")
    else:
        head = (f"An extreme rainfall event ({when}) in the {cell} grid cell: {e.severity:.0f} mm in total, "
                f"in the wettest 1% of rainy days of 1991–2020 (threshold {e.threshold_summary:.0f} mm/day).")
    rank = (f"It ranks {e.rank} of {e.n_events} similar events in the record; events at least this strong occurred "
            f"in {e.years_with_event_this_severe} of {e.n_years} years.")
    # Only checks from a DIFFERENT data source count as independent; the neighbouring POWER cell does not.
    ind = [c for c in checks if c.get("independent")]
    avail = [c for c in ind if c.get("verdict") != "no_data"]
    corr = [c for c in avail if c.get("verdict") == "corroborated"]
    if not avail:
        evidence = "No independent source is available for these dates, so it cannot be cross-checked."
    elif len(corr) == len(avail):
        evidence = ("The one available independent source agrees it was unusual." if len(avail) == 1
                    else f"All {len(avail)} available independent sources agree it was unusual.")
    elif corr:
        evidence = f"{len(corr)} of {len(avail)} available independent sources agree it was unusual; the evidence is mixed."
    else:
        which = "The one available independent source does not" if len(avail) == 1 else f"None of the {len(avail)} available independent sources"
        evidence = f"{which} confirm it, so it may be an artifact of the reanalysis data. Treat it with caution."
    other = "" if other_cell_match is None else (" The neighbouring grid cell shows the same event." if other_cell_match else " The neighbouring grid cell does not.")
    prov = " Some of these days are provisional: NASA may still revise them." if e.provisional else ""
    return f"{head} {rank} {evidence}{other}{prov}"
