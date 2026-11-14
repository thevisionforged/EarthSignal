# Decisions

Architecture and scientific decisions, newest last. Each entry gives the context, the decision, and its consequences.

## D-001: Modular monolith, Python backend and React frontend (2026-11-14)
- **Context:** Hackathon MVP on a single Windows laptop.
- **Decision:** One FastAPI backend package (`backend/earthsignal`) and one Vite React-TS frontend (`frontend/`). No microservices.
- **Consequences:** Simple to run locally. The modules (`data`, `analysis`, `api`) are kept separate so they can be split out later.

## D-002: No PostgreSQL/PostGIS, Docker or xarray/geopandas in the MVP (2026-11-14)
- **Context:** The environment audit found no PostgreSQL or Docker. Physical RAM is **7.7 GB**, not the 16 GB assumed in early planning, with about 1 GB free at audit time. The MVP needs one point time series (~16k rows).
- **Decision:** Store raw data as immutable JSON files and processed data as CSV plus a `provenance.json`. Install only fastapi, uvicorn, pydantic, httpx, numpy, pandas, scipy and pytest. Defer xarray, geopandas, rasterio and PostGIS until gridded or spatial data is needed.
- **Consequences:** No database service is required. Revisit when gridded or regional data arrives.

## D-003: First data source is the NASA POWER Daily API point endpoint (2026-11-14)
- **Context:** We need real NASA data quickly, without credentials, and small enough for the laptop.
- **Decision:** `GET https://power.larc.nasa.gov/api/temporal/daily/point` for Lucknow (26.8467 N, 80.9462 E), community `AG`, `time-standard=LST`, parameters `T2M` and `PRECTOTCORR`, 1981-01-01 to yesterday.
- **Consequences:** No Earthdata login is needed. Earthdata-authenticated products (for example GPM IMERG or MODIS) are a later milestone.

## D-004: NASA POWER characterised as reanalysis, not observation (2026-11-14)
- **Verified from:** https://power.larc.nasa.gov/docs/methodology/ and https://power.larc.nasa.gov/docs/methodology/data/sources_meteorology/
- **Facts:**
  - "Meteorological parameters are derived from NASA's GMAO MERRA-2 assimilation model and GEOS-IT."
  - MERRA-2 covers 1981-01-01 to about a month behind near real time. GEOS-IT fills in to near real time with about 2 days of latency.
  - Native grid: 1/2° latitude × 5/8° longitude.
  - POWER as a whole mixes satellite-derived products (solar and radiation from CERES SYN1deg, FLASHFlux and GEWEX SRB; IMERG; SMAP) with model and reanalysis products. The two variables we use are reanalysis.
  - NASA reports validation against GSOD daily stations (1981–2020): T2M MBE −0.53 °C, RMSE 2.10 °C, R² 0.97. Daily precipitation MBE 0.55 mm/day, RMSE 3.69 mm/day, R² 0.39, so precipitation skill is much weaker.
- **Decision:** Label POWER values `data_kind = "derived_estimate"` everywhere, never "observed". Never describe POWER as satellite-only.

## D-005: Variable definitions and units verified against the official API metadata (2026-11-14)
Source: `https://power.larc.nasa.gov/api/system/manager/parameters?community=AG&temporal=daily&parameters=T2M,PRECTOTCORR` (the response is stored with every ingest).

| Parameter | Name | Units | Official definition |
|---|---|---|---|
| T2M | Temperature at 2 Meters | C | "The average air (dry bulb) temperature at 2 meters above the surface of the earth." |
| PRECTOTCORR | Precipitation Corrected | mm/day | "The average MERRA-2 bias corrected total precipitation at the surface of the earth." |

The sources_meteorology page explains that PRECTOTCORR uses MERRA-2's observationally corrected precipitation forcing and cites Reichle et al. (2017), doi:10.1175/JCLI-D-16-0570.1. The POWER pages do not name the reference precipitation dataset, so EarthSignal does not claim one. Ingestion fails if the units in the response, the metadata or the expected values disagree.

## D-006: Missing-value convention (2026-11-14)
- The POWER documentation pages we read do not state the fill value. Every live API response carries it as `header.fill_value` (−999.0 in all responses seen).
- **Decision:** Parse the fill value from each response header and replace only that value with NaN. Abort if the header lacks it. Never zero-fill or impute. Missing days at the end of the series are reported as expected near-real-time latency; missing days within the series are reported as warnings.

