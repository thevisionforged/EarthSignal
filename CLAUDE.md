# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

**EarthSignal**: *Understand Reality. Simulate Possibilities. Anticipate Tomorrow.*
Built by the AstraelForge research and engineering team, part of TheVisionForged.

EarthSignal is meant to become a Predictive Earth Intelligence System. It will use real-world observations, scientific modelling, statistical analysis and machine learning to understand environmental systems, find patterns, explore scenarios and anticipate future conditions. The first geographic focus is **Lucknow, Uttar Pradesh, India**.

**Current priority:** build a working, demonstrable hackathon MVP before expanding the long-term research vision. Every submission claim must match functionality that is implemented and tested, and NASA data usage must be verified, not just asserted.

## Current state

Milestone 1 (historical MVP) is implemented and tested. See `docs/TASKS.md`, `docs/IMPLEMENTATION_LOG.md` and `docs/DECISIONS.md` (read DECISIONS before changing data handling or statistics). **No forecasts exist yet, by design** (D-008).

Environment audit (2026-11-14): Windows 11, **7.7 GB physical RAM** (often only about 1 GB free), 512 GB SSD. Python 3.12.10, Node v26.13.0, npm 11.20.0, git 2.56.0. PostgreSQL, Docker, uv and conda are not installed. PyPI downloads are slow (about 40 KB/s), so large installs take a long time; run them in the background.

## Architecture

- `backend/earthsignal/data/power.py`: NASA POWER daily point API. Builds URLs, writes raw files immutably (`open(..., "xb")`), parses (fill value taken from `header.fill_value` and replaced with NaN), validates (flags problems without altering data) and builds the provenance dict.
- `backend/earthsignal/data/ingest.py`: CLI. `download()` creates `data/raw/<dataset_id>/` (response, parameter metadata, request record). `process()` reads raw and writes `data/processed/<dataset_id>/daily.csv` and `provenance.json`. A new dataset_id is created per run, and raw files are never overwritten.
- `backend/earthsignal/data/store.py`: loads the newest processed dataset (by `retrieved_at_utc`).
- `backend/earthsignal/analysis/trend.py`: annual means (≥95% coverage, cutoff of retrieval date − 2 months per NASA guidance), Mann-Kendall plus Yue-Wang correction (decides significance), Sen's slope and CI, OLS cross-check, and rule-based `diagnostics`.
- `backend/earthsignal/analysis/seasonal.py` (IMD seasons, Benjamini-Hochberg FDR) and `sensitivity.py` (start/end-year windows of at least 20 years, plus diagnostics). Both reuse `trend.analyze_trend`. Never pick a window after looking at the results (D-011).
- `backend/earthsignal/data/source_probe.py`: measures the MERRA-2/GEOS-IT boundary with single-day requests and writes `source_periods.json` (D-012).
- **Grid-cell caveat (D-013):** POWER returns the cell containing the point, with no interpolation. Lucknow straddles a cell boundary, so there are two study areas in `config.STUDY_AREAS`: `lucknow` (eastern cell, default) and `lucknow_airport` (western cell, containing the stations). Datasets are matched to areas by requested coordinates (`store.area_of`), and endpoints take `?area=`. Check cell membership before any point comparison.
- `backend/earthsignal/data/gsod.py` and `analysis/compare.py`: NOAA GSOD station 42369099999 compared against the western cell (D-014, D-015). **Never commit real GSOD data** (WMO Resolution 40); tests use synthetic GSOD-format rows. Only station days with at least 20 observations enter the metrics, because the observation count changed over time. GSOD precipitation is not usable for comparison.
- `backend/earthsignal/analysis/backtest.py`: the chronological baseline harness (D-016), exposed at `/api/backtest`. Training stops `max(lead)` days before each test year. Any new forecasting method must be evaluated with this harness and must beat damped anomaly persistence before anything forecast-like reaches the UI.
- **Milestone 3, multi-source:**
  - `data/grid.py`: MERRA-2 and IMERG cell geometry, with verified edges.
  - `data/imerg_power.py`: GPM IMERG via POWER `IMERG_PRECTOT`, which is **UTC only**. All 42 IMERG cells per MERRA-2 cell are fetched and area-weighted.
  - `analysis/multisource.py`: POWER versus IMERG comparison (D-019).
  - `metadata.py`: the common `DatasetMetadata` interface (D-018), served at `/api/sources`. Every new source must map to it.
  - Use IMERG data only up to the Final-run end (`imerg_power.FINAL_RUN_END`, 2025-09-30).
  - Native GES DISC IMERG needs Earthdata Login. Never handle the user's credentials; see `docs/research/GPM_IMERG_RESEARCH.md` §5.
  - POWER responses with non-empty `messages` are rejected (D-020).
- **Milestone 4, gauge reference:**
  - `data/imd.py`: IMD 0.25° binary, little-endian, (days, lat S→N, lon W→E), −999 = missing. Byte count is checked on download.
  - `data/cpc.py`: CPCU, with gauge counts from the CPC HTTPS archive. File naming varies by year, including `.gz`.
  - `analysis/arbiter.py`: one primary test per product (trend of product − IMD), plus break tests at the **pre-registered** dates 2006 and 2014 with Bonferroni correction (D-023). Never add break dates chosen from the data.
  - IMD's day boundary is undocumented, so compare it monthly or annually only.
