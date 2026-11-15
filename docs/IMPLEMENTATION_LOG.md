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
- Committed and pushed as `56075c6`.

## 2026-11-15: Milestone 3, multi-source (GPM IMERG)
- **Start state:** git clean; Milestone 2 commits `bb592d8`, `26e4f36` and `56075c6` intact.
- **Phase 1 investigation (official sources only):**
  - NASA CMR collections, granules and variables APIs (public JSON).
  - IMERG V07 Technical Documentation (13 July 2023), TRMM-era caveats (2019, V06), GES DISC GPM README, V07 release notes, GPM data policy, and the POWER sources_meteorology page.
  - PDFs were text-extracted with `pypdf` 4.3.1, installed into the session scratchpad only (not the project venv), and run with `python -I`.
  - Findings are in `docs/research/GPM_IMERG_RESEARCH.md`.
- **Authentication (observed):**
  - HTTPS GET of a `GPM_3IMERGDF` granule returns 302 to `urs.earthdata.nasa.gov/oauth/authorize`.
  - OPeNDAP returns 302 to `/login/urs`.
  - No credentials were requested, used or bypassed.
- **POWER IMERG behaviour (observed):**
  - LST requests return all −999 with a message, so IMERG is UTC only.
  - Native 0.1° cells, with edges on multiples of 0.1°. The point-in-cell test used 6 probes.
  - Valid 1998-01-01 to 2026-09-14.
  - `IMERG_PRECTOT_COUNT` is the conditional count, so it cannot be used to check completeness.
- **MERRA-2 cell edges:** verified with probes on both sides of all 4 eastern-cell edges and the western cell's west edge.
- **Sample (Phase 2):**
  - `imergpower_lucknow_20240701_20240731_20261114T223158Z`, 42 cells + MERRA-2 UTC.
  - All 43 checksums match.
  - The point-cell, edge-cell and MERRA-2 values equal the earlier direct probes exactly. The independently recomputed area mean agrees within 5e-5.
  - The July 2024 sub-cell totals spread from 298.5 to 396.9 mm.
  - The first attempt failed on a server connection reset and wrote nothing, which led to the retry logic (D-020).
- **Full acquisition:** each run took about 10 min. 86 POWER requests in total.
  - `imergpower_lucknow_19980101_20261113_20261114T223323Z`
  - `imergpower_lucknow_airport_19980101_20261113_…`
  - Each covers 10,544 days, with 10,484 area-mean days valid. The 60 missing days are all at the end (2026-09-15 onward), so there are no gaps inside the series. 409 days fall after the Final-run end.
- **Real comparison (1998-01-01 to 2025-09-30, UTC, mm):**

| | Eastern cell | Western cell |
|---|---|---|
| Daily r / RMSE | 0.67 / 6.70 mm/day | 0.73 |
| Monthly r (n) / MERRA-2 ÷ IMERG | 0.96 (333) / 1.07 | 0.97 / 1.03 |
| Monthly anomaly r | 0.85 | 0.87 |
| Wet-day fraction MERRA-2 / IMERG, CSI | 27.8% / 24.2%, 0.63 | 24.8% / 23.3%, 0.63 |
| Trend 1998–2024, MERRA-2 (mm/day per decade, p) | **+0.41 (0.010)** | **+0.25 (0.044)** |
| Trend 1998–2024, IMERG | **−0.00 (0.97)** | **−0.04 (0.48)** |
| Trend of the difference | +0.40 (0.004) | +0.26 (0.024) |
| Mean annual difference, 1998–2013 → 2015–2024 | −8 → +172 mm (p 0.002) | −27 → +128 mm (p 0.007) |
| Monthly r, area mean vs single 0.1° cell | 0.96 vs 0.95 | 0.97 vs 0.96 |

  - **Interpretation:** IMERG does **not** confirm the MERRA-2 precipitation increase. The two agree before 2014 and diverge from 2015 in both cells.
  - The data cannot tell which product changed, and the diagnostic wording was corrected to be neutral before it reached the UI.
- **Ingestion hardening (D-020):** message rejection, all-missing error, transport retries. The existing POWER raw data reprocesses identically.
- **Test-design errors corrected:**
  1. Synthetic MERRA noise clipped at zero has a positive mean, so the expected ratio was wrong.
  2. The URL substring check assumed latitude came before longitude.
- **Verification:**
  - `pytest backend`: 99 passed, 1 deselected. `pytest -m network`: 1 passed.
  - `npm test`: 7 passed; typecheck clean; build OK (434 kB gzipped).
  - Temporary-server smoke test of 10 routes: all 200, unknown area 422. The CSVs carry provenance headers.
- Committed and pushed as `8c78e6a`.