## D-007: Trend method: annual means, Mann-Kendall with Yue-Wang correction, Sen's slope (2026-11-14)
- **Context:** Daily temperature is dominated by the seasonal cycle and is strongly autocorrelated, so a naive regression on daily values overstates significance.
- **Decision:**
  1. Aggregate to calendar-year means. Exclude years with less than 95% valid days (no imputation).
  2. Follow NASA POWER's advice to "end the analysis 2 months behind NRT when assessing climate trends": only years ending on or before retrieval date − 2 months are used.
  3. Run the Mann-Kendall test with tie correction and a continuity correction.
  4. Apply the Yue & Wang (2004) variance inflation based on the lag-1 autocorrelation of the Sen-detrended series (only when ρ₁ > 0). The modified p-value decides significance.
  5. Report Sen's slope with a 95% CI (`scipy.stats.theilslopes`), and OLS with Durbin-Watson as a cross-check.
- **Validation:** Unit tests check a hand-computed S and variance, agreement with `scipy.stats.kendalltau` and the median of pairwise slopes, recovery of a known synthetic trend, a white-noise false-positive rate near 5%, and fewer false positives under AR(1) noise.
- **Limitations (also returned by the API):** results describe one reanalysis grid cell; reanalysis trends can be affected by changes in which observations were assimilated; a trend is not a cause; extrapolating it is not a forecast; the Sen CI assumes independence.

## D-008: No forecasts in the current milestones (2026-11-14)
- **Decision:** Forecasting is out of scope until historical validation and chronological backtesting exist. The API exposes only historical estimates and descriptive trend statistics.

## D-010: Rule-based trend diagnostics (2026-11-14)
- **Context:** On real Lucknow T2M, the naive Mann-Kendall (p=0.035) and OLS (p=0.026) tests indicate significant cooling, but the autocorrelation-corrected test does not (p=0.18). The annual series rises and then falls (DW 1.04).
- **Decision:** `analyze_trend` returns `diagnostics`, deterministic statements derived only from the statistics (thresholds α = 0.05, DW < 1.5, lag-1 r > 0.3), and the UI shows them. The modified Mann-Kendall p-value is the only basis for "significant". Narrative text is never generated by an LLM here (CLAUDE.md integrity rule 7).

## D-011: Seasonal trends and robustness checks (2026-11-15, Milestone 2a)
- **Seasons:** India Meteorological Department convention. Winter Jan–Feb, pre-monsoon Mar–May, monsoon Jun–Sep, post-monsoon Oct–Dec. No season crosses a year boundary. A season-year needs at least 95% valid days and must end on or before the 2-month cutoff.
- **Method:** the same as the annual trend (D-007). Corrected Mann-Kendall p-values are adjusted with **Benjamini-Hochberg (FDR)** across the 4 seasons of each variable, using `scipy.stats.false_discovery_control`. The seasonal verdict uses the FDR-adjusted p.
- **Robustness:** Sen's slope and corrected p are recomputed for every start year (end fixed) and every end year (start fixed), with windows of at least 20 years. These overlapping windows are descriptive and are **not** used to claim significance. Rule-based diagnostics flag window-dependent significance, sign changes, and results that only appear in recent years.
- **Guardrail:** report the full-period result. Never choose a window after looking at the results.

## D-012: MERRA-2 / GEOS-IT boundary measured, not assumed (2026-11-15)
- Single-day POWER requests report their own source in `header.sources`. Checked: 14 of 14 single-day values match the full-range download exactly.
- `python -m earthsignal.data.source_probe` binary-searches the boundary and stores each raw probe response immutably. Result at the probe time (2026-11-14 20:44 UTC): **MERRA-2 up to 2026-09-30, GEOS-IT from 2026-10-01**.
- The trend window (ending 2025, or May 2026 for winter and pre-monsoon) is entirely MERRA-2, so mixing in GEOS-IT is not a factor in the current results.
- **Assumption:** a single switch point, checked at the search endpoints.

## D-013: The study point sits at the edge of a MERRA-2 grid cell (2026-11-15). Decision pending.
- **Evidence:** live POWER requests for 2024-01-01 to 03.
  - Points at the airport (26.761 N, 80.889 E) and the old city station (26.867 N, 80.933 E) return **identical** values and elevation (127.59 m).
  - Our study point (26.8467 N, 80.9462 E) returns different values (elevation 117.11 m).
  - So POWER returns the value of the grid cell containing the point, with no interpolation.
- **Grid geometry:** MERRA-2 longitude centres fall at multiples of 0.625°, so one boundary is at 80.9375° E. Our point is 0.009° east of it, in the cell centred near (27.0 N, 81.25 E), which lies mostly east of Lucknow. The stations and most of western Lucknow are in the cell centred near (27.0 N, 80.625 E). The geometry is inferred from the MERRA-2 grid spacing; the cell-membership behaviour is verified.
- **Consequence:** Milestone 1 results are real and correctly computed, but they describe the eastern cell. Any station comparison must use the station's own cell.
- **Options for the user:** (a) keep the current cell and describe it accurately; (b) switch the study point to the airport cell; (c) show both cells. Every option means new ingestion (raw data is kept) and recomputing the results.

