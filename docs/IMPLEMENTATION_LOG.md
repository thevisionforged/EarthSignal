# Implementation log

Newest entries at the bottom. Record only what was actually done and verified.

## 2026-11-14: Environment audit
- CPU: Intel i5-11260H, 6 cores / 12 threads. **RAM: 7.7 GB physical, about 0.9 GB free at audit time** (planning had assumed 16 GB). Disk C: 293 GB free.
- Tools: Python 3.12.10, pip 25.0.1 (upgraded to 26.3 in the venv), Node v26.13.0, npm 11.20.0, git 2.56.0. Not installed: PostgreSQL/psql, Docker, uv, conda.
- `power.larc.nasa.gov` is reachable (HTTP 200).

## 2026-11-14: NASA POWER investigation (before implementation)
- Live probe: `GET /api/temporal/daily/point?parameters=T2M,PRECTOTCORR&community=AG&longitude=80.9462&latitude=26.8467&start=20240101&end=20240105&format=JSON` returned HTTP 200. Header: `api.version = v2.10.3`, `sources = ["MERRA2"]`, `fill_value = -999.0`, `time_standard = LST`. Units: T2M `C`, PRECTOTCORR `mm/day`. Returned coordinates: 80.946, 26.847, elevation 117.11 m. This response is stored byte-for-byte as `backend/tests/fixtures/power_daily_sample.json`.
- Parameter metadata endpoint response stored as `backend/tests/fixtures/power_parameter_metadata_sample.json`.
- Official documentation pages read: methodology, sources_meteorology, processing, daily API, referencing. Findings are in DECISIONS D-004 to D-006. The documentation pages do not state the fill value, so it is taken from each response header.

## 2026-11-14: Milestone 1 build
- Ran `git init`. Created the venv `.venv`. Backend package at `backend/` (editable install with `[dev]` extras).
- Implemented `earthsignal.data.power` (URL building, immutable writes, parsing, validation, provenance), `earthsignal.data.ingest` (CLI), `earthsignal.data.store`, `earthsignal.analysis.trend` and `earthsignal.api.main`.
- Frontend: hand-written Vite + React 18 + TS setup with `plotly.js-basic-dist-min`. `npm install` added 100 packages. npm's install-script policy skipped esbuild's postinstall, but Vite works because esbuild's platform binary is a separate package.
- Frontend verification: `npm test` passed (4 tests), `npm run typecheck` passed, and `npm run build` passed (bundle 1.25 MB, 428 kB gzipped, mostly Plotly).
- The first pip install appeared stalled after upgrading pip, so it was stopped and rerun with logging. The cause was a slow network: PyPI measured at about 40 KB/s, so scipy (36.7 MB) took more than 15 minutes.
- Installed in the venv: fastapi 0.163.0, starlette 1.10.0, uvicorn 0.54.0, pydantic 2.14.3, httpx 0.28.1, numpy 2.5.4, pandas 3.1.1, scipy 1.18.1, pytest 9.2.0, plus their dependencies.

## 2026-11-14: First real NASA POWER ingestion
- Command: `.venv\Scripts\python -m earthsignal.data.ingest` (took about 4.6 s).
- dataset_id `power_daily_lucknow_19810101_20261113_20261114T173438Z`, retrieved at 2026-11-14T17:34:38Z.
- Raw response sha256: `b37050b4ca49cd9c63e666ce9468e22a57b94e1202a64ea3643c2558a7709643`.
- API v2.10.3. Sources reported: **MERRA2 and GEOSIT**, confirming the near-real-time splice.
- Returned grid point: 26.847 N, 80.946 E, elevation 117.11 m.
- T2M: 16,751 of 16,753 days valid, 1981-01-01 to 2026-11-11, daily range 7.26 to 42.01 °C.
- PRECTOTCORR: 16,751 of 16,753 days valid, same dates, range 0.0 to 142.43 mm/day.
- The 2 missing days are 2026-11-12 and 2026-11-13, at the end of the series (latency). There are no missing days within the series and no values outside the plausible ranges.

## 2026-11-14: First real trend results (1981–2025, 45 annual means; 2026 excluded by the 2-month cutoff)
| Variable | Sen's slope / decade (95% CI) | MK p | Modified MK p | lag-1 r | OLS / decade (p) | DW |
|---|---|---|---|---|---|---|
| T2M | −0.158 °C (−0.287, −0.007) | 0.035 | **0.181** | 0.43 | −0.146 (0.026) | 1.04 |
| PRECTOTCORR | +0.243 mm/day (0.101, 0.377) | 0.0023 | **0.014** | 0.21 | +0.192 (0.008) | 1.45 |