## 2026-11-15: Milestone 4, explaining the precipitation divergence
- **Start state:** clean, at `8c78e6a`. The user chose this focus out of four options.
- **Research:**
  - CHIRPS and IMD were investigated through a web-fetch agent; CHIRPS was rejected (D-021).
  - The MERRA-2 correction input was found in NASA/TM-2014-104606 Vol. 35 (NTRS 20150000725): MERRA-2 over land excluding Africa uses CPCU, V1.0 for 1979–2005 and real-time from 2006. The journal paper (Reichle et al. 2017) returned HTTP 403.
  - The CPC README gives "30K+ gauges" for 1979–2005 and "~17K" for 2006 onward.
  - IMD method from Pai et al. (2014), fetched from IMD's own site: 6,955 gauges, Shepard interpolation, varying network.
  - PDFs were text-extracted with scratchpad `pypdf`, run in `-I` mode.
- **IMD acquisition:** 1998–2024, 27 yearly binary files (656 MB raw), each byte count checked. Format verified on the 2024 file against geography and byte order. Processed to `imd_rf025_lucknow_1998_2024`, with no missing days in either cell.
- **CPC:**
  - The NOAA PSL OPeNDAP subset returned 429, then 502 on two later attempts (handled politely, nothing written). Recorded as a blocker.
  - The CPC HTTPS archive gauge sample covers 54 days (15 July and 15 August, 1998–2024). The first run missed 2006–2008 because of `.gz` naming; it was fixed and fetched separately.
  - Format verified: the 2014-07-15 global total is 16,807, against the README's "~17K".
- **Results:**
  - The arbitration table and the gauge-count table are in `docs/research/PRECIP_DIVERGENCE_INVESTIGATION.md`.
  - Western cell: MERRA-2 drifts from IMD (+129 mm/yr per decade, p 0.02) and IMERG does not.
  - Both cells: MERRA-2 shifts relative to IMD across 2006 (p 0.022 east, 0.008 west).
  - Eastern cell: not settled, and its IMD trend is fragile.
  - Local CPC gauges did **not** fall at 2006 (about 5–6 within ±2° before and after), so the "lost gauges" hypothesis is **not supported**.
- **Corrections made during the work:**
  1. A verdict rule that overstated the eastern cell was replaced (D-023).
  2. An unsupported IMD rainfall-day claim was removed from the metadata.
  3. A test of mine assumed an IMD box belonged to one cell, but boxes centred at 81.0° E straddle the cell boundary.
  4. The chart helper did not resolve per-bar colour arrays.
  5. The CPC URL list missed the `.gz` names.
- **Verification:**
  - `pytest backend`: 115 passed, 1 deselected. `pytest -m network`: 1 passed.
  - `npm test`: 7 passed; typecheck clean; build OK.
  - Temporary-server smoke test: `/api/precip-arbitration` 200 for both cells with 54 gauge rows; unknown area 422.
- Committed and pushed as `24f9ac3`.

## 2026-11-15: Milestone 5, demo and submission readiness
- **Start state:** clean, at `24f9ac3`. The user chose this focus.
- **Space Apps rules:** not readable here. The web-fetch tool and direct curl both fail with an untrusted certificate chain. The chain was inspected without reading content: issuer "SSL.com TLS Issuing RSA CA R1", subject `www.space.apps.nasa.gov`, so this is not network interception. Certificate checks were not bypassed. Rules-dependent items are a checklist in `docs/SUBMISSION_DRAFT.md`.
- **Review copy:** a separate backend (:8011) and Vite (:5181) were run, because the user's uvicorn on :8000 predates Milestone 2b. `vite.config.ts` now reads `EARTHSIGNAL_API_PORT` (default 8000) to make that possible.
- **Visual review with Claude in Chrome:**
  - all views render; no console errors
  - checked in a 390 px frame and in dark mode
- **Defects found and fixed:**
  1. IMERG and IMD labelled "Derived estimate (reanalysis)" in the sources table and the precipitation-card badge. Fixed with a source-type label, plus a test that no satellite, gauge or station product is called reanalysis.
  2. A 7 px horizontal overflow at phone width in the data-sources view (grid children lacked `min-width: 0`).
  3. Internal "Milestone 3/4" wording in the UI.
  4. Nested brackets in card titles.
  5. IMD shared POWER's colour in the coverage chart.
- **New default "Key findings" view:** the text comes from `findings.ts` pure functions and live API results (6 new frontend tests). It shows: no significant temperature trend 1981–2025 in either cell; POWER and the airport thermometer drift apart over 2006–2023; POWER's rainfall increase not supported by gauges in the western cell, with no rainfall trend claimed.
- **Build errors caught by the typecheck:**
  - `overview.ts` and `Overview.tsx` clashed on a case-insensitive filesystem; renamed to `findings.ts`.
  - `process` was untyped in `vite.config.ts`; declared locally instead of adding `@types/node`.
- **Cleanup:** a leftover Vite Node process on :5181 was stopped after its task was stopped (same behaviour as in Milestone 1).
- **Docs:** added `docs/DEMO_RUNBOOK.md` and `docs/SUBMISSION_DRAFT.md`; updated the README tour and the demo outline.
- **User decisions:** commit and push; MIT licence; slide deck as the demo format. Committed and pushed as `f92140e` (with `LICENSE`).
- **Fresh clone from GitHub:**
  - backend imports from the clone, 115 passed
  - frontend `npm ci`, 13 tests, typecheck and build OK
  - the clone contains no data, so the repository is reproducible and no restricted data is committed
