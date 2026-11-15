# EarthSignal

*Understand Reality. Simulate Possibilities. Anticipate Tomorrow.*
AstraelForge · TheVisionForged

EarthSignal aims to become a Predictive Earth Intelligence System. It starts with Lucknow, Uttar Pradesh, India. **The current version is historical only.** It:

- ingests real NASA POWER daily data (2 m air temperature and corrected precipitation, 1981 to the present)
- adds NASA GPM IMERG satellite-gauge precipitation (1998 onward) and NOAA station temperature as comparison sources
- checks precipitation against the India Meteorological Department (IMD) rain-gauge analysis
- records full provenance for every download
- validates the data
- computes a statistically defensible long-term trend with its caveats
- shows everything in a small web dashboard

**No forecasts, machine learning or simulations are implemented yet.**

### For judges: the 2-minute tour
1. Start the app (see **Run**) and open the **Key findings** view: three findings computed live from the analysis.
2. Follow **See the evidence** to the temperature trend and its robustness checks, the airport-station check, and the rain-gauge check.
3. **Data sources** lists all six datasets with one common set of metadata (provider, version, units, resolution, coverage, processing, citation, limitations).
4. The full demo script is in `docs/DEMO_RUNBOOK.md`, the decisions in `docs/DECISIONS.md`, and the research notes in `docs/research/`.

## Data source

| | |
|---|---|
| Provider | NASA Langley Research Center, POWER Project, Daily API (`/api/temporal/daily/point`) |
| What the values are | **Reanalysis**: NASA GMAO **MERRA-2** (1981 to about a month behind real time), extended to near real time with **GEOS-IT** (about 2 days latency). Weather-model output that assimilates observations. **Not** direct station or satellite measurements. |
| Spatial resolution | Native grid 0.5° latitude × 0.625° longitude (roughly 55 × 62 km). POWER returns the cell containing the request point, with no interpolation. Lucknow straddles a cell boundary (80.9375° E), so EarthSignal analyses **two cells** (DECISIONS D-013): the **eastern cell**, from the central-city point 26.8467 N, 80.9462 E, mostly covering land east of the city; and the **western cell**, from the airport station point 26.761 N, 80.889 E, covering the airport and western Lucknow. |
| Time standard | Daily values in Local Solar Time (LST) |
| Variables | `T2M`, Temperature at 2 Meters (°C): "The average air (dry bulb) temperature at 2 meters above the surface of the earth." `PRECTOTCORR`, Precipitation Corrected (mm/day): "The average MERRA-2 bias corrected total precipitation at the surface of the earth." (Definitions are taken from the POWER parameter-metadata API.) |
| Missing values | The marker is read from each response's `header.fill_value` (−999 so far) and converted to empty/NaN. Values are never zero-filled or imputed. |
| Access | Public; no login or API key |

**Second NASA source: GPM IMERG precipitation (Milestone 3).**
- **Product:** NASA GPM IMERG Final daily V07 (`GPM_3IMERGDF`, doi:10.5067/GPM/IMERGDF/DAY/07). Satellite microwave and infrared precipitation, calibrated monthly to GPCC rain gauges.
- **Access:** EarthSignal obtains it through POWER's `IMERG_PRECTOT` parameter, which needs no login. That parameter is **UTC only** and served on IMERG's native 0.1° cells. Native GES DISC files need an Earthdata Login, so they are not used yet.
- **Version and period:** POWER does not state the IMERG version (V07 is inferred). Only data up to **2025-09-30**, the end of the Final run, is used.
- **Not independent:** IMERG Final uses MERRA-2 winds and GPCC gauges, so agreement with POWER is consistency, not validation.
- Full details: `docs/research/GPM_IMERG_RESEARCH.md`.

The documentation consulted is listed in `docs/DECISIONS.md` (D-003 to D-006): POWER methodology, meteorology sources, processing, Daily API and referencing pages.

## What the analysis does
- **Annual means:** calendar-year means; years with less than 95% valid days are excluded, not imputed.
- **Cutoff:** following NASA POWER's guidance, the trend analysis ends about 2 months behind the retrieval date. The current partial year is never used.
- **Significance:** a Mann-Kendall test with the **Yue & Wang (2004) correction for autocorrelation** decides whether a trend is significant (α = 0.05).
- **Trend size:** Sen's slope with a 95% confidence interval.
- **Cross-check:** OLS slope and Durbin-Watson, shown for comparison only.
- **Diagnostics:** rule-based checks flag cases where naive tests disagree with the corrected test, or where the series is not well described by a single trend.