## D-014: NOAA GSOD investigated as the independent station record. Not yet downloaded; licence decision pending.
- **Station:** `42369099999`, LUCKNOW / CHAUDHARY CHARAN SINGH INTL (VILK), 26.761 N, 80.889 E, 125 m. The NOAA station list gives records from 1944-01-01 to 2025-08-24. There is also `42368099999` (LUCKNOW, 26.867 N, 80.933 E), 1973 to 2021-11-25. Source: `https://www.ncei.noaa.gov/pub/data/noaa/isd-history.csv`.
- **Access:** `https://www.ncei.noaa.gov/data/global-summary-of-the-day/access/{YEAR}/42369099999.csv`, anonymous, HTTP 200 for 2024.
- **Format (readme):** TEMP is a daily mean in °F, with missing coded 9999.9. TEMP_ATTRIBUTES is the number of observations (6 to 24 seen in 2024). PRCP is in inches, with missing coded 99.99. PRCP_ATTRIBUTES flag "I" means no precipitation report at all, so 0.00 with "I" is not a confirmed dry day. At least 4 observations are required for a daily summary.
- **Comparability issues:**
  - GSOD days are **UTC** days. POWER days are Local Solar Time, about 5.4 h ahead.
  - The number of observations behind each daily mean changes over time, which can bias a trend. This needs a minimum-observation rule and a homogeneity check.
  - The station is a point; POWER is a ~55 × 62 km cell.
  - Precipitation reporting has gaps.
- **Independence (not verified):** MERRA-2 may assimilate this station's surface reports. Its corrected precipitation is constrained by gauge analyses (Reichle et al. 2017), which may include Lucknow gauges. Agreement is therefore not fully independent confirmation, especially for precipitation.
- **Licence (GSOD readme, WMO Resolution 40):** non-US data are "intended for free and unrestricted use in research, education, and other non-commercial activities". For non-US locations, the readme also restricts providing "the data or any derived product" to other users. The formal NCEI landing page returned HTTP 503 and has not been read.
- **Proposed handling, pending user decision:** never commit GSOD files (`data/` is already gitignored). Use them for non-commercial research comparison. Do not show GSOD-derived values in any public demo until the user decides how to read the restriction.

## D-013 resolution and D-014 resolution (2026-11-15, user decisions)
- **D-013:** the user chose to **show both cells**. Study areas are `lucknow` (the original point, eastern cell) and `lucknow_airport` (26.761 N, 80.889 E, western cell containing stations 42369 and 42368). Datasets are matched to areas by requested coordinates. Every data endpoint takes `?area=`. The dashboard has a cell switcher. The original dataset is unchanged.
- **D-014:** the user judges a non-commercial hackathon demo acceptable under the GSOD/WMO Resolution 40 terms. GSOD-derived comparison results are shown in the dashboard **with the licence notice attached**. Raw GSOD files are still never committed (`data/` is gitignored), and tests use synthetic GSOD-format data only.

## D-015: Station comparison design (2026-11-15)
- **Inspection before design:** the real GSOD file for 42369099999 (1981–2025) was examined first.
  - Median observations per day: 6–8 until 1995, 12–19 in 1996–2004, 22–24 from 2005.
  - Days with at least 20 observations make up 83–100% of each year from 2005.
  - Precipitation flag "I" (no report) covers about 230 days per year from 1999. Only 15 of 536 months have at least 90% of days with a 24-hour report (flag G).
- **Temperature, primary rule:** a station day counts only if it has at least 20 observations, and a month only if at least 90% of its days are valid in both series. All metrics use this primary set.
- **Context series:** the at-least-4-observations series is shown for context only. Its POWER−station difference is about +1.2 °C in months with up to 8 observations, versus +0.66 °C in months with at least 20. That gap shows the sampling inhomogeneity.
- **Trend comparison:** annual means of paired monthly anomalies (each series relative to its own calendar-month climatology), using years with at least 10 paired months. The same method (D-007) is applied to the station, to POWER, and to the POWER−station difference. A significant difference trend means the records drift apart.
- **Precipitation:** not compared. GSOD reports are mostly missing ("I") or partial-day (A–F, H), and the readme does not state that the D and F sums cover a full 24 hours. Any monthly total would be biased.
- **Comparison cell:** POWER is compared using the cell that contains the station (the western cell). The eastern cell's metrics are reported in the implementation log for reference only.

