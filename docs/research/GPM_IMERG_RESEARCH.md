# GPM IMERG: source investigation (Milestone 3, Phase 1–2)

Investigated 2026-11-15. Every fact below has a source. **"Observed"** means EarthSignal saw it in a live API response on that date. **"Documented"** means it comes from an official NASA page or document. Where the two disagree, both are recorded.

## 1. Product identity (documented: NASA CMR collection metadata)
Source: `https://cmr.earthdata.nasa.gov/search/collections.umm_json?keyword=IMERG&provider=GES_DISC` (public API, no login).

| Run | Daily short name | Version | DOI | Temporal coverage (CMR) |
|---|---|---|---|---|
| **Final** (research grade) | `GPM_3IMERGDF` | 07 | 10.5067/GPM/IMERGDF/DAY/07 | 1998-01-01 to **2025-09-30** |
| Late (~14 h latency) | `GPM_3IMERGDL` | 07 | 10.5067/GPM/IMERGDL/DAY/07 | 1998-01-01 to ongoing |
| Early (~4 h latency) | `GPM_3IMERGDE` | 07 | 10.5067/GPM/IMERGDE/DAY/07 | 1998-01-01 to ongoing |

- **Related products:**
  - half-hourly: `GPM_3IMERGHH` (Final), `GPM_3IMERGHHL`, `GPM_3IMERGHHE`
  - monthly Final: `GPM_3IMERGM`
  - land/sea mask: `GPM_IMERG_LandSeaMask`
