# Tasks

Priority order. Status: `[x]` done and tested · `[~]` in progress · `[ ]` not started.

## Milestone 1: smallest end-to-end MVP (historical, no forecasts)
- [x] Environment audit (hardware, tools). See IMPLEMENTATION_LOG 2026-11-14.
- [x] Check NASA POWER documentation: source methodology, variable definitions and units, fill value, time standard, latency, citation (DECISIONS D-004 to D-006).
- [x] Project skeleton, git repo, `.gitignore`, Python venv, `pyproject.toml`
- [x] NASA POWER acquisition: immutable raw capture, request record, parameter metadata capture
- [x] Parsing, fill-value handling (NaN, never zero), validation report
- [x] Provenance record (URL, retrieval time, API version, coordinates, units, definitions, date range, hashes, docs, citation)
- [x] Trend analysis: annual means, Mann-Kendall plus Yue-Wang, Sen's slope plus CI, OLS cross-check, limitations
- [x] FastAPI: `/api/health`, `/api/datasets`, `/api/provenance`, `/api/timeseries`, `/api/trend`
- [x] Backend tests (pytest) using a recorded real POWER response
- [x] Run the real ingestion for 1981-01-01 to yesterday and record the actual coverage (IMPLEMENTATION_LOG)
- [x] Rule-based trend diagnostics (D-010)
- [x] React + TS + Vite frontend: monthly time series, annual means, Sen trend line, trend statistics, diagnostics, provenance
- [x] Frontend unit tests (Vitest), typecheck and build
- [x] README run procedure, verified by actually running it (HTTP level)
- [x] First git commit (`c2f0c5e`, 2026-11-15)

## Milestone 1b: demo readiness (no new science, data or architecture)
- [x] `.gitignore` covers `*.tsbuildinfo` (done before `c2f0c5e`, re-verified)
- [x] Code review of the backend and frontend; defects fixed (IMPLEMENTATION_LOG 2026-11-15)
- [x] Reanalysis labelling: page banner, chart badge, provenance card and API `data_kind`
- [x] Trend card made readable: plain verdict, corrected and uncorrected p, CI, "How to read these numbers"; non-significant trend line marked and muted
- [x] Responsive CSS (phone breakpoints at 560 and 360 px), legend moved above the plot, theme-aware chart colours
- [x] README rewritten: data source, analysis, results, limitations, troubleshooting
- [x] Seven-slide demo outline (`docs/DEMO_OUTLINE.md`)
- [x] Second commit (`556cc76` after the email rewrite). Pushed to private GitHub repo `thevisionforged/EarthSignal`.
- [ ] **Manual browser inspection by the user** (light and dark, desktop and phone width, both tabs, the "How to read" toggle, and the offline backend message)
- [ ] Choose the Space Apps challenge and confirm submission requirements

## Milestone 2: historical validation and backtesting groundwork
### 2a: seasonal and robustness analysis (existing data only)
- [x] Seasonal trends (IMD seasons) with Benjamini-Hochberg FDR across seasons (D-011)
- [x] Start-year and end-year robustness windows with rule-based diagnostics (D-011)
- [x] MERRA-2 / GEOS-IT boundary measured with a reproducible probe (D-012). The trend window is all MERRA-2.
- [x] API `/api/seasonal`, `/api/sensitivity`; dashboard robustness and seasonal cards
- [ ] Manual browser check of the new cards (user)
### 2b: independent station comparison
- [x] Investigate NOAA GSOD: station, access, format, comparability, licence (D-014)
- [x] Found the study point sits at the edge of a grid cell; the stations fall in the neighbouring cell (D-013)
- [x] Decision: show both cells; area switcher in the API and dashboard (D-013 resolution)
- [x] Decision: show GSOD results with the WMO Resolution 40 notice; never commit raw GSOD (D-014 resolution)
- [x] Western-cell ingestion and source probe (real)
- [x] GSOD ingestion: immutable raw files, provenance, unit conversion, sentinel handling, station metadata history
- [x] Inspected the real station data before choosing rules: observation-count inhomogeneity, unusable precipitation (D-015)
- [x] Temperature comparison: monthly metrics, anomaly correlation, trend comparison including a drift test, dashboard card
- [ ] Manual browser check of the cell switcher and the station card (user)
- [ ] Optional: check whether MERRA-2 assimilates this station's reports (independence), using MERRA-2 documentation
### 2c: backtesting groundwork
- [x] Chronological backtesting harness: climatology, persistence, damped anomaly persistence; leads 1–30 days; yearly expanding folds (D-016)
- [x] Leakage tests and validation against synthetic theory (AR(1) skill, white noise)
- [x] `/api/backtest` (evaluation statistics only; nothing shown as a forecast)
- [ ] Decide later whether a baseline-skill table belongs in the dashboard (it is evaluation, not forecasting)
- [ ] Future: any candidate method must beat damped anomaly persistence at each lead, evaluated with this harness

## Milestone 3: second NASA source
- [ ] Investigate Earthdata-authenticated products (GPM IMERG precipitation, MODIS/MAIAC aerosol) and document access, licence and size before implementing
- [ ] Decide whether gridded data justifies xarray/rasterio and, later, PostGIS

## Deferred / backlog
- [ ] Playwright end-to-end test (needs a ~100–300 MB browser download; ask first)
- [ ] MapLibre study-area map showing the POWER grid cell footprint
- [ ] Lint and format tooling (ruff, eslint)
