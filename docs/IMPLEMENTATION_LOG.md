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