- **Deck:** 7-slide private artifact https://claude.ai/artifact/KjRvtPw71XDsK2g81TDiBV, built from `docs/DEMO_OUTLINE.md`. Every number was checked against the logged results. The cover has a `[CHALLENGE NAME]` placeholder. Sharing it is the user's decision.

## 2026-11-15: Simulation Studio (six interactive tools)
- **Start state:** `f92140e` plus two uncommitted doc notes. Branch `master`.
- **Backend:**
  - `analysis/simulation.py` holds the shared transformations, metrics, aggregations, compound matrix, analogues, year-block bootstrap and sensitivity sweep.
  - `api/simulation.py` provides `/api/sim/{meta,scenario,heat,rain,compound,analogs,uncertainty}` (GET, `format=csv`), mounted in `create_app`.
  - Inputs are validated (422 on out-of-range values, a reversed or empty period, or an unknown area).
- **Frontend:**
  - `src/sim/` holds `logic.ts` (pure helpers: URLs, clamping, histograms, colour ramp, fail-safe localStorage), `ToolFrame.tsx` (shared controls, run/reset/save/CSV/disclosure), `Tools.tsx` (the six tools), `Studio.tsx` and `studio.css`.
  - `Chart` gained a `dark` option. "Simulation Studio" was added to the primary navigation.
  - Plotly's basic bundle has no heatmap or histogram, so the matrix is a coloured, clickable table and the histograms are binned client-side.
- **Real-data checks (eastern cell, 1991–2020):**
  - Combined stress (+2 °C, ×0.7): mean temperature 26.01 → 28.01 °C; precipitation 28,518 → 19,962 mm (−30.0%).
  - Days with daily mean > 35 °C: 1,328 → 2,085 at +2 °C (44.3 → 69.5 a year). Cross-check: days > 33 °C historically is also 2,085.
  - Compound matrix baseline cell: 44.3 days a year, the same as the heat tool.
  - Bootstrap (1,000 resamples): 44.2 days a year (39.4–48.9) → 69.6 (64.6–74.1); precipitation at ×0.8: median 949 → 759 mm.
  - Analogues, monsoon at +2 °C: target 33.00 °C; nearest is 2014 (32.21 °C, similarity 0.38). 1987 (33.66 °C) shows the target is within range.
- **Errors caught and fixed:**
  1. The tools initially used inconsistent periods (summaries included partial years); every tool now uses complete years only.
  2. Two of my own test expectations were wrong (strict threshold; histogram bin edges).
  3. Shell heredoc quoting errors aborted two edit batches; nothing had been applied, and they were redone with the editor tool or a script file.
  4. A browser test script exceeded the tool's 45 s limit; it was rerun in per-tool steps.
  5. The compound matrix overflowed the page by 203 px at phone width (grid-item min-width); fixed so the matrix scrolls inside its box.
- **Verification:**
  - `pytest backend`: 148 passed. `npm test`: 22 passed. Typecheck exit 0. Build OK (445 kB gzipped).
  - Browser (Claude in Chrome): each of the six tools had its inputs changed, was run, and its results and charts updated with no errors.
  - Phone width (390 px): no horizontal overflow in any tool.

## 2026-11-15: Deck slide and Milestone 6, Response Intelligence
- **Deck:** added a "Simulation Studio" slide before the integrity slide; updated the method slide's test count to 170 (148 backend, 22 frontend). Published to the existing private deck.
- **User choices:** "response" = analyst case workflow; detect heat episodes and extreme rainfall; the project must be explainable by a non-specialist teammate (MBA), so the UI and a new `docs/PRESENTER_GUIDE.md` use plain language.
- **Built:** `analysis/events.py` (detection, cross-check helpers, rule-based summary), `cases.py` (case store, workflow, brief), `api/response.py` (routes), `frontend/src/response/` (three-step view). Decisions in D-025.
- **Results on real data (1981–2026):** eastern cell 77 heat episodes and 47 rainfall events; western cell 93 and 43. The most severe heat episode in both cells is 19–30 July 2002 (the airport station agrees on 4 of 5 near-hourly days). The most severe rainfall event in both cells is 29–30 Aug 2000 (282 mm east), but **neither IMERG (23 mm max) nor IMD (10 mm max) confirms it**, so the tool flags it as a possible reanalysis artifact. That is the workflow doing its job.
- **Problems found and fixed:**
  1. The first summary counted the neighbouring POWER cell as an independent check; it is the same dataset, so it is now labelled not independent and excluded from the count.
  2. Feb 29 was mapped to Mar 1's day-of-year slot; caught by a test, fixed.
  3. Awkward wording ("All 1 … source(s)") rewritten; the station check now says when the station lies outside the event's cell. An unverified distance figure was removed before release.
- **Verification:** `pytest backend` 162 passed; `npm test` 26 passed; typecheck exit 0. Browser walk-through on review servers with a throwaway case file: detect → select → investigate → open case → reason-gated decision → note → audit trail → brief download; no console errors; no overflow at 390 px.
