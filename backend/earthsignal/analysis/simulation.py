"""Simulation Studio: hypothetical what-if transformations of the historical NASA POWER record.

Every tool in the studio is built from the SAME few functions here (DECISIONS D-024):

  apply_scenario   scenario_T = T + offset;  scenario_P = P * multiplier   (NaN stays NaN)
  period_frame     the historical daily record restricted to whole calendar years [start, end]
  metrics          counts and totals over VALID days only, with the number of valid/missing days
  monthly / seasonal / annual aggregations

Inputs are NASA POWER daily T2M (daily MEAN 2 m air temperature, deg C, reanalysis) and PRECTOTCORR
(MERRA-2 bias-corrected precipitation, mm/day, reanalysis) for one MERRA-2 grid cell. They are model-based
estimates, not station observations. Outputs of a transformation are HYPOTHETICAL: "the historical record
with a uniform change applied". They are not projections, forecasts or impact predictions.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass

import numpy as np
import pandas as pd

from earthsignal.analysis.seasonal import SEASONS, SEASON_LABELS

T_OFFSET_RANGE = (-3.0, 5.0)  # deg C
P_MULT_RANGE = (0.0, 2.0)  # 0 % .. 200 %
DEFAULT_TEMP_THRESHOLD = 35.0  # deg C, daily-mean temperature; user-adjustable
DEFAULT_WET_THRESHOLD = 1.0  # mm/day: a day with >= 1 mm counts as "wet" (documented choice, user-adjustable)
DEFAULT_HEAVY_THRESHOLD = 50.0  # mm/day: "high-rainfall day" (user-chosen level, not an official hazard class)
MIN_YEAR_COVERAGE = 0.95


@dataclass(frozen=True)
class Scenario:
    temp_offset_c: float = 0.0
    precip_multiplier: float = 1.0

    def validate(self) -> "Scenario":
        lo, hi = T_OFFSET_RANGE
        if not lo <= self.temp_offset_c <= hi:
            raise ValueError(f"temperature offset must be within {lo}..{hi} C")
        lo, hi = P_MULT_RANGE
        if not lo <= self.precip_multiplier <= hi:
            raise ValueError(f"precipitation multiplier must be within {lo}..{hi}")
        return self


@dataclass(frozen=True)
class Thresholds:
    temp_c: float = DEFAULT_TEMP_THRESHOLD
    wet_mm: float = DEFAULT_WET_THRESHOLD
    heavy_mm: float = DEFAULT_HEAVY_THRESHOLD

    def validate(self) -> "Thresholds":
        if not -10 <= self.temp_c <= 50:
            raise ValueError("temperature threshold must be within -10..50 C")
        if not 0 < self.wet_mm <= 50:
            raise ValueError("wet-day threshold must be within (0, 50] mm/day")
        if not self.wet_mm <= self.heavy_mm <= 500:
            raise ValueError("high-rainfall threshold must be >= wet-day threshold and <= 500 mm/day")
        return self


PRESETS: dict[str, dict] = {
    "historical": {"label": "Historical baseline", "temp_offset_c": 0.0, "precip_multiplier": 1.0},
    "warmer": {"label": "Warmer conditions", "temp_offset_c": 2.0, "precip_multiplier": 1.0},
    "drier": {"label": "Drier conditions", "temp_offset_c": 0.0, "precip_multiplier": 0.7},
    "wetter": {"label": "Wetter conditions", "temp_offset_c": 0.0, "precip_multiplier": 1.3},
    "combined": {"label": "Combined stress", "temp_offset_c": 2.0, "precip_multiplier": 0.7},
}


# ---------------------------------------------------------------- core transformations

def apply_scenario(frame: pd.DataFrame, s: Scenario) -> pd.DataFrame:
    """Uniform change applied to every day. Missing values stay missing (NaN + x = NaN)."""
    s.validate()
    out = frame[["T2M", "PRECTOTCORR"]].copy()
    out["T2M"] = out["T2M"] + s.temp_offset_c
    out["PRECTOTCORR"] = out["PRECTOTCORR"] * s.precip_multiplier
    return out


def period_frame(frame: pd.DataFrame, start_year: int, end_year: int) -> pd.DataFrame:
    """Whole calendar years only. Raises if the period is empty or reversed."""
    if end_year < start_year:
        raise ValueError("end year precedes start year")
    sub = frame.loc[f"{start_year}-01-01":f"{end_year}-12-31", ["T2M", "PRECTOTCORR"]]
    if sub.empty:
        raise ValueError(f"no data for {start_year}-{end_year}")
    return sub


def complete_years(frame: pd.DataFrame, min_coverage: float = MIN_YEAR_COVERAGE) -> list[int]:
    """Years in which BOTH variables have at least `min_coverage` of days valid (and the year is whole)."""
    years = []
    for y, g in frame.groupby(frame.index.year):
        n_days = 366 if pd.Timestamp(year=y, month=12, day=31).is_leap_year else 365
        if len(g) == n_days and (g.notna().sum() / n_days).min() >= min_coverage:
            years.append(int(y))
    return years


@dataclass
class Metrics:
    n_days: int
    n_valid_t: int
    n_valid_p: int
    mean_temp_c: float | None
    max_temp_c: float | None
    temp_exceedance_days: int
    total_precip_mm: float | None
    mean_daily_precip_mm: float | None
    max_daily_precip_mm: float | None
    wet_days: int
    high_rain_days: int

    def to_dict(self) -> dict:
        return asdict(self)


def _f(x) -> float | None:
    return None if x is None or (isinstance(x, float) and np.isnan(x)) else round(float(x), 4)


def metrics(frame: pd.DataFrame, th: Thresholds) -> Metrics:
    """Statistics over VALID days only. Counts never treat a missing day as dry or as cool."""
    th.validate()
    t, p = frame["T2M"], frame["PRECTOTCORR"]
    tv, pv = t.dropna(), p.dropna()
    return Metrics(
        n_days=int(len(frame)),
        n_valid_t=int(tv.size),
        n_valid_p=int(pv.size),
        mean_temp_c=_f(tv.mean()) if tv.size else None,
        max_temp_c=_f(tv.max()) if tv.size else None,
        temp_exceedance_days=int((tv > th.temp_c).sum()),
        total_precip_mm=_f(pv.sum()) if pv.size else None,
        mean_daily_precip_mm=_f(pv.mean()) if pv.size else None,
        max_daily_precip_mm=_f(pv.max()) if pv.size else None,
        wet_days=int((pv >= th.wet_mm).sum()),
        high_rain_days=int((pv >= th.heavy_mm).sum()),
    )


def compare(base: Metrics, scen: Metrics) -> dict:
    """Absolute and (where meaningful) percentage differences, scenario minus baseline."""
    out = {}
    for k, b in base.to_dict().items():
        s = getattr(scen, k)
        if k.startswith("n_") or b is None or s is None:
            continue
        diff = s - b
        pct = None
        # Percent change is meaningful for ratio-scale amounts and counts with a non-zero base,
        # NOT for temperatures in deg C (an interval scale with an arbitrary zero).
        if not k.endswith("_c") and b != 0:
            pct = round(100.0 * diff / b, 2)
        out[k] = {"baseline": b, "scenario": s, "difference": round(float(diff), 4), "percent": pct}
    return out


# ---------------------------------------------------------------- aggregations

def monthly_climatology(frame: pd.DataFrame, th: Thresholds) -> list[dict]:
    """Per calendar month: mean temperature, mean monthly precipitation total, exceedance and rain-day
    counts per year (averaged over the years in the frame)."""
    rows = []
    n_years = frame.index.year.nunique()
    for m in range(1, 13):
        g = frame[frame.index.month == m]
        t, p = g["T2M"].dropna(), g["PRECTOTCORR"].dropna()
        rows.append({
            "month": m,
            "mean_temp_c": _f(t.mean()) if t.size else None,
            "mean_monthly_precip_mm": _f(p.sum() / n_years) if p.size else None,
            "exceedance_days_per_year": round(float((t > th.temp_c).sum()) / n_years, 3),
            "wet_days_per_year": round(float((p >= th.wet_mm).sum()) / n_years, 3),
            "high_rain_days_per_year": round(float((p >= th.heavy_mm).sum()) / n_years, 3),
        })
    return rows


def seasonal_totals(frame: pd.DataFrame, th: Thresholds) -> list[dict]:
    """IMD seasons: mean seasonal precipitation total per year and rain-day counts per year."""
    n_years = frame.index.year.nunique()
    rows = []
    for key, months in SEASONS.items():
        g = frame[frame.index.month.isin(months)]
        p, t = g["PRECTOTCORR"].dropna(), g["T2M"].dropna()
        rows.append({
            "season": key,
            "label": SEASON_LABELS[key],
            "mean_temp_c": _f(t.mean()) if t.size else None,
            "mean_seasonal_precip_mm": _f(p.sum() / n_years) if p.size else None,
            "wet_days_per_year": round(float((p >= th.wet_mm).sum()) / n_years, 3),
            "high_rain_days_per_year": round(float((p >= th.heavy_mm).sum()) / n_years, 3),
        })
    return rows


def annual_series(frame: pd.DataFrame, th: Thresholds, years: list[int]) -> pd.DataFrame:
    """Per-year statistics for the given (complete) years."""
    rows = []
    for y in years:
        m = metrics(frame[frame.index.year == y], th)
        rows.append({"year": y, "mean_temp_c": m.mean_temp_c, "total_precip_mm": m.total_precip_mm,
                     "exceedance_days": m.temp_exceedance_days, "wet_days": m.wet_days,
                     "high_rain_days": m.high_rain_days, "max_daily_precip_mm": m.max_daily_precip_mm})
    return pd.DataFrame(rows).set_index("year")


def monthly_series(frame: pd.DataFrame) -> pd.DataFrame:
    """Calendar-month mean temperature and total precipitation; a month with any missing day is NaN."""
    g = frame.resample("MS")
    full = g.count().min(axis=1) == g.size()
    out = pd.DataFrame({"mean_temp_c": g["T2M"].mean(), "total_precip_mm": g["PRECTOTCORR"].sum(min_count=1)})
    return out.where(full)


# ---------------------------------------------------------------- tool-specific calculations

def hottest_days(frame: pd.DataFrame, n: int = 10) -> list[dict]:
    t = frame["T2M"].dropna().sort_values(ascending=False).head(n)
    return [{"date": d.date().isoformat(), "temp_c": _f(v)} for d, v in t.items()]


def hottest_months(frame: pd.DataFrame, n: int = 5) -> list[dict]:
    ms = monthly_series(frame)["mean_temp_c"].dropna().sort_values(ascending=False).head(n)
    return [{"month": d.strftime("%Y-%m"), "mean_temp_c": _f(v)} for d, v in ms.items()]


def compound_matrix(frame: pd.DataFrame, offsets: list[float], multipliers: list[float], th: Thresholds) -> list[dict]:
    """Every (offset, multiplier) pair applied to the same historical days. Each cell is one uniform
    what-if; neighbouring cells do NOT imply that temperature causes precipitation change or vice versa."""
    if len(offsets) * len(multipliers) > 121:
        raise ValueError("matrix limited to 121 cells")
    cells = []
    for o in offsets:
        for m in multipliers:
            met = metrics(apply_scenario(frame, Scenario(o, m)), th)
            cells.append({"temp_offset_c": o, "precip_multiplier": m, **{k: v for k, v in met.to_dict().items() if not k.startswith("n_")}})
    return cells


ANALOG_UNITS = {"annual": None, **{k: v for k, v in SEASONS.items()}}


def analog_features(frame: pd.DataFrame, unit: str, years: list[int]) -> pd.DataFrame:
    """Per-year mean temperature and precipitation total for the whole year or one IMD season.
    A year-season with any missing day is EXCLUDED (reported), never filled."""
    if unit not in ANALOG_UNITS:
        raise ValueError(f"unit must be one of {sorted(ANALOG_UNITS)}")
    months = ANALOG_UNITS[unit]
    rows, excluded = [], {}
    for y in years:
        g = frame[frame.index.year == y]
        if months:
            g = g[g.index.month.isin(months)]
        if g.isna().any().any():
            excluded[y] = f"{int(g.isna().any(axis=1).sum())} day(s) with missing values"
            continue
        rows.append({"year": y, "mean_temp_c": float(g["T2M"].mean()), "total_precip_mm": float(g["PRECTOTCORR"].sum())})
    df = pd.DataFrame(rows).set_index("year") if rows else pd.DataFrame(columns=["mean_temp_c", "total_precip_mm"])
    df.attrs["excluded"] = excluded
    return df


def find_analogs(features: pd.DataFrame, s: Scenario, weights: tuple[float, float] = (1.0, 1.0), n: int = 5) -> dict:
    """Years whose (mean T, total P) lie closest to the scenario target.

    Target = period mean T + offset, period mean P total x multiplier. Each variable is standardised by its
    standard deviation ACROSS years (z-scores), so a degree and a millimetre are comparable. Distance is the
    weighted Euclidean distance in z units; similarity = 1 / (1 + distance)."""
    s.validate()
    if len(features) < 3:
        raise ValueError("fewer than 3 usable years for analog search")
    mu = features.mean()
    sd = features.std(ddof=1).replace(0, np.nan)
    target = pd.Series({"mean_temp_c": mu["mean_temp_c"] + s.temp_offset_c,
                        "total_precip_mm": mu["total_precip_mm"] * s.precip_multiplier})
    z = (features - mu) / sd
    zt = (target - mu) / sd
    w = pd.Series({"mean_temp_c": weights[0], "total_precip_mm": weights[1]})
    dist = np.sqrt((((z - zt) ** 2) * w).sum(axis=1))
    order = dist.sort_values().index[:n]
    return {
        "target": {k: round(float(v), 4) for k, v in target.items()},
        "period_mean": {k: round(float(v), 4) for k, v in mu.items()},
        "period_sd": {k: round(float(v), 4) for k, v in sd.items()},
        "target_z": {k: round(float(v), 3) for k, v in zt.items()},
        "outside_historical_range": {k: bool(target[k] > features[k].max() or target[k] < features[k].min()) for k in target.index},
        "analogs": [{"year": int(y), "distance_z": round(float(dist[y]), 4), "similarity": round(1.0 / (1.0 + float(dist[y])), 4),
                     "mean_temp_c": round(float(features.loc[y, "mean_temp_c"]), 3),
                     "total_precip_mm": round(float(features.loc[y, "total_precip_mm"]), 1)} for y in order],
        "all_years": [{"year": int(y), "mean_temp_c": round(float(r.mean_temp_c), 3), "total_precip_mm": round(float(r.total_precip_mm), 1),
                       "distance_z": round(float(dist[y]), 4)} for y, r in features.iterrows()],
    }


BOOT_METRICS = ("mean_temp_c", "total_precip_mm", "exceedance_days", "wet_days", "high_rain_days")


def year_bootstrap(annual: pd.DataFrame, n_boot: int, seed: int) -> dict:
    """Year-level (block = one calendar year) resampling WITH replacement of complete years. Each
    replicate is the mean of a resampled set of years. Keeps within-year seasonality and day-to-day
    persistence; does not represent year-to-year persistence or any change in climate."""
    if not 10 <= n_boot <= 5000:
        raise ValueError("n_boot must be within 10..5000")
    if len(annual) < 5:
        raise ValueError("at least 5 complete years are needed for resampling")
    rng = np.random.default_rng(seed)
    idx = rng.integers(0, len(annual), size=(n_boot, len(annual)))
    out = {}
    for col in BOOT_METRICS:
        vals = annual[col].to_numpy(dtype=float)
        reps = vals[idx].mean(axis=1)
        out[col] = {"replicates": [round(float(v), 4) for v in reps],
                    "median": round(float(np.median(reps)), 4),
                    "p05": round(float(np.percentile(reps, 5)), 4),
                    "p95": round(float(np.percentile(reps, 95)), 4),
                    "observed_mean": round(float(vals.mean()), 4)}
    return out


def sensitivity_sweep(frame: pd.DataFrame, th: Thresholds, years: list[int], offsets: list[float], multipliers: list[float]) -> dict:
    """Mean per-year metrics as ONE assumption varies and the other is held at baseline."""
    sub = frame[frame.index.year.isin(years)]
    n = len(years)

    def row(s: Scenario) -> dict:
        m = metrics(apply_scenario(sub, s), th)
        return {"exceedance_days_per_year": round(m.temp_exceedance_days / n, 3),
                "precip_mm_per_year": round((m.total_precip_mm or 0.0) / n, 2),
                "wet_days_per_year": round(m.wet_days / n, 3),
                "high_rain_days_per_year": round(m.high_rain_days / n, 3)}

    return {"by_temp_offset": [{"temp_offset_c": o, **row(Scenario(o, 1.0))} for o in offsets],
            "by_precip_multiplier": [{"precip_multiplier": m, **row(Scenario(0.0, m))} for m in multipliers]}