- T2M annual means are not monotonic. Decade means: 1981–90 25.95, 1991–2000 26.37, 2001–10 25.98, 2011–20 25.68, 2021–25 25.45 °C. There is **no statistically significant monotonic trend** after the autocorrelation correction. The naive tests would have wrongly reported significant cooling.
- PRECTOTCORR shows a significant increase after correction, but NASA's validation of POWER daily precipitation is weak (R² 0.39), so this needs independent confirmation.
- Added rule-based `diagnostics` to the trend output (DECISIONS D-010) and a precipitation-specific caveat.

## 2026-11-14: Verification
- `pytest backend`: 43 passed, 1 deselected (the network test).
- `pytest backend -m network`: 1 passed (live POWER request).
- A single-test invocation works.
- Frontend: `npm test` 4 passed, `npm run typecheck` clean, `npm run build` OK.
- Ran the README procedure. uvicorn on :8000 and Vite on :5173 both served. `/api/health`, `/api/trend` and `/api/provenance` returned real data through the Vite proxy.
- Not yet done: a visual check of the rendered chart in a browser (only HTTP responses were checked), and Playwright.

## 2026-11-15: Re-verification for the milestone report (no code changes)
- `pytest backend`: 43 passed, 1 deselected. `pytest backend -m network`: 1 passed. `npm test`: 4 passed. `npm run typecheck`: exit 0. `npm run build`: OK (JS 1,252 kB, 428 kB gzipped).
- Raw file check: `daily_point_response.json` sha256 is unchanged (`b37050b4…9643`). Header covers 19810101–20261113, and 16,753 keys per variable. Only 20261112 and 20261113 carry −999 for each variable. The processed CSV has exactly 2 NaN per column and 0 zeros in T2M.
- Found: `frontend/tsconfig.tsbuildinfo` (a typecheck build artifact) is not in `.gitignore`. Not fixed yet.

## 2026-11-15: First commit
- Added `*.tsbuildinfo` to `.gitignore` and reviewed the 40 files (no data, venv, node_modules or secrets).
- Git identity set for this repo only: `thevisionforged <thevisionforged@users.noreply.github.com>`. Committed as `c2f0c5e`, not pushed.

## 2026-11-15: Demo-readiness review (Milestone 1b)
- Port 5173 was held by an orphaned Vite process from an earlier session (PIDs 17980 and 17500, started 2026-11-14 23:06). Stopping the background task had not killed the Node child. Stopped those PIDs only; the user's servers (Vite :5174, uvicorn PID 1476) were left running.
- The user's uvicorn log showed `Invalid HTTP request received` (non-HTTP traffic on :8000, typically an https attempt) and an asyncio `ConnectionResetError` (known Windows Proactor noise). Neither is an application defect. Documented in README troubleshooting.
- Defects found and fixed:
  1. The chart drew a prominent Sen's slope line even when the trend was not significant (T2M). It is now muted and dotted, with "(not significant)" in the legend (`trendLineLabel`).
  2. When the backend was down, the UI said "No data loaded" and gave the ingest command. It now distinguishes 404 (no data) from an unreachable backend (`loadProblem`).
  3. There was no loading state. Added one.
  4. Chart colours were read once, so they were wrong after an OS theme change. Chart now re-renders on `prefers-color-scheme` change and resolves colour tokens itself.
  5. The legend sat below the plot and crowded the x-axis on narrow screens. It is now above the plot, with automargins and a 300 px chart height on phones.
  6. The reanalysis nature was visible only in a badge and footnote. Added a page banner stating the values are reanalysis estimates, not thermometer or gauge readings, and that there are no forecasts.
  7. The trend heading did not name the variable. Fixed, and added a plain-language verdict and a "How to read these numbers" section. That section explains why the T2M CI excludes 0 while the corrected p is 0.18: the CI does not account for autocorrelation.
  8. `GET /` returned 404. Added a root route listing endpoints.
