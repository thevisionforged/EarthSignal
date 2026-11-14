# Milestone 4: explaining the 2014 POWER/IMERG precipitation divergence

**Question.** Milestone 3 found that NASA POWER (MERRA-2) and GPM IMERG precipitation agree closely before 2014 but diverge afterwards in both Lucknow cells. MERRA-2 trends upward and IMERG is flat. Which product departs from what rain gauges recorded?

**Approach.**
1. Find out from official documentation what MERRA-2's corrected precipitation is built from.
2. Add an independent, dense gauge reference (IMD).
3. Test, at dates fixed **in advance** from documentation, which product drifts away from the gauges.
4. Look directly at the gauge network behind MERRA-2.

## 1. What MERRA-2 corrected precipitation is built from (documented)
Source: Reichle, R. H. and Q. Liu (2014), *Observation-Corrected Precipitation Estimates in GEOS-5*, NASA/TM-2014-104606, Vol. 35 (NASA NTRS 20150000725). The journal paper Reichle et al. (2017) was not accessible (HTTP 403).
- Table 3 lists the inputs for MERRA-2:
  - **"Global land (excl. Africa) 1979 – present CPCU"**, method "BM"
  - Global ocean and Africa: GPCPv2.1, then CMAP from September 2009
- CPCU is the NOAA CPC Unified Gauge-Based Analysis of Global Daily Precipitation: daily, 0.5°, gauges only.
- **Version change:** "The CPCU 'V1.0' product was used for the period 1979-2005 and the CPCU 'real-time' ('RT') is used for the period 2006-present."

Source: CPC README, https://ftp.cpc.ncep.noaa.gov/precip/CPC_UNI_PRCP/GAUGE_GLB/DOCU/PRCP_CU_GAUGE_V1.0GLB_0.50deg_README.txt
- The README states the gauge counts directly: "1979 - 2005 : Rereospective Version (30K+ gauges)" and "2006 - Present : Real-time version (~17K gauges)".
- It also warns that "the analysis quality varies with the gauge network density."
- Each daily file contains the precipitation (0.1 mm) and "number of gauges available in each 0.5deg lat/lon grid box".

**Implication:** over Lucknow, POWER's PRECTOTCORR is anchored to a gauge analysis whose global network roughly **halved in 2006**.