## D-016: Chronological backtesting harness with simple baselines (2026-11-15, Milestone 2c)
- **Purpose:** set the bar that any future forecasting method must beat. **No forecasts are shown in the UI.** The results are evaluation statistics (`data_kind: evaluation_statistic`, `not_a_forecast: true`), exposed through `/api/backtest` only.
- **Baselines:**
  - **Climatology:** a 3-harmonic seasonal cycle fitted by least squares on training data. It handles leap years and needs no smoothing window.
  - **Persistence:** the value at the forecast origin.
  - **Damped anomaly persistence:** climatology plus φ_h × (origin anomaly), where φ_h is the lag-h autocorrelation of training anomalies.
- **Folds:**
  - Expanding window, one fold per calendar test year.
  - Training data ends `max(lead)` days before the test year starts, so no training day falls after any forecast origin. This is tested by scrambling data after an origin and by perturbing the gap.
  - First test year: at least 20 training years (2002 for data starting in 1981).
  - Last test year: the last full year that ends on or before the 2-month cutoff **and** is covered by the data.
- **Leads:** 1, 3, 7, 14 and 30 days.
- **Metrics:** MAE, RMSE, bias, and skill = 1 − MSE/MSE_climatology, pooled and per fold.
- **Missing values:** NaN targets or origins are skipped, never filled.
- **Harness validation (synthetic):**
  - recovers the AR(1) theoretical skill φ^(2h) within 0.05
  - on white noise, damped anomaly persistence has no skill and raw persistence has skill ≈ −1 at lead 1
  - the climatology fit recovers a known harmonic exactly
- **Limitations:**
  - Skill is measured against reanalysis, not station data.
  - RMSE skill is a rough guide for daily precipitation.
  - Climatology bias reflects shifts between the training and test periods.

## D-017: GPM IMERG through NASA POWER first; native GES DISC IMERG needs Earthdata Login (2026-11-15, Milestone 3)
- **Investigation:** see `docs/research/GPM_IMERG_RESEARCH.md`.
  - The official product is `GPM_3IMERGDF` V07 (doi:10.5067/GPM/IMERGDF/DAY/07), whose Final run currently ends 2025-09-30 (CMR).
  - Native files are global, 31.7 MB per day.
  - An HTTPS GET or an OPeNDAP request without credentials redirects to Earthdata Login.
- **Decision:**
  - Acquire IMERG through POWER's `IMERG_PRECTOT` (public, no login). It is UTC only, and was verified to return the native 0.1° cells without interpolation.
  - Label it as a POWER distribution with version V07 *inferred*.
  - Use only data up to 2025-09-30 (the Final-run end) in comparisons.
- **Not done:** a native sample, which needs the user's Earthdata account. EarthSignal never handles credentials directly.
- **MERRA-2 cell edges:** verified empirically on both sides of every edge, with no interpolation. Eastern cell 26.75–27.25 N × 80.9375–81.5625 E; western cell 26.75–27.25 N × 80.3125–80.9375 E. Encoded and tested in `data/grid.py`.

## D-018: Common dataset metadata interface (2026-11-15)
- `metadata.DatasetMetadata` (Pydantic) holds the fields required by the Milestone 3 brief.
- Existing provenance is never rewritten; adapters derive the common description. New source types embed it.
- Served at `GET /api/sources`.

## D-019: POWER-versus-IMERG comparison rules (2026-11-15)
- **Like-for-like basis:**
  - same area: IMERG area mean over the MERRA-2 cell, with every cell required each day
  - same day boundaries: MERRA-2 requested in UTC
  - same units: mm/day
  - same period: 1998-01-01 to 2025-09-30, with both series valid
- **Aggregation:** complete months and years only. Differences are MERRA-2 − IMERG.
- **Era-step test:** fixed at the documented 2014 TRMM→GPM transition.
- **Not independent:** IMERG Final uses MERRA-2 fields and GPCC gauges. Results are framed as consistency between related products, never as validation.
- Full method: `docs/research/MULTI_SOURCE_METHODOLOGY.md`.

## D-020: Ingestion hardening (2026-11-15)
- **API messages:** any non-empty POWER `messages` now rejects the response. This was found when IMERG requested in LST returned only −999 values and a message, which the old parser would have accepted as an all-missing series.
- **Empty variables:** a requested variable with no valid values is now a validation **error**.
- **Retries:** transport errors (connection reset, timeout) are retried up to 3 times with 2, 5 and 15 s backoff. HTTP error statuses are never retried. This followed a real connection reset by the server during the first IMERG sample.
- **No regression:** existing Milestone 1–2 POWER raw data reprocesses under the new rules into byte-identical processed data.

## D-009: Lightweight frontend (2026-11-14)
- **Decision:** Vite + React + TypeScript with `plotly.js-basic-dist-min` (the smallest Plotly bundle with scatter and line traces) and no UI framework. The Vite dev server proxies `/api` to `127.0.0.1:8000`. Playwright is deferred because its browser download is large; Vitest covers the frontend logic.