- Tests added: `test_root_lists_endpoints`, `test_datasets_listing` (backend), plus `loadProblem` and `trendLineLabel` (frontend). One new test initially failed because of a test-fixture bug: two fixtures shared one temp folder. Fixed in the test, not the app.
- README rewritten: data source table, analysis method, results with dataset date, limitations, port fallback, troubleshooting. Added `docs/DEMO_OUTLINE.md`.
- Verification: `pytest backend` 45 passed, 1 deselected. `pytest -m network` 1 passed. `npm test` 6 passed. Typecheck clean. Build OK (JS 1,256 kB, 429 kB gzipped). The user's Vite dev server on :5174 served the updated modules (HTTP 200) and proxied `/api/trend` successfully.
- Not verified by me: the visual rendering in a browser. Waiting for the user's manual inspection.

## 2026-11-15: GitHub
- Installed GitHub CLI 2.104.0 (winget). The user logged in as `thevisionforged` through browser device flow. Ran `gh auth setup-git`, which adds a credential helper for github.com to the global git config.
- Repo identity set to `thevisionforged <thevisionforged@gmail.com>`, at the user's request. Rewrote the 2 unpushed commits' author and committer (`c2f0c5e` became `a299c50`, `1003b34` became `556cc76`); the trees are identical.
- Created the **private** repo https://github.com/thevisionforged/EarthSignal and pushed `master`. GitHub links both commits to the user `thevisionforged`.

## 2026-11-15: Milestone 2a, seasonal and robustness analysis
- New modules:
  - `analysis/seasonal.py`: IMD seasons, BH FDR
  - `analysis/sensitivity.py`: start and end windows of at least 20 years, plus diagnostics
  - `data/source_probe.py`: finds the MERRA-2/GEOS-IT boundary
- New endpoints: `/api/seasonal`, `/api/sensitivity`. New frontend file `Analysis.tsx` with the seasonal table and robustness charts.
- **Source probe (real):** 14 single-day requests. MERRA-2 up to 2026-09-30, GEOS-IT from 2026-10-01. Raw responses are in `data/raw/<dataset_id>__source_probe_20261114T204433Z/`. All 14 single-day T2M values equal the full-download values.
- **Seasonal T2M (real):** no season is significant after FDR.
  - Winter −0.17 °C/decade (FDR p 0.47)
  - Pre-monsoon −0.08 (0.53)
  - Monsoon −0.19 (corrected p 0.054, FDR 0.22)
  - Post-monsoon −0.21 (0.39)
- **Seasonal PRECTOTCORR (real):** **pre-monsoon +0.13 mm/day/decade, FDR p 0.032, significant**.
  - Monsoon +0.55 (corrected p 0.072, FDR 0.14)
  - Winter −0.04 and post-monsoon −0.03, not significant
- **Robustness, T2M:** the full period is not significant, but 13 of 26 start years (1983–1995) give significant cooling. Windows ending 2000–2010 show warming and those ending 2011 or later show cooling. **The temperature trend verdict is fragile.**
- **Robustness, PRECTOTCORR:** positive for every start year (22 of 26 significant). Significant only for windows ending 2021 or later, so recent years drive it.
- Tests: `pytest backend` 61 passed, 1 deselected. `npm test` 6 passed, typecheck clean, build OK (430 kB gzipped).

## 2026-11-15: Milestone 2b investigation (no station data downloaded)
- NOAA station list downloaded to the scratchpad (not the repo). Lucknow airport station `42369099999` has records 1944 to 2025-08-24; old city station `42368099999` has 1973 to 2021-11-25.
- GSOD readme and the 2024 airport file were read through the web-fetch agent (D-014). The NCEI landing page returned HTTP 503.
- **Grid-cell check:** POWER requests at both station coordinates return identical values (elevation 127.59 m). Our study point returns different values (117.11 m). The study point is 0.009° east of the MERRA-2 cell boundary at 80.9375° E (D-013).
- Waiting for user decisions on D-013 and D-014.

## 2026-11-15: Milestone 2a committed
- `bb592d8` pushed to `origin/master`.

## 2026-11-15: Milestone 2b, both grid cells and the station comparison
- The user chose to show both cells and to show GSOD results in the demo with the notice attached (D-013 and D-014 resolutions).
- **Multi-area support:** `config.STUDY_AREAS`, `store.area_of()`, `ingest --area`, `source_probe --area`, `?area=` on all endpoints, and `/api/areas`.
- **Real ingestion, western cell:**
  - dataset `power_daily_lucknow_airport_19810101_20261113_20261114T210009Z`, grid elevation 127.59 m
  - T2M and PRECTOTCORR: 16,751 of 16,753 days valid
  - source probe: MERRA-2 to 2026-09-30, GEOS-IT from 2026-10-01 (14 requests)