- **Seasons:** trends for the four IMD seasons, with a Benjamini-Hochberg false-discovery-rate correction across seasons.
- **Robustness:** the trend is recomputed for every start year and every end year (windows of at least 20 years). These windows are descriptive only; the full-period result is the one reported.
- **Source check:** the MERRA-2 to GEOS-IT switch date is measured with single-day requests (currently 2026-10-01). The trend window is entirely MERRA-2.
- **Station check (temperature):** POWER's western cell is compared with NOAA GSOD station 42369099999 (Lucknow airport), using only near-hourly station days (D-015).
- **Baseline backtest (evaluation only, no forecasts shown):** climatology, persistence and damped anomaly persistence are evaluated chronologically (test years 2002–2025, leads of 1–30 days). This sets the bar any future method must beat. Damped anomaly persistence is best for temperature at every lead (skill +0.75 at 1 day, falling to +0.04 at 30 days). For precipitation, nothing beats climatology beyond 1–3 days. Available at `/api/backtest` (D-016).

### Results (POWER retrieved 2026-11-14, trends 1981–2025)
| | Eastern cell | Western cell | Reading |
|---|---|---|---|
| Temperature, Sen's slope per decade (corrected p) | −0.16 °C (0.18) | −0.12 °C (0.35) | **No significant trend in either cell.** Annual means rose to the 1990s and fell after about 2002. Significance depends on the start year, so no window should be chosen after the fact. |
| Precipitation, Sen's slope per decade (corrected p) | +0.24 mm/day (0.014) | +0.15 mm/day (0.079) | Significant in one cell, **not** in its neighbour, and driven by recent years. **Not a robust finding.** POWER precipitation also has weak station skill (NASA: daily R² 0.39), and GSOD cannot confirm it (D-015). |

**Station check (western cell versus the Lucknow airport station, temperature):**
- **Monthly agreement:** over 216 paired months (1999–2025), POWER is +0.63 °C warmer on average (RMSE 1.70 °C, r 0.977, anomaly r 0.80). The bias is strongly seasonal: about +3 °C in May and June, and −1 °C in September and October.
- **Trends, 2006–2023 (16 years):** station +0.10 °C/decade (not significant), POWER −0.26 °C/decade (not significant).
- **Drift:** the POWER−station difference trends at −0.30 °C/decade (p 0.017). The two records **drift apart**, so POWER's recent cooling should not be read as what the station measured. The data cannot say which record is responsible.

**Precipitation check: POWER (MERRA-2) versus GPM IMERG (Milestone 3)**

Both are averaged over the same MERRA-2 cell, on UTC days, in mm, for 1998-01-01 to 2025-09-30 (`docs/research/MULTI_SOURCE_METHODOLOGY.md`).

| 1998–2024 | Eastern cell | Western cell |
|---|---|---|
| Monthly totals: r / MERRA-2 ÷ IMERG | 0.96 / 1.07 | 0.97 / 1.03 |
| Annual-mean trend, MERRA-2 (mm/day per decade, corrected p) | +0.41 (0.010) | +0.25 (0.044) |
| Annual-mean trend, IMERG | −0.00 (0.97) | −0.04 (0.48) |
| Mean annual MERRA-2 − IMERG, 1998–2013 → 2015–2024 | −8 → +172 mm (p 0.002) | −27 → +128 mm (p 0.007) |

- **Agreement:** the two products agree closely on monthly timing.
- **Trend:** **IMERG does not show the precipitation increase seen in MERRA-2.** The products diverge after the 2014 TRMM-to-GPM transition in both cells. These data cannot tell which product changed.
- **Conclusion:** the POWER precipitation trend for Lucknow is **not supported** by a second NASA source.

**Which product matches the rain gauges? (Milestone 4)**

Reference: IMD's 0.25° gridded rain-gauge analysis (Pai et al. 2014), averaged over the same cells. Annual totals, 1998–2024.
- **Western cell:** the gauges show **no trend** (−40 mm/yr per decade, p 0.35). POWER/MERRA-2 **drifts away from them** (+129, p 0.02) and IMERG does not.
- **Both cells:** MERRA-2 shifts upward relative to the gauges across **2006** (p 0.022 and 0.008). That is the year its documented input, NOAA CPC's gauge analysis, switched from the retrospective version (30K+ gauges) to the real-time version (~17K) (NASA TM-2014-104606 Vol. 35; CPC README).
- **Local gauges:** the number of CPC gauges near Lucknow did **not** fall at 2006 (about 5–6 within ±2° before and after), so the cause of the shift is not established.
- **Eastern cell:** the gauges show a fragile increase, so that cell does not settle the question.
- **Conclusion:** no Lucknow precipitation trend should be stated. Details: `docs/research/PRECIP_DIVERGENCE_INVESTIGATION.md`.

