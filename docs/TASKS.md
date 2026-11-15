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
- [x] Committed and pushed as `56075c6`
- [ ] Decide later whether a baseline-skill table belongs in the dashboard (it is evaluation, not forecasting)
- [ ] Future: any candidate method must beat damped anomaly persistence at each lead, evaluated with this harness

## Milestone 3: multi-source Earth intelligence (GPM IMERG)
- [x] Inspected the repo and git state (clean; Milestone 2 commits intact)
- [x] Phase 1: IMERG source investigation from NASA CMR, the V07 Technical Documentation, the TRMM-era caveats, the GES DISC README and POWER docs (`docs/research/GPM_IMERG_RESEARCH.md`)
- [x] Phase 2: authentication check. Native files and OPeNDAP need Earthdata Login (observed 302 to URS). No credentials handled.
- [x] Phase 2: small sample via POWER (July 2024, 42 cells), checked against direct probes and checksums, then the full record for both cells
- [ ] Phase 2: **native `GPM_3IMERGDF` sample. Blocked on the user's Earthdata Login** (steps in the research doc §5)
- [x] Phase 3: compatibility analysis and comparison method (`docs/research/MULTI_SOURCE_METHODOLOGY.md`, D-019)
- [x] Phase 4: common metadata interface (D-018), `/api/sources`
- [x] Phase 5: dashboard "Data sources & precipitation check" view: source selector, metadata panel, coverage and resolution comparison, POWER vs IMERG charts, limitations, CSV downloads
- [x] Phase 6: tests for download integrity, metadata, parsing, units, missing values, temporal alignment, spatial aggregation, comparison calculations and API (backend 99, frontend 7)
- [x] Phase 7: docs updated
- [ ] Manual browser check of the new view (user)
- [x] Investigate which product changed around 2014 (done in Milestone 4)

## Milestone 4: explain the POWER/IMERG precipitation divergence
- [x] Documented MERRA-2's corrected-precipitation input over Lucknow: CPCU, switching from V1.0 to real-time in 2006 (D-022)
- [x] Gauge reference: IMD 0.25° gridded rainfall, 1998–2024 acquired and format-verified (D-021)
- [x] Arbitration analysis with pre-registered break dates and a corrected verdict rule (D-023), `/api/precip-arbitration`
- [x] CPC gauge-count sample (2 monsoon days per year, 1998–2024)
- [x] Dashboard card: "Which product matches the rain gauges?"
- [x] Research write-up `docs/research/PRECIP_DIVERGENCE_INVESTIGATION.md`
- [ ] CPCU precipitation series via NOAA PSL (blocked by PSL 429/502; retry later)
- [x] Committed and pushed as `24f9ac3`

## Milestone 5: demo and submission readiness
- [x] Visual review in a browser (Claude in Chrome): desktop, phone width (390 px frame), dark mode; console clean
- [x] Fixed: IMERG and IMD were labelled "reanalysis" (table and badge); phone overflow in the data-sources view; internal "Milestone" wording; nested brackets in titles; IMD coverage colour
- [x] New default **Key findings** view: findings generated by unit-tested pure functions from live API results
- [x] `docs/DEMO_RUNBOOK.md` (setup times, timed 3-minute script, recovery steps); README "For judges" tour
- [x] `docs/SUBMISSION_DRAFT.md`, including an AI-use disclosure draft and a confirm-against-rules checklist
- [ ] **User:** read the official Space Apps rules (unreachable from this machine: untrusted certificate chain) and work through the checklist
- [x] Licence: MIT (user decision, 2026-11-15)
- [x] Slide deck from `docs/DEMO_OUTLINE.md`: 7 slides, private artifact https://claude.ai/artifact/KjRvtPw71XDsK2g81TDiBV (fill in [CHALLENGE NAME] on the cover)
- [x] Fresh-clone check of `f92140e`: backend 115 passed; frontend `npm ci`, 13 tests, typecheck and build OK; the clone contains no data
- [ ] **User decisions:** challenge; repository visibility; publishing the deck or video
- [ ] Fresh-clone reproducibility check after the next commit
- [ ] Decide whether gridded data justifies xarray/rasterio (not needed so far; POWER point requests suffice)

## Simulation Studio (six tools)
- [x] Shared calculation module and `/api/sim/*` (meta, scenario, heat, rain, compound, analogs, uncertainty), with CSV export for each tool (D-024)
- [x] Frontend Simulation Studio: dark workstation, six tools, run/reset, presets, saved configurations, methodology and provenance panel
- [x] Tests: backend 148 (33 new); frontend 22 (9 new)
- [x] Browser verification of every tool (inputs → run → results and charts update); phone-width check; matrix overflow fixed
- [x] Committed and pushed (a1d733c)
- [x] Simulation Studio slide added to the deck; test count on the method slide updated (170)

## Milestone 6: Response Intelligence (detect → investigate → respond)
- [x] Detection: heat episodes (≥3 days above the day-of-year 95th percentile, 1991–2020) and extreme rainfall (≥ wet-day 99th percentile), both cells (D-025)
- [x] Investigation: neighbouring cell (labelled not independent), airport station for heat, IMERG and IMD for rain, each against its own history; rule-based plain-English summary
- [x] Response: local case file (open → investigating → confirmed / dismissed / needs data / escalated), reasons required for decisions, audit trail, Markdown evidence brief
- [x] API `/api/response/*` and `/api/cases*`; UI "Response Intelligence" with a three-step guide written for non-specialists
- [x] Tests: backend 162 (14 new); frontend 26 (4 new); typecheck; browser walk-through; phone width
- [x] Presenter guide in plain language (`docs/PRESENTER_GUIDE.md`)
- [x] Committed and pushed (approved 2026-11-15)
- [ ] Optional: a Response Intelligence slide in the deck

## Milestone 7: Anticipate, tested temperature forecasts
- [x] Pre-registered design written before any candidate was run (D-026)
- [x] `analysis/forecast.py`: two candidates, chronological folds, dev/hold-out selection, year-block bootstrap pass rule, contiguous horizon, empirical band
- [x] Result: eastern cell 30/30 leads pass; western cell 1–29 (lead 30 failed, not shown); outcome recorded in D-026
- [x] `/api/forecast` (JSON and CSV, labelled `forecast`); "Anticipate" view with outlook, past-day marking, skill chart and scorecard
- [x] Tests: backend 170 (8 new: leakage, known-answer synthetic cases, pass rule, issuing); frontend 31 (5 new)
- [x] Browser check (both cells, phone width, no console errors); docs and presenter guide updated
- [x] Committed and pushed (approved 2026-11-15)
- [ ] Optional: deck slide for the outlook
- [ ] Later: record issued forecasts and score them when NASA data for those days arrives

## Deferred / backlog
- [ ] Playwright end-to-end test (needs a ~100–300 MB browser download; ask first)
- [ ] MapLibre study-area map showing the POWER grid cell footprint
- [ ] Lint and format tooling (ruff, eslint)
