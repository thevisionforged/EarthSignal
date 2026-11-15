# Demo runbook

How to run a reliable live or recorded demo of EarthSignal. Every step here was run on 2026-11-15 on the development laptop (Windows 11).

## A. Before the demo (once, needs internet)
1. **Get the code:** clone or copy the repository and complete **Setup** in `README.md` (venv plus `npm install`).
   - Allow time: Python packages were slow to install on a ~40 KB/s connection (scipy is 37 MB).
2. **Download the data** (all of it is public; no account needed):

| Step | Command (repo root) | Time measured here | Size |
|---|---|---|---|
| POWER, eastern cell | `.venv\Scripts\python -m earthsignal.data.ingest` | ~5 s | 0.5 MB |
| POWER, western cell | `.venv\Scripts\python -m earthsignal.data.ingest --area lucknow_airport` | ~5 s | 0.5 MB |
| Source switch dates | `.venv\Scripts\python -m earthsignal.data.source_probe` and `... --area lucknow_airport` | ~10 s each | small |
| NOAA airport station | `.venv\Scripts\python -m earthsignal.data.gsod` | ~2 min | ~4 MB |
| GPM IMERG via POWER | `.venv\Scripts\python -m earthsignal.data.imerg_power --area lucknow` and `--area lucknow_airport` | ~10 min each | ~7 MB each |
| IMD rain-gauge grid | `.venv\Scripts\python -m earthsignal.data.imd 1998 1999 … 2024` then `--process` | ~15 min | ~656 MB |
| CPC gauge counts (optional) | see `docs/research/PRECIP_DIVERGENCE_INVESTIGATION.md` §4 | ~25 min | ~70 MB |

3. **Check it works:** `.venv\Scripts\python -m pytest backend` should report all tests passing. Then start the app (section B) and open each of the three views once.
4. **The demo then runs offline.** After the downloads, nothing needs the internet. Re-running a download creates a new dataset and may shift numbers slightly as NASA updates its record.

## B. Start the app
```powershell
# terminal 1 (repo root)
.venv\Scripts\python -m uvicorn earthsignal.api.main:app --app-dir backend --port 8000
# terminal 2
cd frontend; npm run dev
```
- Open the URL Vite prints (normally http://localhost:5173).
- If you change the code, **restart uvicorn**. It does not reload automatically, and an old backend lacks newer endpoints.

## C. Demo script (about 3 minutes)
| Time | Show | Say (only claims the app supports) |
|---|---|---|
| 0:00 | **Key findings** view | "EarthSignal checks what NASA data can and cannot tell us about Lucknow's climate. Each finding is computed live from stored NASA, NOAA and IMD downloads." |
| 0:30 | Finding 1, then *See the evidence* → temperature chart and trend card | "No significant temperature trend over 1981–2025 in either grid cell. Naive tests would wrongly call it significant cooling." |
| 1:00 | Robustness chart | "Starting the analysis in 1983–1995 would give 'significant cooling'. EarthSignal flags that the result depends on the window." |
| 1:20 | Station card | "Against the airport thermometer, NASA POWER drifts apart after 2006. We don't claim to know which record is responsible." |
| 1:45 | **Data sources** view → coverage and resolution table | "Six datasets, one metadata standard. Reanalysis, satellite, gauge grid and station data are labelled as what they are." |
| 2:10 | Gauge card: annual totals, then the gauge-count chart | "Against India's rain-gauge grid, POWER's rainfall increase isn't supported in the western cell. POWER shifts at 2006, the documented year its gauge input changed. Local gauge counts didn't drop, so we report the shift but not a cause." |
| 2:45 | Close | "No rainfall trend is claimed and no forecast is shown until it beats simple baselines. That's the point: honest Earth intelligence." |

## D. If something goes wrong
- **"Backend not reachable":** start terminal 1. If port 8000 is busy, run on another port and start Vite with `$env:EARTHSIGNAL_API_PORT=8001; npm run dev`.
- **A card says "unavailable"** or a 404 mentions a dataset: run the download command it names (section A).
- **Port 5173 busy:** Vite moves to 5174. Use the URL it prints.
- **Network problems** don't matter during the demo once the data is stored locally.

## E. Recording a video (if the submission needs one)
- Record the browser at 1280×720 or larger, following section C.
- Uploading or publishing the video is **your** decision and action.