- **Version status:** "Version 07 is the current version of the data set. Older versions will no longer be available and have been superseded by Version 07." (CMR abstract)
- **Reprocessing:** the V07 release notes describe a second reprocessing labelled **V07B**, completed 8 January 2024 (https://gpm.nasa.gov/resources/documents/imerg-v07-release-notes). Sample granule names end in `.V07B.nc4`.
- **Citation (CMR `CollectionCitations`):** Huffman, G.J., Stocker, E.F., Bolvin, D.T., Nelkin, E.J., Tan, J. (2023), *GPM IMERG Final Precipitation L3 1 day 0.1 degree x 0.1 degree V07*. Edited by Andrey Savtchenko. Greenbelt, MD: Goddard Earth Sciences Data and Information Services Center (GES DISC). doi:10.5067/GPM/IMERGDF/DAY/07. Release date 2023-07-12. Add the access date when used.

## 2. Native daily file (documented: CMR variable metadata and IMERG V07 Technical Documentation)
- **Format:** NetCDF4, one **global** file per UTC day: `3B-DAY.MS.MRG.3IMERG.YYYYMMDD-S000000-E235959.V07B.nc4`.
- **Grid:**
  - 0.1° × 0.1°
  - Coverage 90° N to 90° S in V07: "The spatial coverage of Version 07 IMERG precipitation estimates is the latitude band 90°N-S". Infrared input covers only 60° N to 60° S.
- **Variables (CMR UMM-Var for `GPM_3IMERGDF` V07):**

| Variable | Units | Fill | Dimensions | Meaning |
|---|---|---|---|---|
| `precipitation` | mm/day | −9999.9 | (time, **lon, lat**) | Daily mean precipitation rate (combined microwave-IR). Formerly `precipitationCal`. |
| `precipitation_cnt` | count | none | (time, lon, lat) | Count of all valid half-hourly retrievals for the day (completeness, up to 48) |
| `precipitation_cnt_cond` | count | none | (time, lon, lat) | Count of half-hourly retrievals with precipitation above a threshold |
| `randomError` | mm/day | −9999.9 | (time, lon, lat) | RMS error estimate for the daily rate |
| `MWprecipitation` (+ `_cnt`, `_cnt_cond`) | mm/day | −9999.9 | (time, lon, lat) | Microwave-only daily mean rate |
| `probabilityLiquidPrecipitation` | percent | none | (time, lon, lat) | Probability of liquid phase |

- **Dimension order:** longitude comes before latitude. Readers must not assume (lat, lon).
- **Units:** half-hourly IMERG fields are mm/hr ("All precipitation products have been converted from their original units to mm/hr", Technical Documentation). The daily file stores a daily mean **rate** in mm/day, which is numerically equal to the daily total in mm.
- **Missing values:** "All products in IMERG use the standard missing value '-9999.9'" (Technical Documentation, section 8).

## 3. Processing method (documented: IMERG V07 Technical Documentation, 13 July 2023)
- **What it is:** a multi-satellite merge of passive-microwave retrievals (GPROF), morphed in time and supplemented with infrared estimates (PERSIANN-CCS). It is calibrated to the GPM Combined Radar-Radiometer algorithm.
- **Final-run inputs:** "The IMERG Final Run uses MERRA-2 for the atmospheric fields used to estimate displacement vectors, GPCC monthly Monitoring Analysis for gauge, and 'climatologically tuned' GPROF precipitation retrievals that depend on ERA5."
- **Gauge calibration:** the Final run is calibrated to the GPCC monthly gauge analysis. The Early and Late runs use climatological calibration to the Final run.
- **Latency:** "The pacing items are the GPCC and ERA5, usually giving a latency of about 3.5 months."
- **Consequence for EarthSignal:** IMERG Final is **not independent of MERRA-2**, because MERRA-2 winds drive the morphing, and its gauge input (GPCC) may share stations with other gauge-corrected products. Agreement between IMERG and POWER/MERRA-2 is therefore not independent validation.

## 4. Known limitations (documented)
- **CMR abstract:** "satellite estimates of precipitation are expected to have lower skill over frozen surfaces, complex terrain, and coastal zones." Also: "the changing GPM satellite constellation over time may introduce artifacts that affect studies focusing on multi-year changes."
- **TRMM-era caveats (G. Huffman, 3 May 2019; written for V06):**
  - "one would expect the underlying calibrations to shift across the transition boundary (May/June 2014)", the TRMM-to-GPM change.
  - Before 2005, less capable microwave sensors and "more use of IR-based estimates in the first few years. IR estimates are generally of lower quality and potentially introduce a systematic regional offset in the timing of precipitation systems."
  - Source: https://docserver.gesdisc.eosdis.nasa.gov/public/project/GPM/IMERGV06_TRMMera-caveats.pdf. V07 may differ, and this document predates it.
- **GPCC version switches:** "When the GPCC analyses are updated, we switch to the new version and continue processing forward, even though (in principle) there is a small inhomogeneity as a result." (Technical Documentation)
- **Consequence:** IMERG trends across 2014, and to a lesser degree across 2005, need step-change checks. They must not be presented as homogeneous without such checks.

## 5. Access and authentication (documented and observed)
- **Documented:** "Data user registration is required at PPS and GES DISC … This registration is simple, free, automatic, and on-line" (Technical Documentation). GES DISC registration: https://disc.gsfc.nasa.gov/registration/registration-for-data-access
- **Observed (no credentials, nothing downloaded):**
  - An HTTPS `GET` of `https://data.gesdisc.earthdata.nasa.gov/data/GPM_L3/GPM_3IMERGDF.07/2024/07/3B-DAY.MS.MRG.3IMERG.20240701-S000000-E235959.V07B.nc4` returns **302 to `urs.earthdata.nasa.gov/oauth/authorize`**.
  - The OPeNDAP endpoint (`opendap.earthdata.nasa.gov/...`) returns **302 to `/login/urs`**.
  - A `HEAD` request returned a signed redirect, but EarthSignal does not rely on that behaviour. The documented requirement is Earthdata Login.
- **Supported mechanisms (CMR related URLs):** HTTPS file download, OPeNDAP (subsetting by variable and array index), Earthdata Search, and direct S3 for in-region cloud use. The GES DISC README also lists its subsetting user interface.
- **What the user must do (EarthSignal never handles credentials):**
  1. Create a free Earthdata Login account at https://urs.earthdata.nasa.gov.
  2. Authorise the "NASA GESDISC DATA ARCHIVE" application in the Earthdata profile (Applications, then Authorized Apps).
  3. Store the credentials **outside the repository**: either a `.netrc` in the user's home directory (`machine urs.earthdata.nasa.gov login … password …`), or an Earthdata bearer token in an environment variable such as `EARTHDATA_TOKEN`.
  4. Tell EarthSignal which method to use. Code will only read them at run time and never print, log or commit them.

## 6. Size and compute
- **Per file:** one global daily file is **31.7 MB** (CMR granule metadata for 2024-07-01; the collection lists an average of 12 MB).
- **Whole record:** a full 1998–2025 download is about 10,200 files, roughly **300+ GB**, which is not feasible here (the network measured ~40 KB/s, so one file takes about 13 minutes).
- **Feasible native route:** OPeNDAP subsetting of `precipitation` and `precipitation_cnt` for a small Lucknow box (about 6 × 7 cells), one request per day, a few KB each. That works after login, but means ~10,000 requests, so it suits a sample or a short period. Bulk native time series would need a server-side time-series service; that was not investigated further.
- **Python:** reading NetCDF4 natively needs `h5netcdf`/`h5py` or `netCDF4`, which are new dependencies (ask before installing). OPeNDAP ASCII or DAP4 CSV output can be parsed without them.

## 7. IMERG through NASA POWER (observed; no login)
NASA POWER serves IMERG as parameter `IMERG_PRECTOT` (parameter-metadata API: "The average IMERG total precipitation at the surface of the earth", mm/day).

| Fact | Observation, 2026-11-15 |
|---|---|
| Time standard | **UTC only.** With `time-standard=LST` every value is −999 and `messages` says "The IMERG Source Data is not available at the Local Solar Time (LST) standard." |
| Grid | **Native 0.1° cells, no interpolation.** Points anywhere inside the cell 26.8–26.9° N × 80.9–81.0° E (including its corner) return identical values; points across an edge differ. Cell edges fall on multiples of 0.1°. |
| Coverage | Valid from **1998-01-01**. Last valid day **2026-09-14**, first missing 2026-09-15. Earlier dates return −999. POWER's documentation says "June 1, 1998" and "Near Real Time". **Observed coverage differs from the documentation.** |
| Run and version | POWER documents a mix: "IMERG Final Run … 3.5 Months Behind Near Real Time" and "IMERG Late Run … End of IMERG Final Run … Near Real Time". It does not state a version. Because CMR's Final record ends 2025-09-30, POWER values from 2025-10-01 onward **cannot be Final run**. |
| Count field | `IMERG_PRECTOT_COUNT` = "count of half-hourly precipitation retrievals where precipitation is at least 0.01 mm". This is the *conditional* count, so it **cannot** serve as a completeness check. |
| POWER's own validation | Against GSOD, weekly and monthly only. Monthly all-events: IMERG bias 11.63, RMSE 59.51, R² 0.68; MERRA-2 bias 5.31, RMSE 55.74, R² 0.69. Source: sources_meteorology page. |
| Trend guidance | POWER: "end the analysis 3.5 months behind NRT when assessing trends." |

**Unverified until a native sample exists:** that POWER's `IMERG_PRECTOT` equals the native `GPM_3IMERGDF` `precipitation` for the same 0.1° cell and UTC day.

## 8. Conclusions for EarthSignal
1. **Use IMERG through POWER now** (no login), labelled as *"NASA POWER distribution of GPM IMERG (V07 inferred, not stated by POWER)"*. Use only data on or before **2025-09-30**, the end of the Final run in CMR, for any trend or validation statement.
2. **Treat native `GPM_3IMERGDF` as the reference.** Fetch a small native sample after the user's Earthdata login is set up, and check that POWER's values equal the native values.
3. **Do not treat IMERG as independent of MERRA-2,** and do not treat 1998–2025 IMERG trends as homogeneous without checks across 2005 and 2014.