- **Western versus eastern cell (1981–2025):**
  - T2M: −0.12 °C/decade (corrected p 0.35) in the west, against −0.16 (0.18) in the east. Neither is significant.
  - PRECTOTCORR: **+0.15 mm/day/decade, p 0.079, not significant** in the west, against +0.24 (0.014, significant) in the east. The pre-monsoon FDR result also disappears in the west. **The precipitation "finding" depends on the grid cell.**
- **Real GSOD download:**
  - dataset `gsod_42369099999_1981_2025_20261114T210127Z`: 45 yearly files, none missing on the server, 15,932 station-days
  - station metadata constant at 26.760594 N, 80.889339 E, 124.96 m; the name changed in 2025; the station list ends 2025-08-24
  - download time about 1 min 42 s
- **Inspection findings:** observation-count inhomogeneity and unusable precipitation (D-015).
- **Comparison, western cell versus station:**
  - 216 paired months (1999-11 to 2025-07)
  - POWER − station: mean +0.63 °C, MAE 1.37, RMSE 1.70, r 0.977, anomaly r 0.80
  - seasonal bias pattern: +3.0 °C in May, +2.9 in June, −1.1 in September and October
  - eastern cell, for reference: bias +0.46, RMSE 1.57, r 0.978
- **Trend comparison:** 16 years (2006, 2008, 2010–2023), annual mean anomalies.
  - station +0.10 °C/decade (p 0.86)
  - POWER western cell −0.26 (p 0.58)
  - **difference POWER − station −0.30 °C/decade, p 0.017, significant drift**
  - The records drift apart over the recent period. These data cannot tell which record is responsible.
- Tests: `pytest backend` 70 passed, 1 deselected. `npm test` 6 passed, typecheck clean, build OK (431 kB gzipped).
- HTTP smoke test of all 11 routes on a temporary server (:8001): all 200, and an unknown area returns 422.

## 2026-11-15: Milestone 2b committed
- `26e4f36` pushed to `origin/master` (user approved).

## 2026-11-15: Milestone 2c, backtesting groundwork (no forecasts in the UI)
- New `analysis/backtest.py` and `/api/backtest?area=&variable=` (D-016). Runtime for 2 cells × 2 variables × 24 folds × 5 leads: about 2.4 s.
- **Real results:** test years 2002–2025, 24 folds, 8,766 forecasts per lead. Skill vs climatology (pooled):

| Lead (days) | T2M persistence | T2M damped anomaly | PRECTOTCORR persistence | PRECTOTCORR damped anomaly |
|---|---|---|---|---|
| 1 | +0.73 | **+0.75** (24/24 folds > 0) | −0.10 | **+0.20** (23/24) |
| 3 | +0.16 | **+0.35** (24/24) | −0.83 | +0.01 (16/24) |
| 7 | −0.37 | **+0.17** (23/24) | −1.04 | 0.00 (climatology best) |
| 14 | −1.12 | **+0.10** (20/24) | −1.01 | 0.00 (climatology best) |
| 30 | −3.98 | **+0.04** (17/24) | −1.08 | 0.00 (climatology best) |

  These are eastern-cell numbers. The western cell is within 0.01–0.04 at every lead.
- **Other values:**
  - T2M climatology RMSE 2.14 °C; PRECTOTCORR climatology RMSE 7.45 mm/day.
  - **T2M climatology bias +0.33 °C** at every lead: the test years were cooler than training in POWER. Given the POWER–station drift (D-015), part of this shift may not be real.
- **Two errors found and fixed during testing:**
  1. My white-noise test wrongly expected raw-persistence skill of −1 at every lead. The seasonal change between origin and target adds error at longer leads. The test now asserts −1 at lead 1 and below −1.2 at lead 7.
  2. **Real bug:** `test_year_range` ignored where the data ends, so it scheduled empty folds when the data ended before the cutoff year. This was caught by the API test on synthetic data ending in 2020. Fixed, with regression assertions. Real-data results are unaffected, because the cutoff falls inside the data.
- Tests: `pytest backend` 79 passed, 1 deselected.
