# Multi-source methodology (Milestone 3, Phases 3–4)

How EarthSignal compares NASA POWER (MERRA-2) precipitation with NASA GPM IMERG, and how it describes every dataset in one common way. The source facts are in [GPM_IMERG_RESEARCH.md](GPM_IMERG_RESEARCH.md).

## 1. Why the products cannot be compared directly

| Property | POWER `PRECTOTCORR` (MERRA-2) | POWER `IMERG_PRECTOT` (GPM IMERG) | Consequence |
|---|---|---|---|
| Spatial support | One 0.5° × 0.625° reanalysis cell (about 55 × 62 km) | One 0.1° cell (about 10 × 11 km) | A point's IMERG value describes about 1/31 of the MERRA-2 cell's area. In July 2024, IMERG monthly totals ranged from 299 to 397 mm across the 42 sub-cells of one MERRA-2 cell. |
| Day boundary | Local Solar Time by default (EarthSignal's Milestone 1–2 data) | **UTC only** (LST requests return −999 and a message) | Daily values shift by about 5.4 h. On 2024-07-01, MERRA-2 was 82.58 mm in LST and 43.56 mm in UTC. |
| Units | mm/day | mm/day (the native daily file gives a daily mean rate in mm/day) | Compatible: daily rate in mm/day = daily total in mm. |
| Period | 1981 to ~2 days ago | 1998-01-01 to 2026-09-14 (observed). The Final run ends **2025-09-30** (CMR). | Compare only 1998-01-01 to 2025-09-30. Later IMERG data is not Final run. |
| Inputs | Reanalysis with observation-corrected precipitation forcing | Satellite microwave + IR, MERRA-2 winds for morphing, GPCC gauge calibration (Final) | **Not independent.** Agreement is consistency, not validation. |
| Known artefacts | Changes over time in the observing system | TRMM→GPM transition (May/June 2014); weaker sensors before 2005 | Check trends for a step at 2014. |

## 2. Compatible-aggregation procedure (implemented in `analysis/multisource.py`)
1. **Same area.**
   - Find the MERRA-2 cell containing the study point. Its edges were verified empirically with live requests on both sides of each edge (D-017).
   - Request every 0.1° IMERG cell overlapping it (42 per Lucknow cell).
   - Average them, weighting each by overlap fraction × cos(latitude).
   - A day's area mean exists only if **all** cells are valid. Nothing is partially averaged or filled.
2. **Same day boundaries.** Request MERRA-2 `PRECTOTCORR` for that cell **in UTC** as well.
3. **Same units.** Both series are mm/day. Monthly and annual totals are sums of daily values, in mm.
4. **Same period.** Use only days from 1998-01-01 to 2025-09-30 where both series are valid.
5. **Complete aggregates only.** A month counts only if every day is present in both series, and a year only if all 12 months are.
6. **Symmetric treatment.** Neither series is "truth". Differences are always MERRA-2 − IMERG. Contingency terms (hits, misses) use IMERG only as the vocabulary reference.

## 3. Statistics reported
- **Daily:** bias, ratio of means, RMSE, Pearson r, Spearman ρ, and a wet-day (≥ 1 mm) contingency table (POD, FAR, CSI, frequency bias).
- **Monthly:** the same pair statistics, plus anomaly correlation after removing each series' own calendar-month mean, the mean seasonal cycle, and bias by calendar month.
- **Annual:** pair statistics. Trend of the annual-mean rate (mm/day per decade) for each series and for their difference, using the Milestone 1 method (Mann-Kendall with Yue-Wang correction, Sen's slope).
- **Era step:** mean annual difference for 1998–2013 vs 2015–2024, with 2014 excluded because it straddles the transition. Two-sided Mann-Whitney test. The split year comes from NASA's documented TRMM-to-GPM transition and was **not** chosen by looking at the data.
- **Scale sensitivity:** monthly r and RMSE for the single IMERG cell containing the study point versus the area mean.

## 4. Common metadata interface (`backend/earthsignal/metadata.py`, D-018)
Every dataset is described by `DatasetMetadata`:
- `provider`, `distributor`, `product_id`, `product_version`
- `variables` (name, units, definition, data_kind)
- `spatial_resolution`, `spatial_support`, `geographic_coverage`
- `temporal_resolution`, `time_standard`, `time_coverage`
- `retrieved_at_utc`, `processing_history`, `citation`
- `quality_limitations`, `access`, `usage_notice`

Existing NASA POWER and NOAA GSOD provenance files are **never rewritten**; adapters (`from_power_met`, `from_gsod`) derive the common description from them. New IMERG datasets embed the common block in their provenance. `GET /api/sources` serves all of them.

## 5. Reproducing
```powershell
.venv\Scripts\python -m earthsignal.data.imerg_power --area lucknow                 # 42 cells + MERRA-2 UTC, ~10 min at 40 KB/s
.venv\Scripts\python -m earthsignal.data.imerg_power --area lucknow_airport
.venv\Scripts\python -m earthsignal.data.imerg_power --from-raw data\raw\imerg\<dataset_id>   # offline reprocess
```
The results are served at `GET /api/precip-comparison?area=` and as CSV at `/api/precip-comparison.csv?area=&level=monthly|daily`.

## 6. Not yet done
- **Native check:** comparing POWER's IMERG values with native `GPM_3IMERGDF` V07 files for the same cells and days. This needs the user's Earthdata Login (GPM_IMERG_RESEARCH.md §5).
- **Attribution:** working out which product changed around 2014, using the MERRA-2 precipitation-correction documentation and IMERG release notes.
- **Gauges:** a gauge-based reference for Lucknow (for example IMD gridded rainfall), subject to access and licence review.