Re-running ingestion later produces a new dataset, and the numbers may change slightly as NASA updates the record.

## Simulation Studio (what-if experiments)
The **Simulation Studio** tab offers six interactive tools on the real NASA POWER daily record, for either grid cell. Each tool has run and reset, presets or saved configurations, CSV export, and a methodology, limitations and provenance panel.

| Tool | What it computes |
|---|---|
| 1. Climate Scenario Builder | `T + offset` (−3 to +5 °C), `P × multiplier` (0–200%) on every historical day; baseline versus scenario series and differences |
| 2. Heat Stress Explorer | days whose **daily-mean** temperature exceeds a threshold, per year and per month, plus the hottest days and months |
| 3. Rainfall Stress Simulator | totals, mean daily rain, wet days (≥ 1 mm), high-rainfall days (≥ your threshold), wettest day, monthly and seasonal (IMD) distribution |
| 4. Compound Climate Experiment | a matrix of offsets × multipliers with the supported metrics for each cell |
| 5. Historical Analog Finder | past years or seasons closest to the assumptions (z-standardised distance, similarity score) |
| 6. Uncertainty & Sensitivity Lab | year-block bootstrap with a recorded seed (median, 5th–95th percentile) and one-at-a-time sensitivity curves |

All results are labelled **hypothetical** (the historical record with a uniform change applied) or **derived statistic**. They are not forecasts, projections or impact predictions: no health, flood, crop or economic outcomes. API: `/api/sim/*`; method in `docs/DECISIONS.md` D-024.

## Limitations
- Reanalysis grid cells, not station or street-scale data. Results differ between the two cells covering the city.
- Reanalysis trends can be affected by changes over time in the observations that were assimilated.
- The MERRA-2 to GEOS-IT transition happens in the most recent months. Those values may be revised.
- The station record is not homogeneous: daily means came from 6–8 observations before about 1996 and 20–24 from about 2005. That is why the station check covers only the recent period. It is also not fully independent, since MERRA-2 may assimilate this station's reports.
- A trend describes change. It does not identify a cause, and extrapolating it is not a forecast.
- IMERG trends across 2014 (TRMM to GPM) and 2005 (sensor changes) may contain artifacts (NASA caveats). POWER's IMERG values have not yet been checked against native GES DISC files.

## IMD data notice
IMD gridded rainfall is downloaded from imdpune.gov.in. No licence terms were found on the download pages. IMD asks for citation of Pai et al. (2014), MAUSAM 65(1), 1–18. Raw IMD files are **not** included in this repository.

## Station data notice
NOAA NCEI GSOD data for non-U.S. stations are subject to WMO Resolution 40 (Cg-XII). They are intended for free and unrestricted use in research, education and other non-commercial activities. Non-U.S. data and derived products must not be used commercially. Raw GSOD files are **not** included in this repository; the download command below fetches them from NOAA.

## Requirements
- Python 3.12+, Node.js with npm (developed on Windows 11 with Node v26)
- Internet access to `power.larc.nasa.gov` for ingestion only. Tests run offline.
- No database, Docker or NASA account required. A free NASA Earthdata Login is needed only for the planned native IMERG check.

## Setup (once, from the repository root)
```powershell
python -m venv .venv
.venv\Scripts\python -m pip install -e "backend[dev]"
cd frontend; npm install; cd ..
```

