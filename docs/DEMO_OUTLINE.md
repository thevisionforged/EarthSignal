# NASA Space Apps demo outline (7 slides)

Every claim below maps to something implemented and verified (see "Evidence"). Numbers are from dataset `power_daily_lucknow_19810101_20261113_20261114T173438Z`, retrieved 2026-11-14. If you re-run ingestion before the demo, refresh the numbers from the dashboard.

Not yet known: the specific Space Apps challenge this is entered under and its submission rules. Align slide 1 wording with the challenge statement once it is chosen.

---

## Slide 1: EarthSignal: understanding Lucknow's climate record honestly
- Tagline: *Understand Reality. Simulate Possibilities. Anticipate Tomorrow.*
- Problem: city-level climate claims often skip three things: where the data comes from, what kind of data it is, and whether a "trend" is statistically real.
- What we built: an open pipeline and dashboard that turns 45 years of NASA data for Lucknow into trend results with provenance and stated caveats.
- Scope today: **historical analysis only**. Forecasting is future work.
- *Evidence:* README; dashboard header and banner.

## Slide 2: NASA data used
- NASA POWER Daily API (NASA Langley Research Center), point request for Lucknow (26.85 N, 80.95 E).
- Variables: `T2M`, 2 m air temperature (°C), and `PRECTOTCORR`, bias-corrected precipitation (mm/day). Definitions are quoted from NASA's parameter metadata.
- What it is: **reanalysis**, meaning NASA GMAO MERRA-2 plus GEOS-IT for the most recent days. Model output constrained by observations, on a 0.5° × 0.625° grid cell. *Not* station or satellite readings, and the dashboard labels it that way.
- Coverage: 1981-01-01 to 2026-11-11, with 16,751 of 16,753 days valid. The last 2 days are pending NASA's ~2-day latency.
- *Evidence:* `provenance.json`; dashboard provenance card; DECISIONS D-004 and D-005.

## Slide 3: Pipeline and provenance (show it working)
- Diagram: NASA POWER API → raw JSON (immutable, SHA-256 recorded) → validation → processed CSV and provenance record → FastAPI → React dashboard.
- Recorded for every download: exact request URL, retrieval time (UTC), API version (v2.10.3), sources reported (MERRA2, GEOSIT), coordinates, units, definitions, date range, hashes, citation.
- Missing values: NASA's fill marker is read from each response and becomes "missing", never zero.
- Live: run `python -m earthsignal.data.ingest` (about 5 s) and show its coverage printout.
- *Evidence:* `backend/earthsignal/data/`; tests in `test_power.py` and `test_ingest.py`.

## Slide 4: Dashboard walkthrough (live)
- Temperature tab: monthly means, annual means and Sen's slope line, with the reanalysis label visible.
- Switch to the precipitation tab.
- Provenance card: request URL, retrieval time, variable definitions, citation.
- *Evidence:* `frontend/src/App.tsx`. Manual browser check is still required before the demo (see TASKS).

## Slide 5: Finding 1: no significant temperature trend
- Sen's slope −0.16 °C/decade (95% CI −0.29 to −0.01), 1981–2025, 45 annual means.
- Naive Mann-Kendall p = 0.035 and OLS p = 0.026 would say "significant cooling".
- After correcting for autocorrelation (Yue & Wang 2004), p = 0.18: **not significant**.
- Annual means rose into the 1990s and declined after about 2002: multi-decadal variability, not a steady trend.
- Message: the tool stops a misleading headline.
- *Evidence:* `/api/trend?variable=T2M`; IMPLEMENTATION_LOG trend table; `test_trend.py` (false-positive tests).

## Slide 6: Finding 2: precipitation, with a caveat
- Sen's slope +0.24 mm/day per decade (95% CI +0.10 to +0.38), corrected p = 0.014: significant *in this dataset*.
- But NASA's own validation of POWER daily precipitation against stations: R² 0.39 (versus 0.97 for temperature).
- So EarthSignal reports it as needing independent confirmation, not as a fact about Lucknow's rainfall.
- No cause is claimed for either result.
- *Evidence:* `/api/trend?variable=PRECTOTCORR`; limitations list in the API output.

## Slide 7: Scientific integrity and next steps
- Built in: observed versus derived labels, immutable raw data, chronological cutoff, corrected significance tests, rule-based diagnostics, a written limitations list, 45 backend tests and 6 frontend tests.
- Next, planned and **not built**:
  1. Compare against an independent Lucknow station record.
  2. Seasonal trends and sensitivity checks.
  3. A chronological backtesting harness with simple baselines, before any forecast is shown.
  4. Additional NASA datasets (for example GPM IMERG precipitation), after access review.
- Team: AstraelForge (TheVisionForged).
- Data citation: NASA LaRC POWER Project, funded through the NASA Earth Science Division; Daily API v2.10.3, accessed 2026-11-14.

---

### Claims to avoid in the submission
- Do not say "satellite data" for these variables, "observed temperatures", "forecast", "AI predicts", or "Lucknow is cooling" / "Lucknow is getting wetter" as facts.
- Do not call the precipitation result confirmed.
- Do not imply city-street-scale or urban-heat-island resolution.
