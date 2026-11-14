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

## D-009: Lightweight frontend (2026-11-14)
- **Decision:** Vite + React + TypeScript with `plotly.js-basic-dist-min` (the smallest Plotly bundle with scatter and line traces) and no UI framework. The Vite dev server proxies `/api` to `127.0.0.1:8000`. Playwright is deferred because its browser download is large; Vitest covers the frontend logic.