- `backend/earthsignal/api/main.py`: `create_app(processed_root)` factory. Routes: `/api/health`, `/api/datasets`, `/api/provenance`, `/api/timeseries`, `/api/trend`. Returns 404 (never fake data) when nothing has been ingested.
- `frontend/src/`: React 18 with `plotly.js-basic-dist-min`. Vite proxies `/api` to `127.0.0.1:8000`. `format.ts` holds the pure, tested helpers.
- Data labels: POWER values are `derived_estimate` (reanalysis), trend outputs are `derived_statistic`. Never label POWER data "observed".
- Tests: `backend/tests/fixtures/*.json` are **real recorded** POWER responses. `conftest.synthetic_power_doc` is clearly synthetic and used only for multi-year test paths.

## Original stack proposal

This is a **modular monolith** for the MVP, made of one backend service and one frontend app, with no microservices.

| Layer | Intended stack |
|---|---|
| Frontend | React, TypeScript, Vite; Plotly for charts, MapLibre for maps |
| Backend | Python, FastAPI, Pydantic |
| Scientific computing | NumPy, Pandas, SciPy, Xarray |
| Geospatial | GeoPandas, Rasterio, PostGIS |
| Database | PostgreSQL + PostGIS |
| Testing | Pytest (backend), Vitest (frontend unit), Playwright (end-to-end) |

For the MVP, deliberately not installed: PostgreSQL/PostGIS, Docker, xarray, geopandas, rasterio, MapLibre and Playwright (D-002, D-009). Ask before installing any of them.

## Commands

Run from the repo root (PowerShell):
```powershell
.venv\Scripts\python -m pip install -e "backend[dev]"            # backend setup
.venv\Scripts\python -m earthsignal.data.ingest                   # download real POWER data, eastern cell (network)
.venv\Scripts\python -m earthsignal.data.ingest --area lucknow_airport   # western cell
.venv\Scripts\python -m earthsignal.data.source_probe [--area ...]       # MERRA-2/GEOS-IT switch date
.venv\Scripts\python -m earthsignal.data.gsod                     # NOAA GSOD station data (~2 min at ~40 KB/s)
.venv\Scripts\python -m earthsignal.data.imerg_power --area lucknow [--start/--end]   # GPM IMERG via POWER (~10 min full record)
.venv\Scripts\python -m earthsignal.data.ingest --from-raw data\raw\<dataset_id>   # reprocess offline
.venv\Scripts\python -m uvicorn earthsignal.api.main:app --app-dir backend --port 8000
.venv\Scripts\python -m pytest backend                            # offline tests (network tests deselected)
.venv\Scripts\python -m pytest backend -m network                 # live NASA POWER test
.venv\Scripts\python -m pytest backend/tests/test_trend.py::test_detects_known_trend   # single test
```
Run from `frontend/`: `npm install`, `npm run dev` (port 5173), `npm test`, `npx vitest run -t "senLine"` (single test), `npm run typecheck`, `npm run build`.

## Scientific integrity (non-negotiable)

1. Never fabricate NASA observations, dataset metadata, measurements, model outputs or validation results. If data has not been fetched, say so.
2. For every dataset, record provenance: source, product ID, version, variables, units, spatial and temporal resolution, coverage, and processing history.
3. Label every value as **observed**, **derived estimate**, **forecast** or **hypothetical scenario**, in data models, API responses and the UI.
4. Establish simple scientific baselines (climatology, persistence, linear trend) before advanced ML. Any ML model must beat them to be justified.
5. Validate chronologically (train on the past, test on the future; no random splits on time series). Report suitable error metrics, such as MAE, RMSE and bias, against the baselines.
6. Never present correlation as causation.
7. Keep AI-generated narrative explanations separate from numerical scientific calculations. Text generation must never produce or alter numbers.
8. Document uncertainty and limitations alongside results.

## Engineering principles

- Prefer small, testable, documented components.
- Preserve raw source data unchanged, and keep derived data separate and traceable to its raw inputs.
- Never silently replace missing values with zero. Keep them explicit (NaN/null) and handle them deliberately.
- Keep secrets out of source control, for example NASA Earthdata credentials in an untracked `.env` file.
- Optimize for a 16 GB RAM laptop. Avoid unnecessary services, large models, and heavy infrastructure. Subset data spatially and temporally to the Lucknow region before loading it.

## Working protocol

- Work autonomously inside this project directory. Never scan unrelated personal directories or access credentials.
- Inspect before modifying.
- Maintain `docs/IMPLEMENTATION_LOG.md` (dated entries recording what changed, decisions and why, and verification results) and `docs/TASKS.md` (the task tracker). Create both when work begins.
- Run the relevant tests after meaningful changes, and report failures honestly.
- Explain the commands you run and any important architectural decisions.
- Ask before destructive actions, administrator-level changes (such as system installs or services), external publishing, paid services, or sending private data anywhere.
