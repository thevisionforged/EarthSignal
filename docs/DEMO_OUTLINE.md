# NASA Space Apps demo outline (7 slides)

Every claim below maps to something implemented and verified (see "Evidence").
- **Source data:** POWER datasets retrieved 2026-11-14 (eastern cell `power_daily_lucknow_…T173438Z`, western cell `power_daily_lucknow_airport_…T210009Z`) and GSOD dataset `gsod_42369099999_1981_2025_…T210127Z`.
- **Refresh before the demo:** if you re-run ingestion, take the numbers from the dashboard again.

Not yet known: the specific Space Apps challenge and its submission rules. Align slide 1 wording with the challenge statement once it is chosen.

---

## Slide 1: EarthSignal: reading Lucknow's climate record honestly
- Tagline: *Understand Reality. Simulate Possibilities. Anticipate Tomorrow.*
- Problem: city climate claims often skip where the data comes from, what kind of data it is, and whether a "trend" survives basic checks.
- Built: an open pipeline and dashboard that turns 45 years of NASA data for Lucknow into trend results, robustness checks, a station cross-check, provenance, and stated caveats.
- Scope today: **historical analysis only**. No forecasts.
- *Evidence:* README; dashboard header and banner.

## Slide 2: NASA data used
- NASA POWER Daily API (NASA Langley Research Center).
- Variables: `T2M`, 2 m air temperature (°C), and `PRECTOTCORR`, bias-corrected precipitation (mm/day). Definitions are quoted from NASA's metadata.
- What it is: **reanalysis**, meaning NASA GMAO MERRA-2 plus GEOS-IT for the latest weeks. Model output constrained by observations, on 0.5° × 0.625° cells. *Not* station or satellite readings, and the dashboard says so.
- Lucknow straddles a cell boundary, so EarthSignal analyses **both cells** (east and west).
- **Second NASA source:** GPM IMERG Final V07 precipitation (satellite microwave and infrared, calibrated to GPCC gauges), on 0.1° cells. It was obtained through POWER's `IMERG_PRECTOT` (UTC only, no login) and averaged over each MERRA-2 cell.
- *Evidence:* `/api/sources` (common metadata for all 5 datasets); `docs/research/GPM_IMERG_RESEARCH.md`.
- *Evidence:* `/api/areas`, `provenance.json`; DECISIONS D-004, D-005 and D-013.

## Slide 3: Pipeline and provenance (show it working)
- Pipeline: NASA POWER API, then raw JSON (immutable, SHA-256), then validation, then processed CSV and provenance, then FastAPI, then React dashboard.
- Recorded for every download: request URL, UTC retrieval time, API version (v2.10.3), sources (MERRA2, GEOSIT), coordinates, units, definitions, hashes, citation.
- Missing values: NASA's fill marker becomes "missing", never zero.
- Source switch date measured, not assumed: MERRA-2 to 2026-09-30, GEOS-IT from 2026-10-01. The trend window is all MERRA-2.
- Live: `python -m earthsignal.data.ingest` (about 5 s).
- *Evidence:* `backend/earthsignal/data/`; `test_power.py`, `test_ingest.py`, `test_source_probe.py`.

## Slide 4: Dashboard walkthrough (live)
- Switch between the eastern and western cells, and between temperature and precipitation.
- Trend card: plain verdict, Sen's slope with CI, corrected p, and "how to read these numbers".
- Robustness charts (start and end year), seasonal table, station check, provenance.
- *Evidence:* `frontend/src/`. A manual browser check is required before the demo.

## Slide 5: Finding 1: no robust temperature trend
- 1981–2025: −0.16 °C/decade in the eastern cell (corrected p 0.18), −0.12 in the western cell (p 0.35). **Not significant.**
- Naive tests (uncorrected Mann-Kendall, OLS) would have said "significant cooling". Correcting for autocorrelation removes that.
- Starting the analysis in 1983–1995 *would* give significant cooling, so the verdict depends on the window. EarthSignal flags this and reports the full period.
- No season is significant after the multiple-testing correction.
- *Evidence:* `/api/trend`, `/api/sensitivity`, `/api/seasonal`; IMPLEMENTATION_LOG.

