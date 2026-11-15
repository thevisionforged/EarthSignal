# Deploying EarthSignal on Render

One free Render **web service** built from the repository's `Dockerfile` serves both the API and the React app
from the same address. No database, no secrets and no paid services are needed. The design is recorded in DECISIONS D-027.

## How the deployed app gets its data
| Source | How it reaches the server | Why |
|---|---|---|
| NASA POWER, both grid cells (processed data plus raw API responses) | Committed snapshot in `data/` | Public NASA data. A snapshot keeps the deployed numbers identical to the analysed ones; a new download would shift them. |
| GPM IMERG via POWER (processed) | Committed snapshot | Public NASA data. The raw responses (14 MB) can be re-downloaded with `earthsignal.data.imerg_power`. |
| NOAA CPC gauge counts | Committed (`data/processed/cpc/gauge_counts.json`) | U.S. government data. |
| NOAA GSOD station 42369099999 | Downloaded from NOAA **during the build**, checked against `data/manifests/gsod_42369099999.json`, processed, then the raw files are deleted | Non-U.S. station data is for non-commercial use (WMO Resolution 40). It is never committed. |
| IMD 0.25° gauge rainfall, 1998–2024 | Downloaded from IMD **during the build** (27 × ~25 MB), checked against `data/manifests/imd_rf025.json`, processed, then the raw files are deleted | No redistribution terms were found. It is never committed. |
| Forecast evaluation (D-026) | Computed **once during the build** and cached in `data/cache/` | It takes about 8 s per cell on a laptop and much longer on 0.1 CPU. The cache is tied to the dataset and to the exact `forecast.py` code. |

The checksum manifests contain checksums only, not data. On 2026-11-15 a live download matched all 45 GSOD
files and the IMD 2024 file. If NOAA or IMD later change a file, the build prints `changed: <year>`, uses the new
file and records its checksum in the provenance. Set the environment variable `FETCH_STRICT=1` to fail the build instead.
If NOAA or IMD is unreachable during the build, the app still deploys. The station check and the gauge comparison
then report that their data is missing, and the Key findings page shows those two findings as "not available on this server". Set `FETCH_SOURCES=""` to skip both downloads.

## Configuration
Everything is in `render.yaml` (a Render Blueprint) and the `Dockerfile`.

| Setting | Value |
|---|---|
| Runtime | Docker (`./Dockerfile`, context `.`) |
| Plan / region | `free` / `singapore` (the region cannot be changed later) |
| Branch | `master`; `autoDeployTrigger: off`, so you deploy manually |
| Health check | `GET /api/ready`: 200 when the NASA POWER data for both cells is present, otherwise 503 |
| Start command | `uvicorn earthsignal.api.main:app --host 0.0.0.0 --port $PORT --workers 1 --proxy-headers` (in the Dockerfile) |
| Port | `$PORT`, Render's default is 10000 |
| Python / Node | 3.12.10 (`python:3.12.10-slim-bookworm`) / 22.11.0 (build stage only) |
| Python packages | exact versions in `backend/requirements.lock` |

### Environment variables (none are secret)
| Variable | Default in the image | Meaning |
|---|---|---|
| `EARTHSIGNAL_PUBLIC_DEMO` | `1` | Shows visitors that analyst cases are shared and cleared on restart |
| `EARTHSIGNAL_WARMUP` | `1` | Loads the cached forecast evaluation in the background at startup |
| `EARTHSIGNAL_FRONTEND_DIST` | `/app/frontend/dist` | Serve the built UI. Any non-API path returns `index.html`, so a page refresh works |
| `EARTHSIGNAL_CACHE_DIR` | `/app/data/cache` | Location of the forecast evaluation cache |
| `FETCH_SOURCES` | `gsod imd` | Build only: which restricted sources to download |
| `FETCH_STRICT` | empty | Build only: `1` fails the build on any checksum change |
| `EARTHSIGNAL_CORS_ORIGINS` | empty | Split deploy only: comma-separated UI origins allowed to call the API |
| `VITE_API_BASE` | empty | Split deploy only, build time: the API's origin, e.g. `https://api.example.org` |

The default single-service deploy serves the UI and API from the same origin, so it needs no CORS setting or
`VITE_API_BASE`. Render passes environment variables to the Docker build as build arguments.

## Manual steps (you do these; nothing has been created yet)
1. **Review and commit** the deployment changes locally, then push to `master` when you approve.
2. **Make the repository public** (GitHub → Settings → General → Danger Zone → Change visibility). Every commit
   becomes public, including the commit author address `thevisionforged@gmail.com`.
3. **Create the service from the Blueprint:** Render Dashboard → **New** → **Blueprint** → connect GitHub and choose
   `thevisionforged/EarthSignal` → Render reads `render.yaml` → check that the plan shows **Free** → **Apply**.
   - Render may ask for a payment method even on the free plan. Stop there if you don't want to add one.
4. **Watch the first build** (expect several minutes; the IMD download is about 650 MB). The log should show:
   - `gsod: 45 files match the recorded checksums`
   - `imd: 27 files match the recorded checksums`
   - `"ready": true`
   - `forecast evaluation lucknow: cached` and the same for `lucknow_airport`
5. **Check the live site** at the `https://earthsignal-XXXX.onrender.com` address Render shows:
   - `/api/ready` shows `"ready": true`, all optional sources present and `forecast_warmup.done: true`
   - Open each tab and refresh the page (it must reload, not 404)
   - Response Intelligence shows the public-demo note
   - Anticipate shows the outlook
   - Sources & precipitation shows IMD and the station comparison
6. **Share the deck** from its Share menu in claude.ai. Its link is private until you do.
7. To deploy a later change, push it and click **Manual Deploy → Deploy latest commit**.

## Behaviour to expect on the free plan
- **Spin-down:** after 15 minutes without visitors the service sleeps, and the next visit takes about a minute.
  Open the site a few minutes before a demo.
- **Cases are temporary:** cases opened on the public site are visible to everyone and cleared on every restart,
  redeploy or spin-down. Each case is limited to 200 logged actions and each note to 2,000 characters. There is
  one case per detected event.
- **Memory:** about 150 MB with every endpoint in use (measured locally), within the 512 MB limit.
- **Outlook date:** the outlook is issued from the last day in the snapshot (2026-11-11). It does not update by
  itself. To refresh it, download new POWER data, re-run the tests, update the `.gitignore` snapshot entries,
  commit and redeploy. This is deliberately manual, because new data changes the published numbers.

## Not verified locally
Docker is not installed on the development laptop, so the image itself has not been built locally. The rehearsal
was done on a clean copy of only the publishable files, using the same commands the Dockerfile runs: frontend
`npm ci` and production build, GSOD download and checksum check, readiness check, forecast precompute, and the
production server serving the UI. The first Render build is therefore the first real Docker build. If it fails,
the build log shows which step.
