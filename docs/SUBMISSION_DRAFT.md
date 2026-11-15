# NASA Space Apps submission draft (EarthSignal)

**Status: draft, not submitted.**
- The official Space Apps rules pages (spaceappschallenge.org) could **not** be read from this machine on 2026-11-15. The site's certificate chain (issuer "SSL.com TLS Issuing RSA CA R1", subject `www.space.apps.nasa.gov`) is not trusted by this Windows certificate store. Certificate checks were not bypassed.
- Every field below must be checked against the current official rules before submitting (section 6).

## 1. Project title
EarthSignal: honest climate signals for Lucknow from NASA data

## 2. High-level summary (about 100 words)
EarthSignal turns NASA Earth observations into climate findings for Lucknow, India, and checks them before claiming anything.
- **Sources:** NASA POWER (MERRA-2 reanalysis) and NASA GPM IMERG precipitation, cross-checked against an airport weather station (NOAA) and India's rain-gauge grid (IMD).
- **Provenance:** every download is stored unmodified with its provenance.
- **Statistics:** trends are tested with autocorrelation-corrected statistics, robustness windows and break dates fixed in advance.
- **Findings:**
  - There is no significant temperature trend over 1981–2025.
  - NASA POWER drifts from the airport thermometer after 2006.
  - POWER's rainfall increase is not supported by rain gauges in the western cell.
- **Restraint:** EarthSignal reports what the data supports, and what it doesn't.

## 3. NASA data used (with citations)
- **NASA POWER Daily API** v2.10.3: T2M and PRECTOTCORR (NASA GMAO MERRA-2 / GEOS-IT), Lucknow, 1981–2026. Accessed 2026-11-14.
  > "The data was obtained from the National Aeronautics and Space Administration (NASA) Langley Research Center (LaRC) Prediction of Worldwide Energy Resource (POWER) Project funded through the NASA Earth Science Division."
- **NASA GPM IMERG Final** daily 0.1° V07 (`GPM_3IMERGDF`), via POWER parameter `IMERG_PRECTOT`. Accessed 2026-11-14.
  > Huffman, G.J., E.F. Stocker, D.T. Bolvin, E.J. Nelkin, J. Tan (2023), GPM IMERG Final Precipitation L3 1 day 0.1 degree x 0.1 degree V07, GES DISC, doi:10.5067/GPM/IMERGDF/DAY/07.
- **NASA technical documentation used:**
  - Reichle & Liu (2014), NASA/TM-2014-104606 Vol. 35
  - IMERG V07 Technical Documentation (2023)
  - NASA CMR collection metadata

## 4. Other data
- **NOAA NCEI Global Surface Summary of the Day (GSOD):** station 42369099999, Lucknow airport. Non-commercial research use (WMO Resolution 40); shown with its notice.
- **India Meteorological Department 0.25° gridded rainfall** (Pai et al. 2014, MAUSAM 65(1), 1–18). Downloaded from imdpune.gov.in; no explicit licence found; cited as requested.
- **NOAA CPC Unified gauge analysis:** gauge counts only, from the CPC public archive.

## 5. Use of artificial intelligence (disclosure, factual)
- EarthSignal was developed with an AI coding assistant (Anthropic Claude, in Claude Code). It was used to write and test code, research official data documentation, run the analyses, and draft documentation, including this draft.
- The team directed the work, made the scientific and design decisions recorded in `docs/DECISIONS.md` (for example both grid cells, station data shown with its notice, and milestone scope), and approved every commit.
- No AI system generates the app's numerical results. The statements shown in the app are produced by fixed, unit-tested rules from computed statistics.
- **Edit this section to match the official disclosure wording and your own account of how the team worked.**

## 6. Confirm against the official rules before submitting
- [ ] Required submission fields, and limits on length or word count
- [ ] Demo format: video length limit and/or number of slides; whether a public link is required
- [ ] Whether the code repository must be public. It is **private** now; making it public is your decision.
- [ ] Licence requirements. The code is MIT-licensed (`LICENSE`, chosen by the user on 2026-11-15). Data keeps its providers' terms.
- [ ] Rules on work done before the event. EarthSignal's history is in git from 2026-11-14.
- [ ] AI-use disclosure wording, and whether AI-assisted projects are allowed in your event or category
- [ ] Challenge selection: which official challenge statement EarthSignal answers. Not chosen yet; slide 1 depends on it.
- [ ] Team, eligibility and deadline for your local or virtual event

## 7. Links (fill in after your decisions)
- **Demo:** *(video or slides link, after you publish)*
- **Code:** https://github.com/thevisionforged/EarthSignal *(currently private)*