## Slide 6: Finding 2: checking against a real thermometer
- NOAA GSOD station at Lucknow airport, compared with the POWER cell that contains it.
- Monthly agreement is high (r 0.977), with a +0.63 °C mean offset that is strongly seasonal: +3 °C in May and June, −1 °C in September and October.
- 2006–2023: station +0.10 °C/decade, POWER −0.26 °C/decade, difference **−0.30 °C/decade (p 0.017)**. The records drift apart, so POWER's recent cooling is not what the thermometer saw. Cause unknown.
- Precipitation: POWER's increase is significant in one cell but not the other, and the station's rain reports are too incomplete to check it. Slide 6b covers it.
- Station data notice (WMO Resolution 40): non-commercial research use; shown with attribution.
- *Evidence:* `/api/station-comparison`; DECISIONS D-015.

### Slide 6b (fold into slide 6 if you need exactly 7): a second NASA source on rainfall
- GPM IMERG versus POWER/MERRA-2, compared like for like: same MERRA-2 cell (42 IMERG sub-cells, area-weighted), same UTC days, mm, 1998 to 2025-09.
- Monthly totals agree closely (r 0.96–0.97; MERRA-2 is 3–7% wetter).
- Trend 1998–2024: MERRA-2 **+0.41 / +0.25 mm/day per decade** (east/west, significant). IMERG **−0.00 / −0.04** (no trend).
- The products track each other until 2014, then diverge: the mean difference goes from −8 to +172 mm/yr in the east, with the same pattern in the west. That is the TRMM-to-GPM satellite transition, but the data cannot tell which product changed.
- **Message:** POWER's rainfall increase is not supported by a second NASA dataset.
- **Milestone 4, against IMD rain gauges:**
  - In the western cell, POWER drifts away from the gauges (+129 mm/yr per decade, p 0.02) while IMERG matches them.
  - In both cells, POWER jumps relative to the gauges at 2006, the documented year its gauge input (NOAA CPC) switched versions.
  - Local CPC gauge counts did not change, so the mechanism is open.
- *Evidence:* `/api/precip-arbitration`; `docs/research/PRECIP_DIVERGENCE_INVESTIGATION.md`.
- *Evidence:* `/api/precip-comparison`, CSV downloads; DECISIONS D-019.

## Slide 7: Scientific integrity and next steps
- Built in: observed versus derived labels, immutable raw data, measured source boundary, corrected significance tests, FDR across seasons, robustness windows, a station cross-check with a homogeneity rule, a multi-source comparison with explicit aggregation rules, a common metadata interface, rule-based diagnostics, written limitations. 99 backend tests and 7 frontend tests.
- Next, planned and **not built**:
  1. Chronological backtesting harness with simple baselines, before any forecast is shown.
  2. Investigate the POWER−station drift (station history, MERRA-2 inputs).
  3. Verify POWER's IMERG values against native GES DISC files (needs a free Earthdata Login), and investigate which product changed around 2014.
- Team: AstraelForge (TheVisionForged).
- Citations: NASA LaRC POWER Project, funded through the NASA Earth Science Division (Daily API v2.10.3, accessed 2026-11-14). Huffman et al. (2023), GPM IMERG Final Precipitation L3 1 day 0.1° V07, GES DISC, doi:10.5067/GPM/IMERGDF/DAY/07, accessed via POWER 2026-11-14. NOAA NCEI Global Surface Summary of the Day (accessed 2026-11-14).

---

### Claims to avoid in the submission
- "Satellite data" for these variables, "observed temperatures" for POWER, "forecast", or "AI predicts".
- "Lucknow is cooling" or "Lucknow is getting wetter" stated as facts.
- Calling the precipitation result confirmed, or saying POWER is "validated" in general. Only monthly temperature agreement was checked, and it shows a drift.
- Implying street-scale or urban-heat-island resolution.
- Naming a cause for the POWER−station drift.
- Saying IMERG "validates" or "disproves" POWER. They are related products. Say they **disagree on the trend**.
- Saying "MERRA-2 is wrong" in general, or that the 2006 shift was *caused* by losing gauges. Local counts did not drop. Say "shifts relative to IMD gauges at a documented input change".
- Treating IMD as truth. It is a gauge-based reference with a varying network.
- Saying the IMERG data came straight from GES DISC. It came via POWER; native files need Earthdata Login and were not used.
