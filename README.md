# EarthSignal

*Understand Reality. Simulate Possibilities. Anticipate Tomorrow.*
AstraelForge · TheVisionForged

EarthSignal aims to become a Predictive Earth Intelligence System. It starts with Lucknow, Uttar Pradesh, India. **The current version is historical only.** It:

- ingests real NASA POWER daily data (2 m air temperature and corrected precipitation, 1981 to the present)
- records full provenance for every download
- validates the data
- computes a statistically defensible long-term trend with its caveats
- shows everything in a small web dashboard

**No forecasts, machine learning or simulations are implemented yet.**

## Data source

| | |
|---|---|
| Provider | NASA Langley Research Center, POWER Project, Daily API (`/api/temporal/daily/point`) |
| What the values are | **Reanalysis**: NASA GMAO **MERRA-2** (1981 to about a month behind real time), extended to near real time with **GEOS-IT** (about 2 days latency). Weather-model output that assimilates observations. **Not** direct station or satellite measurements. |
| Spatial resolution | Native grid 0.5° latitude × 0.625° longitude (roughly 55 × 62 km). POWER returns the cell containing the request point (26.8467 N, 80.9462 E), with no interpolation. That point is just east of a cell boundary (80.9375° E), so the cell used (centred near 27.0 N, 81.25 E) mostly covers land **east** of the city. The airport and much of western Lucknow fall in the neighbouring cell (DECISIONS D-013). |
| Time standard | Daily values in Local Solar Time (LST) |
| Variables | `T2M`, Temperature at 2 Meters (°C): "The average air (dry bulb) temperature at 2 meters above the surface of the earth." `PRECTOTCORR`, Precipitation Corrected (mm/day): "The average MERRA-2 bias corrected total precipitation at the surface of the earth." (Definitions are taken from the POWER parameter-metadata API.) |
| Missing values | The marker is read from each response's `header.fill_value` (−999 so far) and converted to empty/NaN. Values are never zero-filled or imputed. |
| Access | Public; no login or API key |

The documentation consulted is listed in `docs/DECISIONS.md` (D-003 to D-006): POWER methodology, meteorology sources, processing, Daily API and referencing pages.

## What the analysis does
- **Annual means:** calendar-year means; years with less than 95% valid days are excluded, not imputed.
- **Cutoff:** following NASA POWER's guidance, the trend analysis ends about 2 months behind the retrieval date. The current partial year is never used.
- **Significance:** a Mann-Kendall test with the **Yue & Wang (2004) correction for autocorrelation** decides whether a trend is significant (α = 0.05).
- **Trend size:** Sen's slope with a 95% confidence interval.
- **Cross-check:** OLS slope and Durbin-Watson, shown for comparison only.
- **Diagnostics:** rule-based checks flag cases where naive tests disagree with the corrected test, or where the series is not well described by a single trend.

### Results from the dataset retrieved 2026-11-14 (1981–2025, 45 years)
| Variable | Sen's slope per decade (95% CI) | Corrected p | Reading |
|---|---|---|---|
| Temperature (T2M) | −0.16 °C (−0.29 to −0.01) | 0.18 | **No significant monotonic trend.** Annual means rose to the 1990s and declined after about 2002. Naive tests would wrongly report significant cooling. |
| Precipitation (PRECTOTCORR) | +0.24 mm/day (+0.10 to +0.38) | 0.014 | Significant in this dataset, but POWER precipitation has weak skill against stations (NASA: daily R² 0.39), so it needs independent confirmation. |

Re-running ingestion later produces a new dataset, and the numbers may change slightly as NASA updates the record.

## Limitations
- Reanalysis for one grid cell. It does not represent within-city variation such as urban heat islands, and it is not a substitute for station records.
- Reanalysis trends can be affected by changes over time in the observations that were assimilated.
- The MERRA-2 to GEOS-IT transition happens in the most recent months. Those values may be revised.
- A trend describes change. It does not identify a cause, and extrapolating it is not a forecast.
- Not yet done: comparison with an independent station record, seasonal analysis, sensitivity to the start year.

## Requirements
- Python 3.12+, Node.js with npm (developed on Windows 11 with Node v26)
- Internet access to `power.larc.nasa.gov` for ingestion only. Tests run offline.
- No database, Docker or NASA account required

## Setup (once, from the repository root)
```powershell
python -m venv .venv
.venv\Scripts\python -m pip install -e "backend[dev]"
cd frontend; npm install; cd ..
```

## Run
**1. Get the data.** A fresh clone has none, because `data/` is not committed.
```powershell
.venv\Scripts\python -m earthsignal.data.ingest
```
This downloads 1981-01-01 to yesterday (UTC) into a new, never-overwritten folder at `data/raw/<dataset_id>/`. It then writes `data/processed/<dataset_id>/daily.csv` and `provenance.json` and prints coverage and warnings. Options are `--start`, `--end`, and `--from-raw <folder>` (reprocess offline).

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
- `backend/earthsignal/analysis/trend.py`: trend statistics and diagnostics
- `backend/earthsignal/api/main.py`: FastAPI app
- `frontend/src/`: React + TypeScript UI using the Plotly basic bundle
- `docs/`: `DECISIONS.md`, `TASKS.md`, `IMPLEMENTATION_LOG.md`, `DEMO_OUTLINE.md`

## Data citation
The data was obtained from the National Aeronautics and Space Administration (NASA) Langley Research Center (LaRC) Prediction of Worldwide Energy Resource (POWER) Project, funded through the NASA Earth Science Division. The API version and access date for each dataset are recorded in its `provenance.json`.
