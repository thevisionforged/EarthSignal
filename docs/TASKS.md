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
- [ ] Visual check of the rendered page in a browser (light and dark, phone width)
- [ ] First git commit (waiting for the user to ask)

## Milestone 2: historical validation and backtesting groundwork
- [ ] Compare POWER T2M with an independent station record for Lucknow (for example NOAA GSOD/ISD for the Amausi airport station), with source and licence checked first
- [ ] Seasonal (monsoon/winter/pre-monsoon) trend breakdown, with a multiple-testing caveat
- [ ] Sensitivity of the trend to the start year and to excluding the GEOS-IT period
- [ ] Chronological backtesting harness with climatology and persistence baselines (still no forecasts in the UI until validated)

## Milestone 3: second NASA source
- [ ] Investigate Earthdata-authenticated products (GPM IMERG precipitation, MODIS/MAIAC aerosol) and document access, licence and size before implementing
- [ ] Decide whether gridded data justifies xarray/rasterio and, later, PostGIS

## Deferred / backlog
- [ ] Playwright end-to-end test (needs a ~100–300 MB browser download; ask first)
- [ ] MapLibre study-area map showing the POWER grid cell footprint
- [ ] Lint and format tooling (ruff, eslint)
