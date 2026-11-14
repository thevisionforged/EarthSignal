# EarthSignal

*Understand Reality. Simulate Possibilities. Anticipate Tomorrow.*
AstraelForge · TheVisionForged

EarthSignal is a Predictive Earth Intelligence System, starting with Lucknow, Uttar Pradesh, India. The current MVP is **historical only**:

- It ingests real NASA POWER daily data (2 m air temperature and corrected precipitation, 1981 to the present).
- It records full provenance for every download.
- It validates the data.
- It computes a statistically defensible long-term trend.
- It shows the results in a web UI.

No forecasts are produced yet.

> NASA POWER meteorology is **reanalysis** (NASA GMAO MERRA-2, extended with GEOS-IT). It is a model-based estimate that assimilates observations, averaged over a ~0.5° × 0.625° grid cell. It is not a station or satellite measurement. See `docs/DECISIONS.md`.

## Requirements
- Windows 11 (developed on), Python 3.12, Node.js (tested with v26) and npm
- Internet access to `power.larc.nasa.gov`, needed only for ingestion
- No database, Docker or NASA account required

## Setup (once)
```powershell
cd C:\AstraelForge\EarthSignal
python -m venv .venv
.venv\Scripts\python -m pip install -e "backend[dev]"
cd frontend; npm install; cd ..
```

## 1. Get the data
```powershell
.venv\Scripts\python -m earthsignal.data.ingest
```
This downloads 1981-01-01 to yesterday (UTC) into a new, never-overwritten folder at `data/raw/<dataset_id>/`. It then writes `data/processed/<dataset_id>/daily.csv` and `provenance.json` and prints coverage and warnings. Options are `--start`, `--end`, and `--from-raw <folder>` (reprocess offline).

## 2. Run the backend (terminal 1)
```powershell
.venv\Scripts\python -m uvicorn earthsignal.api.main:app --app-dir backend --port 8000
```
To check it's running, open http://127.0.0.1:8000/api/health. The interactive docs are at http://127.0.0.1:8000/docs.

## 3. Run the frontend (terminal 2)
```powershell
cd frontend
npm run dev
```
Open http://localhost:5173. Vite proxies `/api` to the backend.

## Tests
```powershell
.venv\Scripts\python -m pytest backend                         # offline backend tests
.venv\Scripts\python -m pytest backend -m network               # live NASA POWER check (opt-in)
.venv\Scripts\python -m pytest backend/tests/test_trend.py::test_detects_known_trend   # single test
cd frontend; npm test; npm run typecheck; npm run build
```

## Layout
- `backend/earthsignal/data/`: POWER request building, immutable raw capture, parsing, validation, provenance (`power.py`), the ingest CLI (`ingest.py`), and reading processed data (`store.py`)
- `backend/earthsignal/analysis/trend.py`: annual means, Mann-Kendall (with Yue-Wang correction), Sen's slope, OLS cross-check
- `backend/earthsignal/api/main.py`: FastAPI app
- `frontend/src/`: React UI (Plotly basic bundle)
- `docs/`: `DECISIONS.md`, `TASKS.md`, `IMPLEMENTATION_LOG.md`

## Data citation
The data was obtained from the National Aeronautics and Space Administration (NASA) Langley Research Center (LaRC) Prediction of Worldwide Energy Resource (POWER) Project, funded through the NASA Earth Science Division. The API version and access date for each dataset are recorded in its `provenance.json`.
