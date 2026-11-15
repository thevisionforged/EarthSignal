# EarthSignal: one container serving the API and the built React app on $PORT (DECISIONS D-027).
# Build:  docker build -t earthsignal .        Run:  docker run -p 10000:10000 earthsignal

# ---- 1. Frontend build ------------------------------------------------------------------------------------------
FROM node:22.11.0-bookworm-slim AS frontend
WORKDIR /app/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
# Leave empty for the default single-service deploy (UI and API on the same origin).
ARG VITE_API_BASE=""
ENV VITE_API_BASE=${VITE_API_BASE}
RUN npm run build

# ---- 2. Backend + data ------------------------------------------------------------------------------------------
FROM python:3.12.10-slim-bookworm
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1
WORKDIR /app

# Exact dependency versions the test suite passed with.
COPY backend/requirements.lock backend/requirements.lock
RUN pip install -r backend/requirements.lock
COPY backend/ backend/
# Editable install keeps the package inside /app/backend, so the repository paths in config.py resolve to /app.
RUN pip install --no-deps -e ./backend

# Committed snapshot: processed NASA POWER + GPM IMERG (via POWER) + NOAA CPC gauge counts, and checksum manifests.
COPY data/ data/

# GSOD station data and IMD gauge rainfall are not in the repository (terms of use). Download them from NOAA and
# IMD, verify every file against the recorded SHA-256 checksums, process, then delete the raw files so they are not
# in the image. Set FETCH_SOURCES="" to skip, or FETCH_STRICT=1 to fail the build on any checksum change.
ARG FETCH_SOURCES="gsod imd"
ARG FETCH_STRICT=""
RUN python -m earthsignal.data.deploy_data --fetch ${FETCH_SOURCES} ${FETCH_STRICT:+--strict} \
 && rm -rf data/raw/stations data/raw/imd \
 && python -m earthsignal.data.deploy_data --check --precompute-forecast /app/data/cache

COPY --from=frontend /app/frontend/dist frontend/dist

RUN useradd --create-home --uid 10001 earthsignal \
 && mkdir -p data/cases \
 && chown -R earthsignal data/cases data/cache
USER earthsignal

ENV EARTHSIGNAL_FRONTEND_DIST=/app/frontend/dist \
    EARTHSIGNAL_CACHE_DIR=/app/data/cache \
    EARTHSIGNAL_WARMUP=1 \
    EARTHSIGNAL_PUBLIC_DEMO=1 \
    PORT=10000
EXPOSE 10000

# One worker: the case file uses an in-process lock, and the free plan has 512 MB (measured ~150 MB in use).
CMD ["sh", "-c", "exec uvicorn earthsignal.api.main:app --host 0.0.0.0 --port ${PORT:-10000} --workers 1 --proxy-headers --forwarded-allow-ips '*'"]
