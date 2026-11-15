"""Production wiring (D-027): readiness check, optional CORS, and serving the built frontend.

None of this changes any calculation. With default settings (local development) only `/api/ready` is added.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse

from earthsignal.config import STUDY_AREAS
from earthsignal.data import cpc, gsod, imd, imerg_power, store


def _newest(paths: list[Path]) -> str | None:
    best = None
    for p in paths:
        prov = json.loads(p.read_text(encoding="utf-8"))
        if best is None or prov["retrieved_at_utc"] > best["retrieved_at_utc"]:
            best = prov
    return best["dataset_id"] if best else None


def data_status(processed_root: Path) -> dict[str, Any]:
    """Which processed datasets this server can see, from provenance files only (cheap enough for a health check).
    NASA POWER for every study area is required; the other sources are optional (the views that need them report
    that they are missing)."""
    power = {k: (p[0]["dataset_id"] if (p := store.list_provenance(processed_root, k)) else None) for k in STUDY_AREAS}
    imerg = {k: _newest(list((processed_root / imerg_power.SUBDIR).glob(f"imergpower_{k}_[0-9]*/provenance.json")))
             for k in STUDY_AREAS}
    return {
        "required": {"nasa_power": power},
        "optional": {
            "gpm_imerg_via_power": imerg,
            "imd_gauge_grid": _newest(list((processed_root / imd.SUBDIR).glob("*/provenance.json"))),
            "noaa_gsod_station": _newest(list((processed_root / gsod.STORAGE_SUBDIR).glob("gsod_*/provenance.json"))),
            "cpc_gauge_counts": (processed_root / cpc.SUBDIR / "gauge_counts.json").is_file(),
        },
        "ready": all(power.values()),
    }


def add_ready(app: FastAPI, processed_root: Path, warm_state: dict[str, Any]) -> None:
    @app.get("/api/ready")
    def ready() -> JSONResponse:
        """Readiness for a load balancer: 200 only when the required NASA POWER data is present."""
        status = data_status(processed_root)
        status["forecast_warmup"] = dict(warm_state)
        return JSONResponse(status, status_code=200 if status["ready"] else 503)


def add_cors(app: FastAPI, origins: tuple[str, ...]) -> None:
    """Only for a split deployment (frontend on another domain). Same-origin deployments need none."""
    if origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=list(origins),
            allow_methods=["GET", "POST"],
            allow_headers=["Content-Type"],
            allow_credentials=False,
        )


def mount_frontend(app: FastAPI, dist: Path) -> None:
    """Serve the built React app. Any non-API path without a matching file returns index.html, so a page
    refresh on any client-side URL works. Unknown /api paths still return a JSON 404."""
    dist = dist.resolve()
    index = dist / "index.html"
    if not index.is_file():
        raise RuntimeError(f"EARTHSIGNAL_FRONTEND_DIST={dist} has no index.html; run `npm run build` in frontend/")

    @app.get("/", include_in_schema=False)
    def spa_root() -> FileResponse:
        return FileResponse(index, headers={"Cache-Control": "no-cache"})

    @app.get("/{full_path:path}", include_in_schema=False)
    def spa(full_path: str) -> FileResponse:
        if full_path == "api" or full_path.startswith("api/"):
            raise HTTPException(status_code=404, detail="Not Found")
        candidate = (dist / full_path).resolve()
        if candidate.is_file() and dist in candidate.parents:
            # Vite puts a content hash in every asset name, so assets can be cached for a long time.
            immutable = candidate.parent == dist / "assets"
            return FileResponse(candidate, headers={"Cache-Control": "public, max-age=31536000, immutable" if immutable else "no-cache"})
        return FileResponse(index, headers={"Cache-Control": "no-cache"})