## 2. Independent gauge reference: IMD 0.25° gridded rainfall
- **Source:** IMD Pune (https://www.imdpune.gov.in/cmpg/Griddata/Rainfall_25_Bin.html).
- **Coverage:** 1901–2024.
- **Format:** yearly binary files, 135 × 129 points from 6.5° N / 66.5° E, in mm, with −999 for missing.
- **Access:** public form download, no login.
- **Method (Pai et al. 2014, MAUSAM 65(1)):**
  - "daily rainfall records from 6955 rain gauge stations with varying availability periods"
  - Shepard inverse-distance interpolation
  - "≥3100 stations per day from 1951 onwards except in the last 2-3 years when the density reduced to about 1900 stations per day" (that is, of 1901–2010)
  - Station counts after 2010 are **not documented** in the sources read.
- **Licence:** no explicit licence on the download pages. IMD requests citation of Pai et al. (2014) and disclaims liability. Raw files are **not** committed.
- **Acquired:** 1998–2024, 27 yearly files (656 MB raw), each checked against the expected byte count (days × 135 × 129 × 4) and checksummed.
- **Format verified against geography (2024):**
  - Arabian Sea undefined on all days
  - Thar desert 418 mm/yr; Cherrapunji 4,332 mm/yr; Mumbai 2,969 mm/yr
  - Lucknow 855 mm/yr
  - big-endian decoding gives nonsense, so the files are little-endian
- **Not independent:** IMD shares some stations with the CPC and GPCC analyses. It is a *reference*, not truth.

## 3. Results: drift against IMD (`analysis/arbiter.py`, `/api/precip-arbitration`)
- **Basis:** monthly and annual totals only, because IMD's rainfall-day boundary is not documented in the sources read. Complete months and years only, 1998–2024, with all three products averaged over the same MERRA-2 cell.
- **Primary test:** the trend of (product − IMD).
- **Supporting break tests:** at the pre-registered 2006 date (CPCU switch) and 2014 date (IMERG TRMM→GPM), Bonferroni-corrected (α = 0.025).

| 1998–2024 | Eastern cell | Western cell |
|---|---|---|
| IMD gauge trend (mm/yr per decade) | +128 (p 0.05; significant in only 10 of 27 leave-one-year-out cases) | −40 (p 0.35; never significant) |
| MERRA-2 trend | +149 (p 0.01) | +92 (p 0.04) |
| IMERG trend | −8 (p 0.94) | −14 (p 0.48) |
| **Primary:** MERRA-2 − IMD trend | +39 (p 0.63), no drift | **+129 (p 0.02), drift** |
| **Primary:** IMERG − IMD trend | −140 (p 0.06), borderline | +4 (p 0.89), no drift |
| MERRA-2 − IMD mean, across **2006** | −40 → +109 mm/yr (**p 0.022**) | −67 → +151 mm/yr (**p 0.008**) |
| MERRA-2 − IMD mean, across 2014 | +83 → +68 (p 1.0) | −1 → +232 (p 0.002) |
| IMERG − IMD mean, across 2014 | +91 → −104 (p 0.069) | +26 → +104 (p 0.33) |
| Annual correlation with IMD: MERRA-2 / IMERG | 0.55 / 0.41 | 0.55 / 0.72 |

### Interpretation
- **Consistent across both cells:** MERRA-2 rises relative to the gauges, by about +150 to +220 mm/yr, after the documented **2006** switch of its gauge input (CPCU) from the retrospective (30K+ gauges) to the real-time (~17K gauges) analysis.
- **Western cell (airport):** the gauges show no trend. MERRA-2 drifts significantly away from them, and IMERG does not. Here the POWER rainfall increase is **not supported by gauges**.
- **Eastern cell:** the gauges show a borderline, fragile increase of a size similar to MERRA-2's. Neither product drifts significantly from the gauges over the full period. IMERG trends *below* the gauges (p 0.06). This cell does not settle which product is right.
- **Overall:** the Milestone 3 divergence is better explained by a **MERRA-2 shift at the 2006 CPCU version change** than by IMERG's 2014 transition. But the evidence is cell-dependent, the gauge reference itself is uncertain, and the local gauge counts (section 4) do not show *why* the version change would matter here.

### Bottom line for EarthSignal
**No precipitation trend for Lucknow should be stated.**
- The POWER/MERRA-2 increase is not supported by gauges in the western cell.
- It shifts relative to gauges at a documented input change in both cells.
- Its gauge input is extremely sparse locally.
- The gauge analysis that partly agrees with it (eastern cell) has a fragile trend.

### Corrected during the analysis
- **Verdict rule:** the first version called a product "departing" if *any* of three tests (trend plus two breaks) reached p < 0.05. That rule labelled the eastern cell "MERRA-2 departs", hiding that the gauges partly agree with MERRA-2. It was replaced by one pre-specified primary test per product, with Bonferroni-corrected supporting break tests and a leave-one-year-out robustness check on the reference.
- **Unsupported metadata claim:** an IMD rainfall-day definition was removed because the cited paper does not contain it.

## 4. The gauge network behind MERRA-2 (CPC archive sample)
- **Sample:** CPC daily files from the public HTTPS archive, 15 July and 15 August of each year, 1998–2024 (54 days), stored unmodified.
- **What was counted:** the files' own gauge-count field, for the CPC boxes overlapping each MERRA-2 cell and for a ±2° neighbourhood. CPC's optimal interpolation also draws on nearby gauges.
- **Format verified:** the global total for 2014-07-15 is 16,807, against the README's "~17K". The ocean is undefined, and Mumbai reads 160 mm on a monsoon day.
- **File naming:** the archive naming varies by year (`…RT.gz` in 2006, `….RT.gz` in 2007–2008, `….RT` later). The first run missed 2006–2008, and they were fetched separately after fixing the URL list.

| Period | Global gauges (mean) | Within ±2°, eastern cell | Within ±2°, western cell | In the cell's own CPC boxes |
|---|---|---|---|---|
| 1998–2005 (retrospective V1.0) | ~30,100 | 6.1 | 4.1 | 0–1 |
| 2006–2015 (real-time) | ~17,400 | 6.4 | 4.8 | 0–1 |
| 2016–2024 (real-time) | ~18,200 | 14.9 | 13.6 | 1–2 |

**Findings:**
- **Global network:** the change is exactly as documented (about 30K to 17K).
- **No local loss at 2006.** About 5–6 gauges within ±2° both before and after the switch. **The simple hypothesis that Lucknow lost gauges at the version change is not supported.** The MERRA-2 step relative to IMD at 2006 coincides with the switch, but its mechanism (different station sources, quality control or method in the real-time analysis) is not visible in gauge counts and is not established here.
- **Very sparse in all periods.** About 1 gauge falls in the CPC boxes covering each 55 km cell, and 5–15 within a roughly 450 km neighbourhood. IMD draws on thousands of gauges nationally.
- **2016 doubling.** Local gauge counts roughly double from 2016. This was **not** a pre-registered date, so it was not tested as a break. It is an observation only.

## 5. Limitations
- IMD is a gauge analysis with a varying network, and some of its stations may overlap with CPC and GPCC. Agreement with it is not proof.
- **Only 27 years.** The break tests compare 7–8 years before against 9–18 years after, so their power is limited.
- **CPCU itself not compared.** The CPCU precipitation series from NOAA PSL could not be fetched: PSL returned 429 Too Many Requests, then 502 Proxy Error. It was not retried aggressively.
- **No physical attribution.** Nothing here establishes the physical cause of the 2006 shift. It is a documented input change coinciding with a statistical step.