## Run
**1. Get the data.** A fresh clone has none, because `data/` is not committed.
```powershell
.venv\Scripts\python -m earthsignal.data.ingest                          # eastern cell (default)
.venv\Scripts\python -m earthsignal.data.ingest --area lucknow_airport   # western cell
.venv\Scripts\python -m earthsignal.data.source_probe                    # optional: MERRA-2/GEOS-IT switch date
.venv\Scripts\python -m earthsignal.data.source_probe --area lucknow_airport
.venv\Scripts\python -m earthsignal.data.gsod                            # NOAA station data, 1981 to last year (~2 min)
.venv\Scripts\python -m earthsignal.data.imerg_power --area lucknow      # GPM IMERG via POWER: 42 cells + MERRA-2 UTC (~10 min)
.venv\Scripts\python -m earthsignal.data.imerg_power --area lucknow_airport
.venv\Scripts\python -m earthsignal.data.imd 1998 1999 2000                 # IMD gauge grid, ~25 MB per year (list the years you need)
.venv\Scripts\python -m earthsignal.data.imd --process                       # area means over both cells
```
- **POWER downloads:** 1981-01-01 to yesterday (UTC), into a new, never-overwritten folder at `data/raw/<dataset_id>/`. Each run writes `data/processed/<dataset_id>/daily.csv` and `provenance.json` and prints coverage and warnings. Options: `--start`, `--end`, `--area`, and `--from-raw <folder>` (reprocess offline).
- **Station data:** GSOD files go to `data/raw/stations/` and `data/processed/stations/`.
- **IMERG data:** goes to `data/raw/imerg/` and `data/processed/imerg/`. Add `--start/--end` for a small sample first.

**2. Backend (terminal 1)**
```powershell
.venv\Scripts\python -m uvicorn earthsignal.api.main:app --app-dir backend --port 8000
```
Check it at http://127.0.0.1:8000/api/health. The API docs are at http://127.0.0.1:8000/docs.

**3. Frontend (terminal 2)**
```powershell
cd frontend
npm run dev
```
Open the URL Vite prints, normally http://localhost:5173. If that port is busy, Vite picks the next free one, such as 5174. Vite forwards `/api` to the backend on port 8000.

### Troubleshooting
- **The dashboard says "Backend not reachable":** start the backend (step 2).
- **The dashboard says "No data ingested yet":** run step 1.
- **Uvicorn logs `WARNING: Invalid HTTP request received.`:** something sent non-HTTP traffic to port 8000, typically a browser trying `https://`. Use `http://`. These warnings are harmless.

## Tests
```powershell
.venv\Scripts\python -m pytest backend                         # offline backend tests
.venv\Scripts\python -m pytest backend -m network               # live NASA POWER check (opt-in)
.venv\Scripts\python -m pytest backend/tests/test_trend.py::test_detects_known_trend   # single test
cd frontend; npm test; npm run typecheck; npm run build
```
The backend tests use real POWER responses recorded on 2026-11-14 (`backend/tests/fixtures/`). Multi-year API tests use clearly labelled synthetic data that is never written to `data/`.

## Layout
- `backend/earthsignal/data/`:
  - `power.py`: POWER request building, immutable raw capture, parsing, validation, provenance
  - `ingest.py`: the ingest CLI
  - `store.py`: reads processed data
- `backend/earthsignal/analysis/`:
  - `trend.py`: trend statistics and diagnostics
  - `seasonal.py`: seasonal trends
  - `sensitivity.py`: robustness windows
  - `compare.py`: station comparison
  - `multisource.py`: POWER versus IMERG precipitation comparison
  - `backtest.py`: baseline backtest
- `backend/earthsignal/data/`:
  - `source_probe.py`: MERRA-2/GEOS-IT switch date
  - `gsod.py`: NOAA station data
  - `grid.py`: MERRA-2 and IMERG cell geometry
  - `imerg_power.py`: IMERG acquisition and area mean
- `backend/earthsignal/metadata.py`: the common dataset metadata interface (`/api/sources`)
- `backend/earthsignal/api/main.py`: FastAPI app
- `frontend/src/`: React + TypeScript UI using the Plotly basic bundle
- `docs/`: `DECISIONS.md`, `TASKS.md`, `IMPLEMENTATION_LOG.md`, `DEMO_OUTLINE.md`, and `research/` (`GPM_IMERG_RESEARCH.md`, `MULTI_SOURCE_METHODOLOGY.md`)

## Licence
EarthSignal's code is released under the MIT License (see `LICENSE`). Data downloaded by the scripts is **not** covered by this licence and keeps its providers' terms: NASA POWER and GPM IMERG (NASA open data), NOAA GSOD (WMO Resolution 40, non-commercial), IMD gridded rainfall (cite Pai et al. 2014). Raw data is not included in the repository.

## Data citation
The data was obtained from the National Aeronautics and Space Administration (NASA) Langley Research Center (LaRC) Prediction of Worldwide Energy Resource (POWER) Project, funded through the NASA Earth Science Division. The API version and access date for each dataset are recorded in its `provenance.json`.
